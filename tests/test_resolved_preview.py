"""Resolved Environment preview (T13).

The preview answers "what will actually be injected?" for the context shown in
the window's context bar. The pickers moved to the bar (2026-10-25), so these
tests drive ``set_context()`` directly: re-resolving on a new context, shadowed
keys, the empty/department-less paths and ``Copy .env``.
"""

import pytest
from PySide6.QtCore import Qt

from launcher.ui.fakes import FakeSettingsDataSource
from launcher.ui.viewmodels import SettingsContext
from launcher.ui.widgets.resolved_preview import ResolvedPreview

CYBERPUNK = SettingsContext(project="CyberPunk", dcc="maya", department="fx")


@pytest.fixture
def preview(qapp):
    widget = ResolvedPreview(FakeSettingsDataSource("rich"))
    widget.set_context(CYBERPUNK)
    yield widget
    widget.deleteLater()


def _rows(preview) -> dict[str, str]:
    """Return {name: value} from the rendered table."""
    table = preview.table
    return {
        table.item(r, 0).text(): table.item(r, 1).text()
        for r in range(table.rowCount())
    }


class TestResolve:
    def test_renders_the_current_context(self, preview):
        assert preview.table.rowCount() > 0
        assert preview.table.rowCount() == len(preview.rows)
        values = _rows(preview)
        assert values["SHOW"] == "CyberPunk"
        assert values["DCC"] == "maya"
        assert values["DEPARTMENT"] == "fx"

    def test_new_context_reresolves(self, preview, qapp):
        preview.set_context(SettingsContext(project="DragonLand", dcc="nuke",
                                            department="comp"))
        values = _rows(preview)
        assert values["SHOW"] == "DragonLand"
        assert values["DCC"] == "nuke"
        assert values["DEPARTMENT"] == "comp"
        assert preview.context.project == "DragonLand"

    def test_empty_context_resolves_to_nothing(self, qapp):
        widget = ResolvedPreview(FakeSettingsDataSource("rich"))
        widget.set_context(SettingsContext())
        assert widget.table.rowCount() == 0
        assert "no variables" in widget.summary_label.text()
        widget.deleteLater()

    def test_missing_department_still_resolves(self, qapp):
        """An unset department is not an error: the resolver falls back."""
        widget = ResolvedPreview(FakeSettingsDataSource("rich"))
        widget.set_context(SettingsContext(project="CyberPunk", dcc="maya",
                                          department=""))
        assert widget.table.rowCount() > 0
        widget.deleteLater()

    def test_shadowed_rows_are_flagged(self, preview):
        assert "shadowed" in preview.summary_label.text()
        tooltips = [
            preview.table.item(r, 2).toolTip()
            for r in range(preview.table.rowCount())
        ]
        assert any("nothing shadowed" not in tip for tip in tooltips)
        assert any("nothing shadowed" in tip for tip in tooltips)

    def test_scope_column_is_a_badge(self, preview):
        texts = [preview.table.item(r, 2).text()
                 for r in range(preview.table.rowCount())]
        assert all(text.startswith("[") and text.endswith("]") for text in texts)
        assert "[derived]" in texts

    def test_env_text_is_name_value_lines(self, preview):
        lines = preview.env_text().splitlines()
        assert len(lines) == preview.table.rowCount()
        assert all("=" in line for line in lines)
        assert "SHOW=CyberPunk" in lines

    def test_row_count_signal_fires(self, qapp):
        seen = []
        widget = ResolvedPreview(FakeSettingsDataSource("rich"))
        widget.resolved_changed.connect(seen.append)
        widget.set_context(CYBERPUNK)
        assert seen == [widget.table.rowCount()]
        widget.deleteLater()

    def test_broken_source_reports_instead_of_raising(self, qapp):
        class _Stub:
            def resolved(self, show, dcc, department):
                raise RuntimeError("database down")

        widget = ResolvedPreview(_Stub())  # type: ignore[arg-type]
        widget.set_context(CYBERPUNK)
        assert widget.table.rowCount() == 0
        assert "Could not resolve" in widget.summary_label.text()
        widget.deleteLater()


class TestWindowIntegration:
    """The preview is driven by the window's context bar, not by itself."""

    def test_window_context_reaches_the_preview(self, qapp):
        from launcher.ui.settings_window import SettingsWindow

        win = SettingsWindow(data_source=FakeSettingsDataSource("rich"),
                             context=SettingsContext(project="SpaceOdyssey",
                                                     dcc="houdini",
                                                     department="lighting",
                                                     seq="seq001", shot="sh010"))
        assert win.resolved_preview.context.project == "SpaceOdyssey"
        assert _rows(win.resolved_preview)["DCC"] == "houdini"
        assert _rows(win.resolved_preview)["DEPARTMENT"] == "lighting"
        win.deleteLater()

    def test_editing_the_bar_reresolves_the_preview(self, qapp):
        from launcher.ui.settings_window import SettingsWindow

        win = SettingsWindow(data_source=FakeSettingsDataSource("rich"),
                             context=CYBERPUNK)
        index = win.project_combo.findData("DragonLand")
        win.project_combo.setCurrentIndex(index)
        assert _rows(win.resolved_preview)["SHOW"] == "DragonLand"
        win.deleteLater()


class TestInPlaceEdit:
    """Editing a value in the table (card C5)."""

    def test_filling_the_table_does_not_look_like_an_edit(self, preview, qapp):
        seen = []
        preview.env_edited.connect(lambda name, value: seen.append((name, value)))

        preview.set_context(SettingsContext(project="DragonLand", dcc="nuke",
                                            department="comp"))
        qapp.processEvents()

        assert seen == []

    def test_editing_a_value_cell_emits_the_name_and_the_new_value(self, preview, qapp):
        seen = []
        preview.env_edited.connect(lambda name, value: seen.append((name, value)))
        row = _row_of(preview, "ASSET_ROOT")

        preview.table.item(row, 1).setText("/tmp/edited-assets")
        qapp.processEvents()

        assert seen == [("ASSET_ROOT", "/tmp/edited-assets")]

    def test_a_value_cell_goes_back_to_read_only_after_the_edit(self, preview, qapp):
        row = _row_of(preview, "ASSET_ROOT")

        preview.table.item(row, 1).setText("/tmp/edited")

        flags = preview.table.item(row, 1).flags()
        assert not (flags & Qt.ItemFlag.ItemIsEditable)

    def test_the_name_cell_is_never_editable(self, preview, qapp):
        seen = []
        preview.env_edited.connect(lambda name, value: seen.append((name, value)))
        row = _row_of(preview, "ASSET_ROOT")

        preview.table.item(row, 0).setText("RENAMED")
        qapp.processEvents()

        assert seen == []


def _row_of(preview, name: str) -> int:
    """Row index of *name* in the rendered table."""
    for row in range(preview.table.rowCount()):
        if preview.table.item(row, 0).text() == name:
            return row
    raise AssertionError(f"{name} is not rendered")
