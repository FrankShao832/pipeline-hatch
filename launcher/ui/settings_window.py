"""Settings dialog for pipeline launcher with database project management."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QPushButton, QHBoxLayout, QLabel, QVBoxLayout,
    QFileDialog, QTreeWidget, QTreeWidgetItem, QHeaderView,
    QLineEdit, QFormLayout, QGroupBox, QMessageBox, QWidget,
)

from launcher.database.repository import ProjectRepo


class ProjectEditDialog(QDialog):
    """Simple dialog for creating or editing a project."""

    def __init__(self, parent=None, project: Optional[dict] = None):
        """Initialize the dialog.

        Args:
            parent: Optional parent widget.
            project: Existing project dict for editing, or None for new project.
        """
        super().__init__(parent)
        self.setWindowTitle("Edit Project" if project else "New Project")
        self.setMinimumWidth(400)
        self._project = project
        self._setup_ui()

    def _setup_ui(self):
        """Build the form layout."""
        self.name_edit = QLineEdit()
        self.root_edit = QLineEdit()
        self.publish_edit = QLineEdit()

        root_btn = QPushButton("Browse...")
        root_btn.clicked.connect(lambda: self._browse(self.root_edit))
        publish_btn = QPushButton("Browse...")
        publish_btn.clicked.connect(lambda: self._browse(self.publish_edit))

        # Pre-fill if editing
        if self._project:
            self.name_edit.setText(self._project.get("name", ""))
            self.root_edit.setText(self._project.get("root_path", ""))
            self.publish_edit.setText(self._project.get("publish_root", ""))
            self.name_edit.setEnabled(False)  # Don't allow renaming

        form = QFormLayout()
        form.addRow("Name:", self.name_edit)

        root_row = QHBoxLayout()
        root_row.addWidget(self.root_edit)
        root_row.addWidget(root_btn)
        form.addRow("Root Path:", root_row)

        publish_row = QHBoxLayout()
        publish_row.addWidget(self.publish_edit)
        publish_row.addWidget(publish_btn)
        form.addRow("Publish Root:", publish_row)

        # Buttons
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)

        main_layout = QVBoxLayout()
        main_layout.addLayout(form)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    @staticmethod
    def _browse(line_edit: QLineEdit) -> None:
        """Open directory browser and set text on line edit."""
        path = QFileDialog.getExistingDirectory()
        if path:
            line_edit.setText(path)

    def get_data(self) -> dict:
        """Return form data as a dict."""
        return {
            "name": self.name_edit.text().strip(),
            "root_path": self.root_edit.text().strip(),
            "publish_root": self.publish_edit.text().strip(),
        }


class SettingsPanel(QDialog):
    """Settings dialog for pipeline configuration.

    When a database session is provided, adds project management
    (list / add / edit / delete) backed by ProjectRepo.

    Signals:
        projects_changed: Emitted after any project CRUD operation so
                          the main window can refresh its project tree.
    """

    projects_changed = Signal()

    def __init__(self, db_session=None, current_user=None, parent=None):
        """Initialize the settings panel.

        Args:
            db_session: Optional SQLAlchemy session for DB project CRUD.
            current_user: Optional User object for permission checks.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._session = db_session
        self._current_user = current_user
        self.setWindowTitle("Settings")
        self.resize(650, 500)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build the full settings UI."""
        main_layout = QVBoxLayout()

        # -- Section 1: Path overrides (always visible) --
        path_group = QGroupBox("Path Overrides")
        path_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 13px; }"
            "QGroupBox::title { padding: 0 4px; }"
        )
        path_layout = QVBoxLayout()

        self.root_path_label = QLabel("Projects Root:")
        self.root_path_value = QLabel("None")
        root_row = QHBoxLayout()
        root_row.addWidget(self.root_path_label)
        root_row.addWidget(self.root_path_value, stretch=1)
        self.root_btn = QPushButton("Browse...")

        self.publish_root_label = QLabel("Publish Root:")
        self.publish_root_value = QLabel("None")
        publish_row = QHBoxLayout()
        publish_row.addWidget(self.publish_root_label)
        publish_row.addWidget(self.publish_root_value, stretch=1)
        self.publish_root_btn = QPushButton("Browse...")

        path_layout.addLayout(root_row)
        path_layout.addWidget(self.root_btn)
        path_layout.addLayout(publish_row)
        path_layout.addWidget(self.publish_root_btn)
        path_group.setLayout(path_layout)
        main_layout.addWidget(path_group)

        # Pre-fill default paths from first enabled project in config
        self._load_default_paths()

        # -- Section 2: Database project management (if session available) --
        if self._session is not None:
            db_group = QGroupBox("Project Manager (Database)")
            db_group.setStyleSheet(
                "QGroupBox { font-weight: bold; font-size: 13px; }"
                "QGroupBox::title { padding: 0 4px; }"
            )
            db_layout = QVBoxLayout()

            # Project tree
            self.project_tree = QTreeWidget()
            self.project_tree.setHeaderHidden(False)
            self.project_tree.setColumnCount(4)
            self.project_tree.setHeaderLabels(["Name", "Root Path", "Publish Root", "Enabled"])
            self.project_tree.header().setStretchLastSection(False)
            self.project_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            self.project_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            self.project_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            self.project_tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            self.project_tree.setRootIsDecorated(False)

            # Buttons
            btn_row = QHBoxLayout()
            add_btn = QPushButton("Add Project")
            add_btn.clicked.connect(self._add_project)
            edit_btn = QPushButton("Edit")
            edit_btn.clicked.connect(self._edit_project)
            delete_btn = QPushButton("Delete")
            delete_btn.clicked.connect(self._delete_project)

            btn_row.addStretch()
            btn_row.addWidget(add_btn)
            btn_row.addWidget(edit_btn)
            btn_row.addWidget(delete_btn)

            db_layout.addWidget(self.project_tree)
            db_layout.addLayout(btn_row)
            db_group.setLayout(db_layout)
            main_layout.addWidget(db_group)

            # Load projects
            self._load_projects()

        # -- Bottom buttons --
        main_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        main_layout.addLayout(btn_layout)

        self.setLayout(main_layout)
        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect button signals."""
        self.root_btn.clicked.connect(self._set_root_path)
        self.publish_root_btn.clicked.connect(self._set_publish_root_path)

    def _load_default_paths(self) -> None:
        """Pre-fill root/publish paths from the first enabled project in config.

        Tries DB first (if connected), then falls back to YAML config.
        """
        root = ""
        publish = ""
        if self._session is not None:
            try:
                from launcher.database.repository import ProjectRepo
                repo = ProjectRepo(self._session)
                first = repo.list_enabled()
                if first:
                    root = first[0].root_path
                    publish = first[0].publish_root
            except Exception:
                pass
        if not root:
            try:
                from launcher.core.config_manager import config_manager
                projects = config_manager.get_project_list()
                for proj in projects:
                    if proj.get("enabled", True):
                        root = proj.get("root", "")
                        publish = proj.get("publish_root", "")
                        break
            except Exception:
                pass
        if root:
            self.root_path_value.setText(root)
        if publish:
            self.publish_root_value.setText(publish)

    def _set_root_path(self) -> None:
        """Open file dialog to select project root directory."""
        root_path = QFileDialog.getExistingDirectory(self, "Select Projects Root")
        if root_path:
            self.root_path_value.setText(root_path)

    def _set_publish_root_path(self) -> None:
        """Open file dialog to select publish root directory."""
        publish_root_path = QFileDialog.getExistingDirectory(self, "Select Publish Root")
        if publish_root_path:
            self.publish_root_value.setText(publish_root_path)

    # -- Database project CRUD ------------------------------------------------

    def _load_projects(self) -> None:
        """Load projects from DB and populate the tree."""
        if not self._session:
            return
        self.project_tree.clear()
        repo = ProjectRepo(self._session)
        for proj in repo.list_projects():
            item = QTreeWidgetItem(self.project_tree)
            item.setText(0, proj.name)
            item.setText(1, proj.root_path)
            item.setText(2, proj.publish_root)
            item.setText(3, "Yes" if proj.enabled else "No")
            item.setData(0, Qt.ItemDataRole.UserRole, proj.id)

    def _add_project(self) -> None:
        """Open dialog to create a new project in DB."""
        if not self._session:
            return
        dialog = ProjectEditDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if not data["name"]:
                QMessageBox.warning(self, "Validation", "Project name is required.")
                return
            repo = ProjectRepo(self._session)
            try:
                repo.create(
                    name=data["name"],
                    root_path=data["root_path"],
                    publish_root=data["publish_root"],
                    created_by=getattr(self._current_user, "username", None),
                )
                self._load_projects()
                self.projects_changed.emit()
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"Failed to create project:\n{exc}")

    def _edit_project(self) -> None:
        """Open dialog to edit the selected project."""
        if not self._session:
            return
        item = self.project_tree.currentItem()
        if not item:
            QMessageBox.information(self, "Info", "Please select a project to edit.")
            return

        project_id = item.data(0, Qt.ItemDataRole.UserRole)
        repo = ProjectRepo(self._session)
        proj = repo.get_by_id(project_id)
        if not proj:
            return

        dialog = ProjectEditDialog(
            self,
            project={"name": proj.name, "root_path": proj.root_path,
                     "publish_root": proj.publish_root},
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                repo.update(
                    project_id,
                    root_path=data["root_path"],
                    publish_root=data["publish_root"],
                )
                self._load_projects()
                self.projects_changed.emit()
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"Failed to update project:\n{exc}")

    def _delete_project(self) -> None:
        """Delete the selected project from DB after confirmation."""
        if not self._session:
            return
        item = self.project_tree.currentItem()
        if not item:
            QMessageBox.information(self, "Info", "Please select a project to delete.")
            return

        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete project '{item.text(0)}'?\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            project_id = item.data(0, Qt.ItemDataRole.UserRole)
            repo = ProjectRepo(self._session)
            try:
                repo.delete(project_id)
                self._load_projects()
                self.projects_changed.emit()
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"Failed to delete project:\n{exc}")
