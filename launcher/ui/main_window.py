"""Main window for Pipeline Launcher."""

from __future__ import annotations

from pathlib import Path
import os
import subprocess
from typing import Optional

from PySide6.QtCore import Qt, QFileSystemWatcher
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QLabel, QTreeWidget, QTreeWidgetItem, QMessageBox, QDialog
)

from launcher.core.config_manager import config_manager
from launcher.core.dcc_manager import dcc_manager
from launcher.ui.settings_window import SettingsPanel
from launcher.utils.logger import logger


def get_icon(icon_name: str) -> QIcon:
    """Load icon from imgs directory.

    Args:
        icon_name: Name of the icon file (without extension).

    Returns:
        QIcon object, empty QIcon if not found.
    """
    icon_path = Path(__file__).parent / "imgs" / f"{icon_name}.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    return QIcon()


class MainWindow(QMainWindow):
    """The main window of pipeline launcher."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the main window.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._setup_ui()
        self._load_projects_from_config()

    def _load_projects_from_config(self) -> None:
        """Load projects from YAML config automatically on startup."""
        try:
            projects = config_manager.get_project_list()
            self.project_tree.clear()
            for proj in projects:
                if proj.get("enabled", True):
                    project_item = QTreeWidgetItem(self.project_tree)
                    project_item.setText(0, proj["name"])
                    project_item.setData(0, Qt.ItemDataRole.UserRole, proj["root"])

            if projects:
                first_proj = projects[0]
                self.root_path = first_proj.get("root", "")
                self.publish_root_path = first_proj.get("publish_root", "")
                logger.info(f"Loaded {len(projects)} project(s)")
        except Exception as e:
            logger.error(f"Failed to load projects from config: {e}")

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self.setWindowTitle("Y Pipeline")
        self.resize(1000, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # State variables - initialized with empty strings to avoid None issues
        self.root_path: str = ""
        self.publish_root_path: str = ""
        self.role: str = ""
        self.file_path: str = ""
        self.project: str = ""
        self.sequence: str = ""
        self.shot: str = ""
        self.file_watcher = QFileSystemWatcher(self)

        # Role selection
        self.role_menu = QComboBox()
        self.role_menu.setEditable(False)
        self.role_menu.setFixedWidth(300)
        self.role_menu.addItems([
            'Select your role...',
            'Maya',
            'Houdini',
            'Nuke'
        ])

        # Buttons
        self.launch_btn = QPushButton('Launch')
        self.launch_btn.setFixedWidth(80)
        self.launch_btn.setFixedHeight(36)

        self.settings_btn = QPushButton()
        self.settings_btn.setFixedWidth(40)
        self.settings_btn.setFixedHeight(36)
        self.settings_btn.setIcon(get_icon("Settings"))

        # Top layout
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

        # Project tree
        self.project_label = QLabel('Project:')
        self.project_tree = QTreeWidget()
        self.project_tree.setHeaderHidden(True)
        self.project_layout = QVBoxLayout()
        self.project_layout.addWidget(self.project_label)
        self.project_layout.addWidget(self.project_tree)

        # Sequence/Shot tree
        self.seq_shot_label = QLabel('Seq/Shot:')
        self.seq_shot_tree = QTreeWidget()
        self.seq_shot_tree.setHeaderHidden(True)
        self.seq_shot_layout = QVBoxLayout()
        self.seq_shot_layout.addWidget(self.seq_shot_label)
        self.seq_shot_layout.addWidget(self.seq_shot_tree)

        # File tree
        self.file_label = QLabel('File:')
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_layout = QVBoxLayout()
        self.file_layout.addWidget(self.file_label)
        self.file_layout.addWidget(self.file_tree)

        # Bottom layout (three-column)
        self.btm_layout = QHBoxLayout()
        self.btm_layout.addLayout(self.project_layout)
        self.btm_layout.addLayout(self.seq_shot_layout)
        self.btm_layout.addLayout(self.file_layout)

        # Main layout
        layout = QVBoxLayout(central_widget)
        layout.addLayout(self.top_layout)
        layout.addLayout(self.btm_layout)

        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect UI signals to slots."""
        self.settings_btn.clicked.connect(self._open_settings)
        self.project_tree.itemClicked.connect(self._on_project_selected)
        self.seq_shot_tree.itemClicked.connect(self._on_seq_shot_selected)
        self.role_menu.currentIndexChanged.connect(self._on_role_changed)
        self.file_watcher.directoryChanged.connect(self._on_directory_changed)
        self.launch_btn.clicked.connect(self._launch_dcc)

    def _open_settings(self) -> None:
        """Open settings dialog for manual path override."""
        settings_panel = SettingsPanel()
        if settings_panel.exec() == int(QDialog.DialogCode.Accepted):
            self.root_path = settings_panel.root_path_value.text()
            self.publish_root_path = settings_panel.publish_root_value.text()
            if self.root_path:
                self.file_watcher.addPath(self.root_path)

    def _on_project_selected(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle project tree item selection.

        Args:
            item: Selected tree item.
            column: Column index (unused).
        """
        del column  # Unused
        self._load_seq_shot(item)

    def _load_seq_shot(self, item: QTreeWidgetItem) -> None:
        """Load sequence and shot structure for selected project.

        Args:
            item: Project tree item.
        """
        project_name = item.text(0)
        project_root = item.data(0, Qt.ItemDataRole.UserRole) or self.root_path

        if not project_root:
            return

        project_path = os.path.join(project_root, project_name)
        self.root_path = project_root
        self.project = project_name

        self.file_watcher.addPath(project_path)

        seq_list = sorted([
            p for p in os.listdir(project_path)
            if os.path.isdir(os.path.join(project_path, p))
        ])

        self.seq_shot_tree.clear()
        for seq in seq_list:
            seq_item = QTreeWidgetItem(self.seq_shot_tree)
            seq_item.setText(0, seq)
            shot_path = os.path.join(project_path, seq)
            self.file_watcher.addPath(shot_path)

            for shot in os.listdir(shot_path):
                if os.path.isdir(os.path.join(shot_path, shot)):
                    shot_item = QTreeWidgetItem(seq_item)
                    shot_item.setText(0, shot)

        self.seq_shot_tree.sortItems(0, Qt.SortOrder.AscendingOrder)

    def _on_seq_shot_selected(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle sequence/shot tree item selection.

        Args:
            item: Selected tree item.
            column: Column index (unused).
        """
        del column  # Unused
        self._load_files()

    def _load_files(self) -> None:
        """Load files for selected sequence/shot."""
        current_item = self.seq_shot_tree.currentItem()
        if not current_item:
            return

        parent_item = current_item.parent()
        if not parent_item:
            return

        role_text = self.role_menu.currentText()
        if role_text == 'Select your role...':
            self._show_info("Please select a role to load files")
            return

        self.role = role_text.lower()
        project_item = self.project_tree.currentItem()
        if not project_item:
            return

        self.file_tree.clear()
        self.shot = current_item.text(0)
        self.sequence = parent_item.text(0)

        project_name = project_item.text(0)
        self.file_path = os.path.join(
            self.root_path,
            project_name,
            self.sequence,
            self.shot,
            self.role
        )

        self.file_watcher.addPath(self.file_path)

        if os.path.isdir(self.file_path):
            for filename in os.listdir(self.file_path):
                filepath = os.path.join(self.file_path, filename)
                if os.path.isfile(filepath) and not filename.startswith('.'):
                    file_item = QTreeWidgetItem(self.file_tree)
                    file_item.setText(0, filename)

            self.file_tree.sortItems(0, Qt.SortOrder.AscendingOrder)

    def _on_role_changed(self, index: int) -> None:
        """Handle role menu selection change.

        Args:
            index: Selected index (unused).
        """
        del index  # Unused
        self._load_files()

    def _on_directory_changed(self, path: str) -> None:
        """Handle directory change event.

        Args:
            path: Changed directory path.
        """
        logger.debug(f"Directory changed: {path}")
        self._load_files()

    def _show_info(self, message: str) -> None:
        """Show information message.

        Args:
            message: Message to display.
        """
        msg_box = QMessageBox()
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def _check_dcc_exists(self, dcc) -> bool:
        """Check if DCC application is installed.

        Uses the DCC's built-in executable_exists() method which checks:
        1. macOS /Applications/ .app bundle
        2. Direct executable path
        3. System PATH environment variable

        Works on macOS, Linux, and Windows.

        Args:
            dcc: DCC instance to check.

        Returns:
            True if DCC exists, False otherwise.
        """
        return dcc.executable_exists()

    def _launch_dcc(self) -> None:
        """Launch DCC application using config-based DCC manager."""
        if not self.role or self.role == 'select your role...':
            self._show_info('Please select a role (Maya/Houdini/Nuke)!')
            logger.warning("Launch attempted without selecting a role")
            return

        dcc = dcc_manager.get_dcc(self.role)
        if not dcc:
            self._show_info(f'DCC "{self.role}" not configured!')
            logger.error(f"DCC not found in config: {self.role}")
            return

        # Check if DCC application exists (macOS .app bundle or executable)
        if not self._check_dcc_exists(dcc):
            self._show_info(f'{dcc.name} not found! Please check installation.')
            logger.error(f"DCC application not found: {dcc.app_name or dcc.executable}")
            return

        # Get selected file
        file_name: Optional[str] = None
        file_path: Optional[str] = None
        if self.file_tree.topLevelItemCount() > 0:
            selected_item = self.file_tree.currentItem()
            if selected_item:
                name = selected_item.text(0)
                if name:
                    file_name = name
                    file_path = os.path.join(self.file_path, name)

        # Check if target path exists
        if file_path:
            if not os.path.exists(file_path):
                self._show_info(f'File not found: {file_path}')
                logger.warning(f"File not found: {file_path}")
                return
        elif self.file_path:
            if not os.path.exists(self.file_path):
                self._show_info(f'Project path not found: {self.file_path}')
                logger.warning(f"Project path not found: {self.file_path}")
                return

        # Build environment context
        env_context: dict[str, str] = {
            'ROLE': self.role,
            'PROJECT_ROOT': self.root_path,
            'PUBLISH_ROOT': self.publish_root_path,
            'SHOW': self.project,
            'SEQ': self.sequence,
            'SHOT': self.shot,
        }

        if self.role == 'houdini' and self.file_path:
            env_context['JOB'] = self.file_path

        # Build and execute command
        if file_path and os.path.exists(file_path):
            command = dcc.build_command(file_path=file_path)
        else:
            command = dcc.build_command(project_path=self.file_path)

        env = dcc.prepare_environment(**env_context)

        try:
            subprocess.Popen(command, env=env)
            logger.info(f"Launched {dcc.name}")
            logger.debug(f"Command: {' '.join(command)}")
        except Exception as e:
            logger.error(f"Failed to launch {dcc.name}: {e}", exc_info=True)
            self._show_info(f'Failed to launch {dcc.name}: {e}')


# Entry point for running directly (for development only)
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())