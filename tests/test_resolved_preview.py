"""Resolved Environment preview (T13).

The preview answers "what will actually be injected?" for a
show / DCC / department triple. These tests pin the wiring: the pickers come
from the data source (not from YAML), changing one re-resolves, shadowed keys
are flagged, and ``Copy .env`` emits the real lines.
"""

import pytest

from launcher.ui.fakes import FakeSettingsDataSource
from launcher.ui.settings_window import SettingsWindow
from launcher.ui.widgets.resolved_preview import ResolvedPreview


@pytest.fixture
def preview(qapp):
    widget = ResolvedPreview(FakeSettingsDataSource("rich"))
    yield widget
    widget.deleteLater()


def _rows(preview):
    """Return {name: value} from the rendered table."""
    table = preview.table
    return {
        table.item(r, 0).text(): table.item(r, 1).text()
        for r in range(table.rowCount())
    }


class TestPickers:
    def test_lists_shows_from_the_data_source(self, preview):
        assert preview.show_combo.count() == 3
        assert preview.show_combo.currentData()

    def test_dcc_and_department_vocabularies_come_from_the_source(self, preview):
        roles = [preview.dcc_combo.itemData(i) for i in range(preview.dcc_combo.count())]
        depts = [preview.department_combo.itemData(i)
                 for i in range(preview.department_combo.count())]

        assert roles == ["maya", "houdini", "nuke"]
        assert "fx" in depts
        assert preview.department_combo.currentData() == "fx"


class TestResolution:
    def test_renders_the_resolved_rows(self, preview):
        assert preview.table.rowCount() == 26          # fixture contract
        assert _rows(preview)["SHOW"] == preview.show_combo.currentData()

    def test_changing_the_dcc_re_resolves(self, preview):
        index = preview.dcc_combo.findData("maya")
        preview.dcc_combo.setCurrentIndex(index)

        rows = _rows(preview)
        assert rows["DCC"] == "maya"
        assert rows["PIPELINE_DCC"] == "maya"

    def test_changing_the_department_re_resolves(self, preview):
        preview.department_combo.setCurrentIndex(
            preview.department_combo.findData("lighting")
        )

        assert _rows(preview)["DEPARTMENT"] == "lighting"

    def test_changing_the_show_re_resolves(self, preview):
        preview.show_combo.setCurrentIndex(1)

        assert _rows(preview)["SHOW"] == preview.show_combo.currentData()

    def test_shadowed_key_keeps_the_loser_in_the_tooltip(self, preview):
        table = preview.table
        for row in range(table.rowCount()):
            if table.item(row, 0).text() == "OCIO":
                assert "global:" in table.item(row, 2).toolTip()
                break
        else:                                          # pragma: no cover
            pytest.fail("OCIO fixture row missing")

    def test_empty_source_says_so(self, qapp):
        widget = ResolvedPreview(FakeSettingsDataSource("empty"))
        try:
            assert widget.table.rowCount() == 0
            assert "no variables" in widget.summary_label.text()
        finally:
            widget.deleteLater()


class TestOutput:
    def test_env_text_is_name_equals_value(self, preview):
        lines = preview.env_text().splitlines()

        assert lines and all("=" in line for line in lines)
        assert any(line.startswith("DCC=") for line in lines)

    def test_copy_button_copies_the_rows(self, qapp):
        window = SettingsWindow(data_source=FakeSettingsDataSource("rich"))
        try:
            window.show()
            window._on_copy_env()
            copied = window.resolved_preview.env_text()

            assert copied
            assert "env copied" in window.saved_label.text()
        finally:
            window.close()
            window.deleteLater()


class TestRealSource:
    def test_preview_uses_the_real_vocabulary(self, qapp):
        from launcher.database.database import DatabaseManager
        from launcher.ui.real_source import RealSettingsDataSource

        db = DatabaseManager()
        db.connect()
        source = RealSettingsDataSource(db=db)
        if not source.db.is_connected:
            pytest.skip("launcher database not available")

        widget = ResolvedPreview(source)
        try:
            roles = [widget.dcc_combo.itemData(i) for i in range(widget.dcc_combo.count())]
            depts = [widget.department_combo.itemData(i)
                     for i in range(widget.department_combo.count())]
            assert "houdini" in roles
            assert {"comp", "lighting", "fx"} <= set(depts)
            assert widget.table.rowCount() > 0
            assert _rows(widget)["SHOW"] == widget.show_combo.currentData()
        finally:
            widget.deleteLater()
