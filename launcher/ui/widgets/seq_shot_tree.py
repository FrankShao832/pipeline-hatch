"""Sequence and shot tree widget — populated from filesystem."""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem


class SeqShotTreeWidget(QTreeWidget):
    """Sequence and shot tree browser, populated from filesystem.

    Scans a project directory for seq/shot folder hierarchies.
    Accepts a shared ``QFileSystemWatcher`` via ``set_file_watcher()``.

    Signals:
        shot_selected(seq: str, shot: str): Emitted when a shot item
            (leaf node) is clicked.
    """

    shot_selected = Signal(str, str)

    def __init__(self, parent=None):
        """Initialize the sequence/shot tree.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.itemClicked.connect(self._on_item_clicked)
        self._watcher = None
        self._watched_paths: set[str] = set()

    def set_file_watcher(self, watcher) -> None:
        """Attach a shared ``QFileSystemWatcher`` for directory monitoring.

        Args:
            watcher: A ``QFileSystemWatcher`` instance.
        """
        self._watcher = watcher

    def load_for_project(self, project_root: str, project_name: str) -> None:
        """Scan filesystem and populate the tree from the given project.

        Args:
            project_root: Root path of the project.
            project_name: Name of the project directory.
        """
        project_path = os.path.join(project_root, project_name)
        self._watch(project_path)
        self.clear()

        if not os.path.isdir(project_path):
            return

        seq_list = sorted([
            p for p in os.listdir(project_path)
            if os.path.isdir(os.path.join(project_path, p))
        ])

        for seq in seq_list:
            seq_item = QTreeWidgetItem(self)
            seq_item.setText(0, seq)
            shot_path = os.path.join(project_path, seq)
            self._watch(shot_path)

            for shot in sorted(os.listdir(shot_path)):
                if os.path.isdir(os.path.join(shot_path, shot)):
                    shot_item = QTreeWidgetItem(seq_item)
                    shot_item.setText(0, shot)

        self.sortItems(0, Qt.SortOrder.AscendingOrder)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Emit ``shot_selected`` if a shot (leaf node) is clicked.

        Args:
            item: The clicked tree item.
            column: Column index (unused).
        """
        parent = item.parent()
        if parent:
            self.shot_selected.emit(parent.text(0), item.text(0))

    def _watch(self, path: str) -> None:
        """Add a path to the file watcher, avoiding duplicates.

        Args:
            path: Directory path to watch.
        """
        if self._watcher is not None and path not in self._watched_paths:
            self._watcher.addPath(path)
            self._watched_paths.add(path)
