"""Task (department) selector widget — populated from YAML config."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox


class TaskSelectorWidget(QComboBox):
    """Task/department selection (fx/comp/lighting).

    Stores the department token as itemData; defaults to the first configured
    department so the launcher always has a valid task context.
    """

    task_changed = Signal(str)

    def __init__(self, parent=None):
        """Initialize the task selector.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setFixedWidth(150)
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
        for d in depts:
            self.addItem(d, userData=d)
        self.setCurrentIndex(0)

    def current_task(self) -> str:
        """Return the selected department token ('' when nothing selected)."""
        idx = self.currentIndex()
        if idx < 0:
            return ""
        data = self.itemData(idx)
        return data if data else self.currentText()

    def _on_selection_changed(self, index: int) -> None:
        """Emit task_changed with the selected department token."""
        if index >= 0:
            task = self.current_task()
            if task:
                self.task_changed.emit(task)
