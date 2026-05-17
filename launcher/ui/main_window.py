from pathlib import Path
import os
import subprocess

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QLabel, QTreeWidget, QTreeWidgetItem, QMessageBox
)

from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt, QFileSystemWatcher

from launcher.core.config_manager import config_manager
from launcher.core.dcc_manager import dcc_manager
from launcher.ui.settings_window import SettingsPanel


def get_icon(icon_name: str) -> QIcon:
    """Load icon"""
    icon_path = Path(__file__).parent / "imgs" / f"{icon_name}.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    return QIcon()


class MainWindow(QMainWindow):
    """The main window of pipeline launcher.

    Args:
        QMainWindow (_type_): _description_
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._load_projects_from_config()

    def _load_projects_from_config(self):
        """Load projects from YAML config automatically on startup."""
        try:
            projects = config_manager.get_project_list()
            self.project_tree.clear()
            for proj in projects:
                if proj.get("enabled", True):
                    project_item = QTreeWidgetItem(self.project_tree)
                    project_item.setText(0, proj["name"])
                    # Store the root path as item data for later use
                    project_item.setData(0, Qt.ItemDataRole.UserRole, proj["root"])

            # Use the first project's root as default
            if projects:
                first_proj = projects[0]
                self.root_path = first_proj.get("root", "")
                self.publish_root_path = first_proj.get("publish_root", "")
        except Exception as e:
            print(f"Failed to load projects from config: {e}")

    def _setup_ui(self):
        self.setWindowTitle("Y Pipeline")
        self.resize(1000, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        self.root_path = None
        self.publish_root_path = None
        self.role = None
        self.file_path = None  # Path to the selected file.
        self.project = None
        self.sequence = None
        self.shot = None
        self.file_watcher = QFileSystemWatcher(self)

        self.role_menu = QComboBox()
        self.role_menu.setEditable(False)
        self.role_menu.setFixedWidth(300)
        role_menu_items = [
            'Select your role...',
            'Maya',
            'Houdini',
            'Nuke'
        ]
        self.role_menu.addItems(role_menu_items)

        self.launch_btn = QPushButton('Launch')
        self.launch_btn.setFixedWidth(80)
        self.launch_btn.setFixedHeight(36)

        self.settings_btn = QPushButton()
        self.settings_btn.setFixedWidth(40)
        self.settings_btn.setFixedHeight(36)
        self.settings_btn.setIcon(get_icon("Settings"))

        self.top_layout = QHBoxLayout()
        self.top_left_layout = QHBoxLayout()
        self.top_left_layout.setContentsMargins(0, 0, 0, 0)
        self.top_right_layout = QHBoxLayout()
        self.top_right_layout.setContentsMargins(0, 0, 0, 0)

        self.top_left_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.top_left_layout.addWidget(self.role_menu)
        self.top_right_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.top_right_layout.addWidget(self.launch_btn)
        self.top_right_layout.addWidget(self.settings_btn)
        self.top_layout.addLayout(self.top_left_layout)
        self.top_layout.addLayout(self.top_right_layout)

        self.project_label = QLabel('Project:')
        self.project_tree = QTreeWidget()
        self.project_tree.setHeaderHidden(True)
        self.project_layout = QVBoxLayout()
        self.project_layout.addWidget(self.project_label)
        self.project_layout.addWidget(self.project_tree)

        self.seq_shot_label = QLabel('Seq/Shot:')
        self.seq_shot_tree = QTreeWidget()
        self.seq_shot_tree.setHeaderHidden(True)
        self.seq_shot_layout = QVBoxLayout()
        self.seq_shot_layout.addWidget(self.seq_shot_label)
        self.seq_shot_layout.addWidget(self.seq_shot_tree)

        self.file_label = QLabel('File:')
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_layout = QVBoxLayout()
        self.file_layout.addWidget(self.file_label)
        self.file_layout.addWidget(self.file_tree)

        self.btm_layout = QHBoxLayout()
        self.btm_layout.addLayout(self.project_layout)
        self.btm_layout.addLayout(self.seq_shot_layout)
        self.btm_layout.addLayout(self.file_layout)

        layout = QVBoxLayout(central_widget)

        # label = QLabel("Y Pipeline ready")
        layout.addLayout(self.top_layout)
        layout.addLayout(self.btm_layout)

        self.connections()

    def connections(self):

        self.settings_btn.clicked.connect(self.custom_settings)  # type: ignore
        self.project_tree.itemClicked.connect(
            self.load_seq_shot)  # type: ignore
        self.seq_shot_tree.itemClicked.connect(self.load_file)  # type: ignore
        self.role_menu.currentIndexChanged.connect(
            self.load_file)  # type: ignore
        self.file_watcher.directoryChanged.connect(
            self.load_file)  # type: ignore
        self.launch_btn.clicked.connect(self.launch_dcc)  # type: ignore

    def custom_settings(self):
        """Open settings dialog for manual path override."""
        settings_panel = SettingsPanel()
        result = settings_panel.exec()

        if result == settings_panel.Accepted:
            self.root_path = settings_panel.root_path_value.text()
            self.publish_root_path = settings_panel.publish_root_value.text()
            self.file_watcher.addPath(self.root_path)

    def load_seq_shot(self):
        """Load sequence and shot structure for selected project."""
        current_item = self.project_tree.currentItem()
        if not current_item:
            return

        project_name = current_item.text(0)
        project_root = current_item.data(0, Qt.ItemDataRole.UserRole)

        # Fallback to config if no stored path
        if not project_root:
            project_root = self.root_path

        project_path = os.path.join(project_root, project_name)

        # Update instance paths
        self.root_path = project_root
        self.project = project_name

        # watch project folders
        self.file_watcher.addPath(project_path)

        seq_list = []

        for p in os.listdir(project_path):
            if os.path.isdir(os.path.join(project_path, p)):
                seq_list.append(p)
        seq_list.sort()
        self.seq_shot_tree.clear()
        for seq in seq_list:
            seq_item = QTreeWidgetItem(self.seq_shot_tree)
            seq_item.setText(0, seq)
            shot_path = os.path.join(project_path, seq)

            # watch seq/shot tree widget directory
            self.file_watcher.addPath(shot_path)

            for shot in os.listdir(shot_path):
                if os.path.isdir(os.path.join(shot_path, shot)):

                    shot_item = QTreeWidgetItem(seq_item)
                    shot_item.setText(0, shot)
                    self.seq_shot_tree.sortItems(
                        0, Qt.SortOrder.AscendingOrder)

    def load_file(self):

        if self.seq_shot_tree.currentItem():
            current_name = self.seq_shot_tree.currentItem()
            parent_item = current_name.parent()
            project_name = self.project_tree.currentItem().text(0)

            msg_box = QMessageBox()
            msg_box.setText('Select a role to load files')
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)

            if self.role_menu.currentText() == 'Select your role...' and \
                    parent_item is not None:
                msg_box.exec()
            else:
                self.role = self.role_menu.currentText().lower()

            if parent_item is not None:
                self.file_tree.clear()
                self.shot = current_name.text(0)
                self.file_path = os.path.join(
                    self.root_path,
                    project_name,
                    parent_item.text(0),
                    self.shot,
                    self.role
                )

                # watch file folders
                self.file_watcher.addPath(self.file_path)

                if os.path.isdir(self.file_path):
                    for f in os.listdir(self.file_path):
                        file_existence = os.path.isfile(
                            os.path.join(self.file_path, f)
                        )
                        if file_existence and f.startswith('.'):
                            continue
                        elif file_existence:
                            file_item = QTreeWidgetItem(self.file_tree)
                            file_item.setText(0, f)
                            self.file_tree.sortItems(
                                0, Qt.SortOrder.AscendingOrder)

    def set_env(self):
        """Collect pipeline environment variables."""
        base_env = {}
        self.project = self.project_tree.currentItem().text(0)
        seq_shot_item = self.seq_shot_tree.currentItem()
        if seq_shot_item:
            self.shot = seq_shot_item.text(0)
            if seq_shot_item.parent():
                self.sequence = seq_shot_item.parent().text(0)

        base_env['ROLE'] = self.role
        base_env['PROJECT_ROOT'] = self.root_path
        base_env['PUBLISH_ROOT'] = self.publish_root_path
        base_env['SHOW'] = self.project
        base_env['SEQ'] = self.sequence
        base_env['SHOT'] = self.shot

        return base_env

    def launch_dcc(self):
        """Launch DCC application using config-based DCC manager."""
        if not self.role or self.role == 'select your role...':
            msg_box = QMessageBox()
            msg_box.setText('Please select a role (Maya/Houdini/Nuke)!')
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()
            return

        # Get DCC instance from manager
        dcc = dcc_manager.get_dcc(self.role)
        if not dcc:
            msg_box = QMessageBox()
            msg_box.setText(f'DCC "{self.role}" not configured!')
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()
            return

        # Get file path if a file is selected
        file_name = None
        file_path = None
        if self.file_tree.topLevelItemCount() > 0:
            selected_item = self.file_tree.currentItem()
            if selected_item:
                file_name = selected_item.text(0)
                file_path = os.path.join(self.file_path, file_name)

        # Build environment context
        env_context = {
            'ROLE': self.role,
            'PROJECT_ROOT': self.root_path,
            'PUBLISH_ROOT': self.publish_root_path,
            'SHOW': self.project,
            'SEQ': self.sequence,
            'SHOT': self.shot,
        }

        # Add JOB for Houdini
        if self.role == 'houdini':
            env_context['JOB'] = self.file_path

        # Build command based on selection
        if file_path and os.path.exists(file_path):
            command = dcc.build_command(file_path=file_path)
        else:
            command = dcc.build_command(project_path=self.file_path)

        # Prepare environment
        env = dcc.prepare_environment(**env_context)

        # Launch
        try:
            subprocess.Popen(command, env=env)
        except Exception as e:
            msg_box = QMessageBox()
            msg_box.setText(f'Failed to launch {dcc.name}: {e}')
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()


# Entry point for running directly (for development only)
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
