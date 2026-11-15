"""Main-window wiring tests (plan T06: modeless settings singleton).

The settings window applies changes immediately, so ``_open_settings`` no longer
runs a modal ``exec()`` loop nor reads paths back afterwards: it builds the
window once, raises it on later clicks, and refreshes the project tree through
``projects_changed``. These tests pin that behaviour, including the re-open path
(a closed window must be replaceable).

Note (P10): a ``QDialog`` that was never shown does not emit ``finished`` on
``close()``, so the close test shows the window first.
"""

import pytest
from PySide6.QtWidgets import QApplication

from launcher.ui.main_window import MainWindow
from launcher.ui.settings_window import SettingsWindow


@pytest.fixture
def window(qapp, monkeypatch):
    """A main window that never touches the DB or the YAML project list."""
    monkeypatch.setattr(
        "launcher.ui.widgets.project_tree.ProjectTreeWidget.load_projects",
        lambda self: None,
    )
    win = MainWindow()
    yield win
    if win._settings_win is not None:
        win._settings_win.close()
    win.close()
    win.deleteLater()


def _settings_windows():
    return [w for w in QApplication.topLevelWidgets()
            if isinstance(w, SettingsWindow)]


class TestSettingsWiring:
    def test_first_click_builds_a_modeless_window(self, window):
        window._open_settings()

        win = window._settings_win
        assert isinstance(win, SettingsWindow)
        # D-C: modeless — the main window stays usable behind it.
        assert win.isModal() is False
        assert win.isVisible() is True

    def test_second_click_reuses_the_open_window(self, window):
        window._open_settings()
        first = window._settings_win
        assert first is not None

        window._open_settings()

        assert window._settings_win is first
        assert len(_settings_windows()) == 1

    def test_closed_window_can_be_opened_again(self, window, qapp):
        window._open_settings()
        first = window._settings_win
        first.show()
        qapp.processEvents()

        first.close()
        qapp.processEvents()

        assert window._settings_win is None
        window._open_settings()
        assert window._settings_win is not None
        assert window._settings_win is not first

    def test_projects_changed_refreshes_the_tree_once(self, window, monkeypatch):
        calls = []
        # Patch before the connection is made: the signal stores a bound method.
        monkeypatch.setattr(window.project_tree, "load_projects",
                            lambda: calls.append(1))
        window._open_settings()

        assert calls == []
        window._settings_win.projects_changed.emit()
        assert calls == [1]

    def test_gear_button_opens_the_settings_window(self, window, qapp):
        window.settings_btn.click()
        qapp.processEvents()
        assert isinstance(window._settings_win, SettingsWindow)
