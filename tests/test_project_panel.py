"""Tests for the right-hand Project column (settings window r7, 2026-10-26).

The column's job is not to list projects — the context bar picks one. It has to
answer, for that one show: is it healthy, where do its paths point, what is in
it, which env layers does it own, and what is dangerous. Each card gets its own
test so a regression points at the card, not at "the panel".
"""

import pytest
from PySide6.QtWidgets import QDialog, QLineEdit

from launcher.ui.fakes import FakeSettingsDataSource
from launcher.ui.viewmodels import ApplySummary, SettingsContext
from launcher.ui.widgets import project_panel as project_panel_module
from launcher.ui.widgets.project_panel import (
    MARK_MISSING,
    MARK_UNKNOWN,
    ProjectPanel,
)


@pytest.fixture
def ds():
    return FakeSettingsDataSource("rich")


@pytest.fixture
def panel(qapp, ds):
    widget = ProjectPanel(ds)
    widget.set_project("CyberPunk")
    yield widget
    widget.deleteLater()


def _paths(panel) -> dict[str, tuple[str, str]]:
    """``{label: (mark, value)}`` read back out of the paths grid."""
    grid = panel.paths_grid
    out: dict[str, tuple[str, str]] = {}
    for row in range(grid.rowCount()):
        mark = grid.itemAtPosition(row, 0).widget().text()
        label = grid.itemAtPosition(row, 1).widget().text()
        field = grid.itemAtPosition(row, 2).widget()
        out[label] = (mark, field.text())
    return out


class TestHealth:
    def test_complete_project_reads_ready(self, panel):
        assert panel.verdict_label.text() == "Ready"
        assert "5/5" in panel.health_detail.text()
        assert panel.repair_btn.isEnabled() is False

    def test_missing_project_names_the_problem(self, panel, ds):
        panel.set_project("DragonLand")
        assert "folder(s) missing" in panel.verdict_label.text()
        assert "5/5" not in panel.health_detail.text()
        assert panel.repair_btn.isEnabled() is True

    def test_warnings_are_reported_but_do_not_colour_the_verdict(self, panel):
        """Global checks belong to the middle column — reported, not judged here."""
        assert panel.verdict_label.text() == "Ready"
        assert "1 warning" in panel.checks_label.text()

    def test_clean_checks_say_clean(self, qapp):
        widget = ProjectPanel(FakeSettingsDataSource("empty"))
        assert widget.checks_label.text() == ""
        widget.deleteLater()

    def test_repair_is_idempotent_and_visible(self, panel):
        panel.set_project("DragonLand")
        first = panel.repair_now()
        assert first.counts()[0] > 0
        assert "created" in panel.repair_status.text()

        second = panel.repair_now()
        assert second.counts()[0] == 0, "a second repair must create nothing"
        assert second.counts()[1] > 0
        # The card re-reads the data source, so the verdict flips to Ready.
        assert panel.verdict_label.text() == "Ready"
        assert panel.repair_btn.isEnabled() is False

    def test_unknown_project_is_not_rendered_as_empty_project(self, panel):
        panel.set_project("DoesNotExist")
        assert panel.verdict_label.text() == "Unknown project: DoesNotExist"

    def test_nothing_selected_says_so(self, panel):
        panel.set_project("")
        assert panel.verdict_label.text() == "No project selected"


class TestPaths:
    def test_every_path_is_rendered_with_a_mark(self, panel):
        paths = _paths(panel)
        assert set(paths) == {"Root", "Publish", "Cache", "Assets", "Renders"}
        assert all(mark != MARK_MISSING for mark, _ in paths.values())

    def test_paths_are_read_only_and_selectable(self, panel):
        grid = panel.paths_grid
        field = grid.itemAtPosition(0, 2).widget()
        assert isinstance(field, QLineEdit)
        assert field.isReadOnly() is True
        assert field.text().endswith("/CyberPunk")
        assert field.toolTip().startswith("/Volumes/Development")

    def test_missing_paths_get_the_missing_mark(self, panel):
        panel.set_project("DragonLand")
        paths = _paths(panel)
        assert paths["Root"][0] == MARK_MISSING
        assert paths["Publish"][0] == MARK_MISSING

    def test_unchecked_project_shows_unknown_not_dead(self, panel):
        """``scaffold_state == "n/a"`` means unchecked — never claim a path is dead."""
        panel.set_project("SpaceOdyssey")
        assert _paths(panel)["Root"][0] == MARK_UNKNOWN
        assert "not checked" in panel.health_detail.text()

    def test_source_is_named(self, panel):
        assert panel.source_label.text().startswith("source: database")

    def test_disabled_project_is_flagged(self, panel, ds):
        ds._created.append(type(ds.projects()[0])(
            name="GhostShow", root="/tmp/r", publish_root="/tmp/p",
            enabled=False, scaffold_state="n/a"))
        panel.set_project("GhostShow")
        assert "disabled" in panel.source_label.text()


class TestContents:
    def test_counts_come_from_the_project_row(self, panel):
        text = panel.counts_label.text()
        assert "3 sequence(s)" in text
        assert "18 shot(s)" in text
        assert "2 show-scoped var(s)" in text

    def test_vocabulary_is_shown(self, panel):
        text = panel.vocab_label.text()
        assert "departments:" in text
        assert "dcc:" in text
        assert "houdini" in text


class TestLayers:
    def test_layer_counts_cover_all_five_scopes(self, panel):
        text = panel.layers_label.text()
        for scope in ("derived", "global", "show", "dcc", "department"):
            assert scope in text

    def test_only_this_shows_overrides_are_counted(self, panel):
        panel.set_project("DragonLand")
        assert "show 0" in panel.layers_label.text()

    def test_guarded_override_is_called_out(self, panel):
        text = panel.guarded_label.text()
        assert "OCIO @ show:CyberPunk" in text
        assert "guard" in text

    def test_guarded_warning_is_absent_for_another_show(self, panel):
        panel.set_project("DragonLand")
        assert panel.guarded_label.text() == ""

    def test_guarded_keys_are_the_comparability_class(self):
        from launcher.ui.viewmodels import GUARDED_SCOPE_KEYS
        assert {"OCIO", "ACES_CONFIG"} <= set(GUARDED_SCOPE_KEYS)


class TestDangerZone:
    def test_collapsed_by_default(self, panel):
        assert panel.danger_body.isVisibleTo(panel) is False
        assert panel.danger_toggle.isChecked() is False

    def test_toggle_reveals_it(self, panel):
        panel.danger_toggle.setChecked(True)
        assert panel.danger_body.isVisibleTo(panel) is True
        panel.danger_toggle.setChecked(False)
        assert panel.danger_body.isVisibleTo(panel) is False

    def test_destructive_actions_are_not_wired(self, panel):
        """A rename touches disk + DB + env scope key + publish root: no button."""
        assert panel.deactivate_btn.isEnabled() is False
        assert panel.delete_btn.isEnabled() is False
        assert "Not wired yet" in panel.deactivate_btn.toolTip()


class TestStates:
    def test_errors_mode_reports_the_backend_failure(self, qapp):
        widget = ProjectPanel(FakeSettingsDataSource("errors"))
        assert "Could not load projects" in widget.verdict_label.text()
        assert widget.paths_grid.count() == 0
        widget.deleteLater()

    def test_empty_mode_has_no_project(self, qapp):
        widget = ProjectPanel(FakeSettingsDataSource("empty"))
        assert "No project selected" in widget.verdict_label.text()
        assert widget.open_root_btn.isEnabled() is False
        widget.deleteLater()

    def test_set_context_is_the_window_entry_point(self, panel):
        panel.set_context(SettingsContext(project="DragonLand"))
        assert panel.project == "DragonLand"


class TestCreation:
    """The ``+`` next to the column title opens New Project (card C7)."""

    def test_the_plus_button_is_there_and_explains_itself(self, panel):
        assert panel.new_project_btn.text() == "+"
        assert "New project" in panel.new_project_btn.toolTip()

    def test_the_dialog_inherits_the_current_shows_roots(self, panel, monkeypatch):
        """Retyping a volume path is where project rows get typos."""
        seen: dict[str, str] = {}

        class Opening:
            DialogCode = QDialog.DialogCode
            summary = None
            project_name = ""

            def __init__(self, data_source, root="", publish_root="", parent=None):
                seen["root"] = root
                seen["publish_root"] = publish_root

            def exec(self):
                return QDialog.DialogCode.Rejected

        monkeypatch.setattr(project_panel_module, "NewProjectDialog", Opening)

        panel.new_project_btn.click()

        assert seen["root"] == panel._row.root
        assert seen["publish_root"] == panel._row.publish_root

    def test_a_created_project_is_announced_and_shown(self, panel, monkeypatch):
        class Accepting:
            DialogCode = QDialog.DialogCode
            project_name = "BrandNew"
            summary = ApplySummary(created=("/a", "/b"), env_written=2)

            def __init__(self, data_source, root="", publish_root="", parent=None):
                pass

            def exec(self):
                return QDialog.DialogCode.Accepted

        monkeypatch.setattr(project_panel_module, "NewProjectDialog", Accepting)
        announced: list[str] = []
        panel.project_created.connect(announced.append)

        panel.new_project_btn.click()

        assert announced == ["BrandNew"]
        assert panel.project == "BrandNew"          # the column follows the new show
        assert "Created BrandNew" in panel.repair_status.text()
        assert "2 override(s)" in panel.repair_status.text()
