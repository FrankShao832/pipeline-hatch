"""Tests for the three-column settings shell (plan T05, revised 2026-10-26 r7).

Layout assertions pin the *policy* (two pinned columns around one flexible
column, no tab strip) rather than transient pixels — the splitter redistributes
until the window is shown, and offscreen geometry is not a contract we want to
freeze.
"""

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QFrame

from launcher.ui.fakes import FakeSettingsDataSource
from launcher.ui.viewmodels import SettingsContext
from launcher.ui.settings_window import (
    PANEL_MARGIN,
    PREFLIGHT_MIN_WIDTH,
    PREVIEW_MIN_WIDTH,
    PROJECT_WIDTH,
    SettingsPanel,
    SettingsWindow,
)
from launcher.ui.widgets.preflight_page import PreflightPage
from launcher.ui.widgets.project_panel import ProjectPanel
from launcher.ui.widgets.resolved_preview import ResolvedPreview
from launcher.ui.widgets.scope_badge import (
    BADGE_COLORS,
    badge_color,
    badge_html,
    badge_qss,
    badge_text,
)


@pytest.fixture
def window(qapp):
    win = SettingsWindow(data_source=FakeSettingsDataSource("rich"))
    yield win
    win.deleteLater()


class TestColumns:
    def test_three_columns_in_reading_order(self, window):
        """r7: resolved env | preflight | project — the tab strip is gone.

        Column order is a reading order, not a preference: the resolved
        environment is the answer (read first, far left), the project is the
        working surface (far right, next to the pointer), and preflight sits in
        the flexible middle because four columns of diagnostics need the width.
        """
        assert window.splitter.count() == 3
        assert window.splitter.widget(0) is window.preview_panel
        assert window.splitter.widget(1) is window.preflight_panel
        assert window.splitter.widget(2) is window.project_panel_box

    def test_two_tables_share_the_surplus_and_the_form_is_pinned(self, window):
        """The form-shaped column is pinned; the two tables both want width.

        Their long columns (resolved values, preflight messages) are the ones
        that elide first, so they split the surplus instead of one of them
        hoarding it while the other clips its most important column.
        """
        assert (window.project_panel_box.minimumWidth()
                == window.project_panel_box.maximumWidth() == PROJECT_WIDTH)
        assert window.preview_panel.minimumWidth() == PREVIEW_MIN_WIDTH
        assert window.preflight_panel.minimumWidth() == PREFLIGHT_MIN_WIDTH
        assert window.preview_panel.maximumWidth() > PREVIEW_MIN_WIDTH   # can grow
        assert PREVIEW_MIN_WIDTH >= 440
        assert PROJECT_WIDTH == 380

    def test_no_tab_strip_remains(self, window):
        """Switching pages hid two thirds of the evidence — there is none now."""
        assert not hasattr(window, "tab_bar")
        assert not hasattr(window, "stack")
        assert not hasattr(window, "pages_host")

    def test_all_three_columns_are_live_widgets(self, window):
        assert isinstance(window.resolved_preview, ResolvedPreview)
        assert isinstance(window.preflight_page, PreflightPage)
        assert isinstance(window.project_panel, ProjectPanel)

    def test_every_column_is_a_framed_surface(self, window):
        """Columns must read as surfaces, not one grey field.

        Each column is wrapped in a QFrame that copies the table viewport
        convention (StyledPanel + Plain shadow + Base background role), so
        nothing is hard-coded to a light theme.
        """
        for panel, content in (
            (window.preview_panel, window.preview_host),
            (window.preflight_panel, window.preflight_page),
            (window.project_panel_box, window.project_panel),
        ):
            assert isinstance(panel, QFrame)
            assert panel.frameShape() == QFrame.Shape.StyledPanel
            assert panel.frameShadow() == QFrame.Shadow.Plain
            assert panel.autoFillBackground() is True
            assert panel.backgroundRole() == QPalette.ColorRole.Base
            assert panel.layout().indexOf(content) == 0
            assert panel.layout().contentsMargins().left() == PANEL_MARGIN

    def test_frames_follow_the_system_palette(self, window):
        """No hard-coded colours: the fill must come from the palette."""
        base = window.palette().color(QPalette.ColorRole.Base)
        assert window.preview_panel.palette().color(
            window.preview_panel.backgroundRole()) == base

    def test_resize_grows_the_tables_and_not_the_form(self, window, qapp):
        """The pinned project column keeps its width; the tables take the rest."""
        window.show()
        qapp.processEvents()
        before_project = window.project_panel_box.width()
        before_preview = window.preview_panel.width()
        before_preflight = window.preflight_panel.width()

        window.resize(1500, 860)
        qapp.processEvents()

        assert window.project_panel_box.width() == before_project == PROJECT_WIDTH
        assert window.preview_panel.width() > before_preview
        assert window.preflight_panel.width() > before_preflight

    def test_context_reaches_every_column(self, window):
        """One context, three renderers: no column may keep showing CyberPunk."""
        index = window.project_combo.findData("DragonLand")
        window.project_combo.setCurrentIndex(index)
        assert window.resolved_preview.context.project == "DragonLand"
        assert window.preflight_page.scope_label.text().startswith("scope: DragonLand")
        assert window.project_panel.project == "DragonLand"

    def test_preflight_drives_the_footer(self, window):
        """One source of truth: the Preflight column publishes the numbers."""
        errors, warnings = window.preflight_page.counts()
        assert (errors, warnings) == (0, 1)          # rich fixture ships one warn
        assert window.warnings_label.text() == "1 warning"

    def test_footer_initial_state(self, window):
        assert window.saved_label.text() == "Saved —"
        # Not hard-coded: the counter mirrors the Preflight column's findings.
        assert window.warnings_label.text() == "1 warning"
        # T13: Copy .env is live — it copies the resolved rows.
        assert window.copy_env_btn.isEnabled() is True
        assert window.fixture_label.isHidden() is False   # visible once shown
        assert window.close_btn.text() == "Close"

    def test_close_button_emits_finished(self, window, qapp):
        window.show()
        qapp.processEvents()
        spy = QSignalSpy(window.finished)
        window.close_btn.click()
        qapp.processEvents()
        assert spy.count() == 1
        assert window.isVisible() is False

    def test_footer_updates(self, window):
        window.set_issue_counts(0, 1)
        assert window.warnings_label.text() == "1 warning"
        window.set_issue_counts(2, 3)
        assert window.warnings_label.text() == "2 errors · 3 warnings"
        window.set_issue_counts(1, 0)
        assert window.warnings_label.text() == "1 error"
        window.set_issue_counts(0, 0)
        assert window.warnings_label.text() == "0 issues"
        window.set_saved_now("12:04")
        assert window.saved_label.text() == "Saved 12:04"

    def test_real_data_source_hides_fixture_badge(self, qapp):
        class _Stub:
            def projects(self):
                return []

        win = SettingsWindow(data_source=_Stub())  # type: ignore[arg-type]
        assert win.is_fixture is False
        assert win.fixture_label.isHidden() is True
        win.deleteLater()


class TestDegradedModes:
    def test_errors_mode_still_builds(self, qapp):
        """``projects()`` raises in this fixture: the shell must still build."""
        win = SettingsWindow(data_source=FakeSettingsDataSource("errors"))
        assert win.splitter.count() == 3
        assert win.is_fixture is True
        assert "Could not load" in win.project_panel.verdict_label.text()
        win.deleteLater()

    def test_empty_mode_still_builds(self, qapp):
        win = SettingsWindow(data_source=FakeSettingsDataSource("empty"))
        assert win.splitter.count() == 3
        assert win.resolved_preview.rows == []
        assert "No project selected" in win.project_panel.verdict_label.text()
        win.deleteLater()

    def test_no_arguments_uses_fixture(self, qapp):
        win = SettingsWindow()
        assert win.is_fixture is True
        win.deleteLater()


class TestTransitionalCompat:
    def test_settings_panel_alias(self, qapp):
        assert SettingsPanel is SettingsWindow
        win = SettingsPanel()
        win.deleteLater()


class TestScopeBadge:
    def test_five_scopes_have_colours(self):
        assert set(BADGE_COLORS) == {"derived", "global", "show", "dcc", "department"}
        assert badge_color("global").startswith("#")
        assert badge_color("unknown").startswith("#")

    def test_badge_text_and_html(self):
        assert badge_text("global") == "[global]"
        assert badge_text("show", "CyberPunk") == "[show:CyberPunk]"
        html = badge_html("show", "CyberPunk")
        assert "[show:CyberPunk]" in html
        assert BADGE_COLORS["show"] in html
        assert badge_qss("dcc") == f"color: {BADGE_COLORS['dcc']};"


class TestContextBar:
    """The bar is a *snapshot*: main window when it has a selection, else a default."""

    def test_default_context_when_nothing_is_selected(self, window):
        # First *usable* project: enabled and scaffolded (CyberPunk), not row 0
        # by accident — on a real install row 0 can be disabled or half-built.
        assert window.project_combo.currentData() == "CyberPunk"
        assert window.dcc_combo.currentData() == "maya"
        # Department is never guessed.
        assert window.department_combo.currentData() == ""
        assert window.department_combo.currentText() == "— no department —"

    def test_context_is_taken_from_the_main_window(self, qapp):
        win = SettingsWindow(
            data_source=FakeSettingsDataSource("rich"),
            context=SettingsContext(project="DragonLand", seq="seq001", shot="sh010",
                                    dcc="houdini", department="lighting"),
        )
        assert win.project_combo.currentData() == "DragonLand"
        assert win.department_combo.currentData() == "lighting"
        assert win.dcc_combo.currentData() == "houdini"
        assert win.scope_chip.text() == "▸ seq001/sh010"
        win.deleteLater()

    def test_unknown_project_falls_back_to_the_default(self, qapp):
        win = SettingsWindow(data_source=FakeSettingsDataSource("rich"),
                             context=SettingsContext(project="DoesNotExist"))
        assert win.project_combo.currentData() == "CyberPunk"
        win.deleteLater()

    def test_unknown_department_is_left_unset(self, qapp):
        win = SettingsWindow(data_source=FakeSettingsDataSource("rich"),
                             context=SettingsContext(project="CyberPunk",
                                                     department="not-a-department"))
        assert win.department_combo.currentData() == ""
        assert win.department_combo.currentText() == "— no department —"
        win.deleteLater()

    def test_scope_chip_says_so_when_no_shot_is_known(self, window):
        assert window.scope_chip.text() == "▸ no shot"

    def test_no_selection_does_not_leak_back_to_the_main_window(self, window):
        """Editing here is local: the bar never writes to the provider."""
        window.project_combo.setCurrentIndex(
            window.project_combo.findData("SpaceOdyssey"))
        assert window.context.project == "SpaceOdyssey"


class TestEnvEditWiring:
    """A value edited in the left column becomes a show override (card C5)."""

    def test_editing_saves_a_show_scoped_row_for_the_context_project(self, qapp):
        ds = FakeSettingsDataSource("rich")
        win = SettingsWindow(
            data_source=ds,
            context=SettingsContext(project="DragonLand", dcc="nuke",
                                    department="comp"),
        )

        win.resolved_preview.env_edited.emit("ASSET_ROOT", "/tmp/edited")

        saved = [row for row in ds._env if row.name == "ASSET_ROOT"]
        assert saved, "the edit never reached the data source"
        assert saved[0].scope == "show"
        assert saved[0].scope_key == "DragonLand"
        assert saved[0].value == "/tmp/edited"
        win.deleteLater()

    def test_a_successful_edit_stamps_the_footer(self, window):
        assert window.saved_label.text() == "Saved —"

        window.resolved_preview.env_edited.emit("ASSET_ROOT", "/tmp/edited")

        assert window.saved_label.text().startswith("Saved just now")


class TestRevert:
    """The footer's Revert takes back the last write (card C6).

    The button's *state* is part of the contract: a Revert that looks live and
    then reports "nothing to revert" is worse than a disabled one that explains
    why, so the enabled flag is asserted alongside the behaviour.
    """

    def test_revert_is_disabled_before_anything_is_written(self, window):
        assert window.revert_btn.isEnabled() is False
        assert "No backup yet" in window.revert_btn.toolTip()

    def test_a_write_enables_revert(self, window):
        window.resolved_preview.env_edited.emit("ASSET_ROOT", "/tmp/edited")

        assert window.revert_btn.isEnabled() is True
        assert "Restore" in window.revert_btn.toolTip()

    def test_reverting_restores_the_rows_from_before_the_edit(self, qapp):
        ds = FakeSettingsDataSource("rich")
        win = SettingsWindow(
            data_source=ds,
            context=SettingsContext(project="DragonLand", dcc="nuke",
                                    department="comp"),
        )
        before = [(r.name, r.value, r.scope, r.scope_key) for r in ds.env_rows()]

        win.resolved_preview.env_edited.emit("ASSET_ROOT", "/tmp/edited")
        win.revert_btn.click()

        after = [(r.name, r.value, r.scope, r.scope_key) for r in ds.env_rows()]
        assert after == before
        assert win.saved_label.text().startswith("Saved reverted")
        win.deleteLater()

    def test_revert_stays_available_after_use(self, window):
        """Restoring is idempotent — the backup is copied back, not consumed."""
        window.resolved_preview.env_edited.emit("ASSET_ROOT", "/tmp/edited")

        window.revert_btn.click()

        assert window.revert_btn.isEnabled() is True


class TestNewProjectWiring:
    """A created project becomes the window's context (card C7)."""

    def test_the_bar_moves_to_the_new_project(self, window):
        names_before = [window.project_combo.itemData(i)
                        for i in range(window.project_combo.count())]

        window.project_panel.project_created.emit("BrandNew")

        assert "BrandNew" not in names_before
        assert window.project_combo.currentData() == "BrandNew"
        assert window.context.project == "BrandNew"

    def test_all_three_columns_follow_the_new_context(self, window):
        window.project_panel.project_created.emit("BrandNew")

        assert window.project_panel.project == "BrandNew"
        assert window.context.project == "BrandNew"
        assert window.saved_label.text().startswith("Saved just now · created BrandNew")

    def test_the_main_window_is_told_to_reload_its_tree(self, window):
        spy = QSignalSpy(window.projects_changed)

        window.project_panel.project_created.emit("BrandNew")

        assert spy.count() == 1
