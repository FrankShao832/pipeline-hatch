"""Role selector widget — dynamically populated from YAML config."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox


class RoleSelectorWidget(QComboBox):
    """Role selection dropdown, dynamically populated from YAML config.

    Stores the role key (e.g. 'maya') as itemData so consumers can retrieve
    the correct lookup key regardless of display name.

    Signals:
        role_changed(str): Emitted when a role is selected, passes the role key.
    """

    role_changed = Signal(str)

    def __init__(self, parent=None):
        """Initialize the role selector.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setEditable(False)
        self.setFixedWidth(300)
        self._populate()
        self.currentIndexChanged.connect(self._on_selection_changed)

    def _populate(self) -> None:
        """Load DCC roles from YAML config, with fallback defaults."""
        try:
            from launcher.core.config_manager import config_manager

            dcc_config = config_manager.get_dcc_config()
            dcc_list = dcc_config.get("dcc", {})
            self.addItem('Select your role...')
            for role_key, role_config in dcc_list.items():
                display_name = role_config.get("name", role_key.title())
                self.addItem(display_name, userData=role_key)
        except Exception:
            self.addItems([
                'Select your role...',
                'Maya',
                'Houdini',
                'Nuke'
            ])

    def current_role(self) -> str | None:
        """Get the currently selected role key.

        Returns:
            Role key string (e.g. 'maya', 'houdini'), or None if
            the placeholder item 'Select your role...' is selected.
        """
        if self.currentIndex() <= 0:
            return None
        role = self.itemData(self.currentIndex())
        if role:
            return role
        return self.currentText().lower()

    def _on_selection_changed(self, index: int) -> None:
        """Emit role_changed signal with the selected role key.

        Args:
            index: The new combo box index (0 = placeholder).
        """
        if index > 0:
            role = self.current_role()
            if role:
                self.role_changed.emit(role)
