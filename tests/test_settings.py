"""Tests for the three-column settings shell (plan T05).

Layout assertions pin the *policy* (fixed-width flanks) rather than transient
pixels — the splitter redistributes until the window is shown, and offscreen
geometry is not a contract we want to freeze.
"""

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QFrame

from launcher.ui.fakes import FakeSettingsDataSource
from launcher.ui.settings_window import (
    NAV_WIDTH,
    PANEL_MARGIN,
    PREVIEW_WIDTH,
    SettingsPanel,
    SettingsWindow,
)
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


class TestShell:
    def test_three_columns_with_fixed_flanks(self, window):
        assert window.splitter.count() == 3
        # D-D: nav and preview are pinned, the flexible column takes the rest.
        assert window.nav.minimumWidth() == window.nav.maximumWidth() == NAV_WIDTH
        assert (window.preview_panel.minimumWidth()
                == window.preview_panel.maximumWidth() == PREVIEW_WIDTH)
        assert NAV_WIDTH == 200 and PREVIEW_WIDTH == 420

    def test_nav_is_the_rightmost_column(self, window):
        """D-D (2026-10-25 revision 2): nav at the right edge, pages beside it.

        Two constraints from 默雷: the nav should sit where the mouse is (right
        edge), and the page column — the one whose content changes with the
        selection — should sit in the middle, next to the nav. The resolved
        preview takes the far column. Pin the order itself: that *is* the
        layout change.
        """
        assert window.splitter.widget(0) is window.preview_panel
        assert window.splitter.widget(1) is window.pages_panel
        assert window.splitter.widget(2) is window.nav

    def test_left_and_middle_columns_are_framed_like_the_nav(self, window):
        """All three columns must read as surfaces, not one grey field.

        The nav is a QListWidget and gets a hairline frame for free; the other
        two columns are wrapped in a QFrame that copies the same convention
        (StyledPanel + Plain shadow + Base background role), so nothing is
        hard-coded to a light theme.
        """
        for panel, content in (
            (window.preview_panel, window.preview_host),
            (window.pages_panel, window.stack),
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

    def test_resize_grows_only_the_page_column(self, window, qapp):
        """The pages column absorbs extra width; nav and preview stay pinned."""
        window.show()
        qapp.processEvents()
        before_nav = window.nav.width()
        before_preview = window.preview_panel.width()
        before_pages = window.pages_panel.width()

        window.resize(1400, 780)
        qapp.processEvents()

        assert window.nav.width() == before_nav == NAV_WIDTH
        assert window.preview_panel.width() == before_preview == PREVIEW_WIDTH
        assert window.pages_panel.width() > before_pages

    def test_nav_has_three_entries_and_pages(self, window):
        assert window.nav.count() == 3
        assert [window.nav.item(i).text() for i in range(3)] == [
            "Projects", "Environment", "Preflight",
        ]
        assert window.stack.count() == 3

    def test_nav_switches_page(self, window):
        window.nav.setCurrentRow(1)
        assert window.stack.currentIndex() == 1
        window.nav.setCurrentRow(2)
        assert window.stack.currentIndex() == 2

    def test_footer_initial_state(self, window):
        assert window.saved_label.text() == "Saved —"
        assert window.warnings_label.text() == "0 warnings"
        # T13: Copy .env is live — it copies the resolved rows.
        assert window.copy_env_btn.isEnabled() is True
        assert window.fixture_label.isHidden() is False   # visible once shown
        assert window.close_btn.text() == "Close"
        assert window.nav.currentRow() == 0

    def test_close_button_emits_finished(self, window, qapp):
        window.show()
        qapp.processEvents()
        spy = QSignalSpy(window.finished)
        window.close_btn.click()
        qapp.processEvents()
        assert spy.count() == 1
        assert window.isVisible() is False

    def test_footer_updates(self, window):
        window.set_warning_count(1)
        assert window.warnings_label.text() == "1 warning"
        window.set_warning_count(3)
        assert window.warnings_label.text() == "3 warnings"
        window.set_warning_count(0)
        assert window.warnings_label.text() == "0 warnings"
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
        assert win.nav.count() == 3
        assert win.stack.count() == 3
        assert win.is_fixture is True
        win.deleteLater()

    def test_empty_mode_still_builds(self, qapp):
        win = SettingsWindow(data_source=FakeSettingsDataSource("empty"))
        assert win.stack.count() == 3
        assert win.nav.count() == 3
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
