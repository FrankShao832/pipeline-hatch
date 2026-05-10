from pathlib import Path
import os
import subprocess
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QLabel, QTreeWidget, QDialog, QTreeWidgetItem, QMessageBox
)

from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt, QFileSystemWatcher
from ui.settings_window import SettingsPanel

MAYA_ENV_PATH = '/Users/frank/Library/Preferences/Autodesk/maya/2025/Maya.env'


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

        self.launch_btn = QPushButton('Launch!')
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
        """Custom settings."""

        settings_panel = SettingsPanel()
        result = settings_panel.exec()

        if result == QDialog.DialogCode.Accepted:

            self.root_path = settings_panel.root_path_value.text()
            self.publish_root_path = settings_panel.publish_root_value.text()

            # watch project root path
            self.file_watcher.addPath(self.root_path)

            if self.root_path is not None:
                project_list = []
                for p in os.listdir(self.root_path):
                    if os.path.isdir(os.path.join(self.root_path, p)):
                        project_list.append(p)

                project_list.sort()
                self.project_tree.clear()
                for p in project_list:
                    project_item = QTreeWidgetItem(self.project_tree)
                    project_item.setText(0, p)

        return self.root_path, self.publish_root_path

    def load_seq_shot(self):
        """_summary_

        Returns:
            _type_: _description_
        """
        project_name = self.project_tree.currentItem().text(0)
        project_path = os.path.join(
            self.root_path, project_name)  # type: ignore

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

    def create_maya_env(self):
        """Parse the Maya.env file and create a new one for subprocess."""

        maya_env = {}
        with open(MAYA_ENV_PATH, 'r') as f:
            for line in f:
                if line.startswith('#'):
                    continue
                elif '=' in line:
                    key, value = line.strip().split('=', 1)
                    maya_env[key.strip()] = value.strip()
        base_env = self.set_env()
        maya_env.update(base_env)

        return maya_env

    def set_env(self):
        base_env = {}
        self.project = self.project_tree.currentItem().text(0)
        seq_shot_item = self.seq_shot_tree.currentItem()
        if seq_shot_item:
            self.shot = seq_shot_item.text(0)
            if seq_shot_item.parent():
                self.sequence = seq_shot_item.parent().text(0)

        os.environ['ROLE'] = self.role
        os.environ['PROJECT_ROOT'] = self.root_path
        os.environ['PUBLISH_ROOT'] = self.publish_root_path
        os.environ['SHOW'] = self.project
        os.environ['SEQ'] = self.sequence
        os.environ['SHOT'] = self.shot

        base_env['ROLE'] = self.role
        base_env['PROJECT_ROOT'] = self.root_path
        base_env['PUBLISH_ROOT'] = self.publish_root_path
        base_env['SHOW'] = self.project
        base_env['SEQ'] = self.sequence
        base_env['SHOT'] = self.shot

        return base_env

    def launch_dcc(self):

        maya_command = [
            '/Applications/Autodesk/maya2025/Maya.app/Contents/MacOS/Maya'
        ]
        maya_env = self.create_maya_env()

        nuke_command = [
            '/Applications/Nuke15.0v4/Nuke15.0v4.app/Contents/MacOS/Nuke15.0',
            '--nukex'
        ]

        # /Applications/Houdini/Houdini19.5.752/Houdini FX 19.5.752.app/
        # Contents/MacOS
        houdini_command = [
            ('/Applications/Houdini//Houdini20.0.625/Frameworks/'
                'Houdini.framework/Versions/20.0/Resources/bin/houdinifx')
        ]
        file_name = None
        if self.file_tree.topLevelItemCount() > 0:
            file_name = self.file_tree.currentItem().text(0)
        dcc_command = []

        if file_name:
            file_path = os.path.join(
                self.file_path,
                file_name
            )
            if self.role == 'maya':
                maya_command.append('-file')
                maya_command.append(file_path)
                dcc_command = maya_command
            elif self.role == 'houdini':
                # self.set_h_env()
                houdini_command.append(file_path)
                dcc_command = houdini_command
            elif self.role == 'nuke':
                nuke_command.append(file_path)
                dcc_command = nuke_command
            else:
                msg_box = QMessageBox()
                msg_box.setText('Select a role!')
                msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
                msg_box.exec()

        else:
            if self.role == 'maya':
                maya_command.append('-proj')
                maya_command.append(self.file_path)  # type: ignore
                dcc_command = maya_command
            elif self.role == 'houdini':
                # self.set_h_env()
                os.putenv('JOB', self.file_path)  # type: ignore
                dcc_command = houdini_command

            elif self.role == 'nuke':
                nuke_command.append('-m')
                nuke_command.append(self.file_path)  # type: ignore
                dcc_command = nuke_command
            else:
                msg_box = QMessageBox()
                msg_box.setText('Select a role!')
                msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
                msg_box.exec()

        if self.role == 'maya':
            subprocess.Popen(dcc_command, env=maya_env)
        else:
            self.set_env()
            subprocess.Popen(dcc_command)


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    # Only needed (sys.argv) for access to command line arguments
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
