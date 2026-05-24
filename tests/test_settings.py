"""Tests for SettingsPanel dialog."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from launcher.ui.settings_window import SettingsPanel


class TestSettingsPanel:
    """Test suite for SettingsPanel dialog."""

    def test_initial_display(self, qtbot):
        """Both path labels show default paths from config on initial open."""
        panel = SettingsPanel()
        qtbot.addWidget(panel)

        # Should be pre-filled from first enabled project, not "None"
        assert panel.root_path_value.text() != ""
        assert panel.publish_root_value.text() != ""

    def test_ok_cancel_buttons(self, qtbot):
        """OK button triggers accept, Cancel triggers reject."""
        def _find_by_text(widget, text: str):
            for btn in widget.findChildren(QPushButton):
                if btn.text() == text:
                    return btn
            return None

        # OK → accept signal
        panel = SettingsPanel()
        qtbot.addWidget(panel)
        ok_btn = _find_by_text(panel, "OK")
        assert ok_btn is not None
        with qtbot.waitSignal(panel.accepted, timeout=500):
            qtbot.mouseClick(ok_btn, Qt.MouseButton.LeftButton)

        # Cancel → reject signal
        panel2 = SettingsPanel()
        qtbot.addWidget(panel2)
        cancel_btn = _find_by_text(panel2, "Cancel")
        assert cancel_btn is not None
        with qtbot.waitSignal(panel2.rejected, timeout=500):
            qtbot.mouseClick(cancel_btn, Qt.MouseButton.LeftButton)

    def test_browse_buttons_exist(self, qtbot):
        """Two Browse buttons exist and are clickable."""
        panel = SettingsPanel()
        qtbot.addWidget(panel)

        browse_buttons = [btn for btn in panel.findChildren(QPushButton)
                          if btn.text() == "Browse..."]
        assert len(browse_buttons) == 2

        # Verify both buttons are enabled
        for btn in browse_buttons:
            assert btn.isEnabled()
