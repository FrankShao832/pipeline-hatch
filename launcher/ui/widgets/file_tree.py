"""File tree widget — lists files in a directory."""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem


class FileTreeWidget(QTreeWidget):
    """File browser for a given directory path.

    Lists non-hidden files sorted alphabetically.
    Accepts a shared ``QFileSystemWatcher`` via ``set_file_watcher()``.
    """

    def __init__(self, parent=None):
        """Initialize the file tree.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setHeaderHidden(True)
        self._watcher = None
        self._watched_paths: set[str] = set()

    def set_file_watcher(self, watcher) -> None:
        """Attach a shared ``QFileSystemWatcher`` for directory monitoring.

        Args:
            watcher: A ``QFileSystemWatcher`` instance.
        """
        self._watcher = watcher

    def load_for_path(self, path: str) -> None:
        """List files in the given directory, sorted alphabetically.

        Hidden files (names starting with ``.``) are excluded.

        Args:
            path: Directory path to list files from.
        """
        self._watch(path)
        self.clear()

        if not os.path.isdir(path):
            return

        for filename in sorted(os.listdir(path)):
            filepath = os.path.join(path, filename)
            if os.path.isfile(filepath) and not filename.startswith('.'):
                item = QTreeWidgetItem(self)
                item.setText(0, filename)

        self.sortItems(0, Qt.SortOrder.AscendingOrder)

    def selected_file_path(self) -> Optional[str]:
        """Return the full path of the currently selected file.

        Returns:
            The file path string, or None if no item is selected.
        """
        item = self.currentItem()
        if item:
            return item.text(0)
        return None

    def _watch(self, path: str) -> None:
        """Add a path to the file watcher, avoiding duplicates.

        Args:
            path: Directory path to watch.
        """
        if self._watcher is not None and path not in self._watched_paths:
            self._watcher.addPath(path)
            self._watched_paths.add(path)
