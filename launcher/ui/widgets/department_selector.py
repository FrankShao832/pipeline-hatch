"""Department selector widget — populated from YAML config.

Vocabulary (docs/VOCABULARY.md): the *department* (fx / comp / lighting) owns the
work — it is the data axis behind the shot workdir, the DEPARTMENT env var and
the publish path. The selected DCC (see ``role_selector``) is only the
application used to open that work. They are separate axes; this widget carries
the department one, so it must not be called "task".
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox


class DepartmentSelectorWidget(QComboBox):
    """Department selection (fx/comp/lighting).

    The first item is the placeholder ``Select your department`` with an empty
    value, so the launcher starts with *no* department: the artist must say
    whose work they are opening. Stores the department token as itemData.
    """

    PLACEHOLDER = "Select your department"

    department_changed = Signal(str)

    def __init__(self, parent=None):
        """Initialize the department selector.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        # Wide enough for the placeholder text, which is the longest label.
        self.setFixedWidth(200)
        self._populate()
        self.currentIndexChanged.connect(self._on_selection_changed)

    def _populate(self) -> None:
        """Load departments from YAML config, with fallback defaults."""
        try:
            from launcher.core.config_manager import config_manager
            pipeline = (config_manager.get_dcc_config() or {}).get("pipeline", {}) or {}
            depts = pipeline.get("departments") or []
        except Exception:
            depts = []
        if not depts:
            depts = ["fx", "comp", "lighting"]
        self.addItem(self.PLACEHOLDER)
        for d in depts:
            self.addItem(d, userData=d)
        self.setCurrentIndex(0)

    def current_department(self) -> str:
        """Return the selected department token ('' while the placeholder shows)."""
        if self.currentIndex() <= 0:
            return ""
        data = self.itemData(self.currentIndex())
        return str(data) if data else self.currentText()

    def _on_selection_changed(self, index: int) -> None:
        """Emit department_changed — '' means the selection was cleared."""
        self.department_changed.emit(self.current_department())
