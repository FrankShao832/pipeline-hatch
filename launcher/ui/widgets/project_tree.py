"""Project tree widget — populated from YAML config."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem


class ProjectTreeWidget(QTreeWidget):
    """Project tree browser, populated from YAML config.

    Displays enabled projects from the pipeline configuration file.
    Stores the project root path as itemData on each tree item.

    Signals:
        project_selected(name: str, root_path: str): Emitted when a
            project item is clicked.
    """

    project_selected = Signal(str, str)

    def __init__(self, parent=None):
        """Initialize the project tree.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.itemClicked.connect(self._on_item_clicked)

    def load_projects(self) -> None:
        """Load and display projects from the YAML configuration.

        Only projects with ``enabled: true`` (or missing enabled field)
        are displayed. Logs a warning on failure.
        """
        try:
            from launcher.core.config_manager import config_manager

            projects = config_manager.get_project_list()
            self.clear()
            for proj in projects:
                if proj.get("enabled", True):
                    item = QTreeWidgetItem(self)
                    item.setText(0, proj["name"])
                    item.setData(0, Qt.ItemDataRole.UserRole, proj.get("root", ""))
        except Exception as e:
            from launcher.utils.logger import logger

            logger.error(f"Failed to load projects: {e}")

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Emit project_selected signal with project name and root path.

        Args:
            item: The clicked tree item.
            column: Column index (unused).
        """
        name = item.text(0)
        root = item.data(0, Qt.ItemDataRole.UserRole) or ""
        self.project_selected.emit(name, root)
