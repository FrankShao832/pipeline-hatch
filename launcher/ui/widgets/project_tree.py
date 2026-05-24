"""Project tree widget — populated from YAML config with default project support."""

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QAction, QCursor, QFont
from PySide6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem


# QSettings identifiers
_SETTINGS_ORG = "PipelineDevs"
_SETTINGS_APP = "PipelineLauncher"
_SETTINGS_KEY = "default_project"

# Prefix for default project display
_STAR = "\u2605 "  # ★


class ProjectTreeWidget(QTreeWidget):
    """Project tree browser, populated from YAML config.

    Supports setting a default project via right-click context menu.
    The default project is:
    - Moved to the top of the list
    - Marked with a ★ prefix and bold font
    - Visually selected and auto-scrolled into view
    - Persisted via QSettings, auto-selected on next launch

    Stores the project root path as itemData on each tree item.

    Signals:
        project_selected(name: str, root_path: str): Emitted when a
            project item is clicked or auto-selected on startup.
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
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    # ---- Public API ----

    def load_projects(self) -> None:
        """Load and display projects from the YAML configuration.

        Only projects with ``enabled: true`` (or missing enabled field)
        are displayed. After loading, applies visual markers for the
        default project and auto-selects it.
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

            # Apply default project visuals, reorder, and auto-select
            self._refresh_default_marker()
            self._select_default_project()
        except Exception as e:
            from launcher.utils.logger import logger

            logger.error(f"Failed to load projects: {e}")

    # ---- Right-click context menu ----

    def _show_context_menu(self, pos) -> None:
        """Show right-click context menu for the clicked item.

        Args:
            pos: Mouse position relative to the widget.
        """
        item = self.itemAt(pos)
        if item is None:
            return

        menu = QMenu(self)
        display = item.text(0)
        name = display[len(_STAR):] if display.startswith(_STAR) else display
        default_name = self._get_default_name()
        is_default = (name == default_name)

        if is_default:
            action = QAction("\u2715 Clear default project", self)
            action.triggered.connect(lambda: self._clear_default_project(item))
        else:
            action = QAction("\u2605 Set as default project", self)
            action.triggered.connect(lambda: self._set_default_project(item))

        menu.addAction(action)
        menu.exec(QCursor.pos())

    def _set_default_project(self, item: QTreeWidgetItem) -> None:
        """Mark the given item as the default project.

        Saves the project name to QSettings, refreshes visual
        markers, reorders the tree so the default is at top,
        and visually selects it.

        Args:
            item: The tree item to set as default.
        """
        display = item.text(0)
        name = display[len(_STAR):] if display.startswith(_STAR) else display
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        settings.setValue(_SETTINGS_KEY, name)

        # Refresh markers and reorder
        self._refresh_default_marker()

        # Visually select the newly-set default (now at index 0)
        default_item = self.topLevelItem(0)
        if default_item:
            self.setCurrentItem(default_item)
            self.scrollToItem(default_item)
            # Emit signal so downstream trees (seq, shot, file) update
            root = default_item.data(0, Qt.ItemDataRole.UserRole) or ""
            self.project_selected.emit(name, root)

    def _clear_default_project(self, item: QTreeWidgetItem) -> None:
        """Remove default project status.

        Clears the stored default project name from QSettings and
        refreshes visual markers.

        Args:
            item: The current default tree item (unused, but kept for
                  consistent lambda signature).
        """
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        settings.remove(_SETTINGS_KEY)
        self._refresh_default_marker()

    # ---- Visual markers & reorder ----

    @staticmethod
    def _get_default_name() -> str:
        """Read the stored default project name from QSettings.

        Returns:
            Project name string, or empty string if none set.
        """
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        return settings.value(_SETTINGS_KEY, "")

    def _refresh_default_marker(self) -> None:
        """Update ★ prefix, bold font, and reorder items.

        The default project (if any) is moved to index 0 (top of the
        tree) with a ★ prefix and bold font. All other items are
        restored to plain text without the prefix.
        """
        default_name = self._get_default_name()

        # --- Pass 1: Update visual markers (★ prefix + bold) ---
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            name = item.text(0)

            # Strip any existing ★ prefix for comparison
            clean = name[len(_STAR):] if name.startswith(_STAR) else name
            item.setText(0, clean)

            if clean == default_name:
                item.setText(0, f"{_STAR}{clean}")
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
            else:
                font = item.font(0)
                font.setBold(False)
                item.setFont(0, font)

        # --- Pass 2: Move default project to top ---
        if default_name:
            for i in range(self.topLevelItemCount()):
                item = self.topLevelItem(i)
                display = item.text(0)
                clean = display[len(_STAR):] if display.startswith(_STAR) else display
                if clean == default_name:
                    reorder_item = self.takeTopLevelItem(i)
                    self.insertTopLevelItem(0, reorder_item)
                    break

    def _select_default_project(self) -> None:
        """Visually select the default project if one is stored.

        Called after load_projects(). Finds the default project
        (already at index 0 after _refresh_default_marker()),
        highlights it in the tree, scrolls it into view, and
        emits the project_selected signal.
        """
        default_name = self._get_default_name()
        if not default_name:
            return

        # Default is at index 0 after _refresh_default_marker()
        if self.topLevelItemCount() == 0:
            return

        item = self.topLevelItem(0)
        display = item.text(0)
        clean = display[len(_STAR):] if display.startswith(_STAR) else display
        if clean == default_name:
            self.setCurrentItem(item)
            self.scrollToItem(item)
            root = item.data(0, Qt.ItemDataRole.UserRole) or ""
            self.project_selected.emit(default_name, root)

    # ---- Item click ----

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Emit project_selected signal with project name and root path.

        Strips the ★ prefix before emitting so downstream code always
        receives the clean project name.

        Args:
            item: The clicked tree item.
            column: Column index (unused).
        """
        display = item.text(0)
        name = display[len(_STAR):] if display.startswith(_STAR) else display
        root = item.data(0, Qt.ItemDataRole.UserRole) or ""
        self.project_selected.emit(name, root)
