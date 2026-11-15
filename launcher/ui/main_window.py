"""Main window for Pipeline Launcher."""

from __future__ import annotations

from pathlib import Path
import os
import subprocess
from typing import Optional

from PySide6.QtCore import Qt, QFileSystemWatcher
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QMessageBox
)

from launcher.ui.widgets import (
    RoleSelectorWidget,
    DepartmentSelectorWidget,
    ProjectTreeWidget,
    SeqShotTreeWidget,
    FileTreeWidget,
)
from launcher.core.dcc_manager import dcc_manager
from launcher.core.launch_env import build_env_context, merge_env_store
from launcher.ui.real_source import RealSettingsDataSource
from launcher.ui.widgets.rename_shot_dialog import RenameShotDialog
from launcher.ui.settings_window import SettingsPanel
from launcher.ui.viewmodels import SettingsContext
from launcher.utils.logger import logger


def resolve_workdir(shot_dir: str, dcc: str = "", department: str = "") -> str:
    """Pick the workdir for a shot, department first.

    The department is the data axis and owns the work folder; the DCC is the
    runtime choice that opens it (see docs/VOCABULARY.md). Resolution order,
    most specific first:

    1. ``<shot>/<department>/<dcc>`` — a department that uses several apps
       (``fx/houdini``, ``comp/nuke``): department outside, dcc inside;
    2. ``<shot>/<department>`` — the normal single-app department folder;
    3. ``<shot>/<dcc>`` — legacy app-named trees (``<shot>/nuke``), kept
       launchable until every tree is migrated;
    4. ``<shot>/<department>`` even when missing, so the caller can report the
       folder it actually expected.

    Args:
        shot_dir: ``<root>/<show>/<seq>/<shot>`` (may be empty).
        dcc: Selected DCC (``nuke`` / ``maya`` / ``houdini``).
        department: Selected department token (``fx`` / ``comp`` / ``lighting``).

    Returns:
        Absolute workdir path, or the department path when nothing exists yet.
    """
    if not shot_dir:
        return ""
    candidates = []
    if department and dcc:
        candidates.append(os.path.join(shot_dir, department, dcc))
    if department:
        candidates.append(os.path.join(shot_dir, department))
    if dcc:
        candidates.append(os.path.join(shot_dir, dcc))
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(shot_dir, department) if department else shot_dir


def get_icon(icon_name: str) -> QIcon:
    """Load icon from imgs directory.

    Searches in order:
    1. Development path:  launcher/ui/imgs/{name}.png
    2. py2app bundle:     Resources/imgs/{name}.png
    3. py2app bundle:     Resources/launcher/ui/imgs/{name}.png

    Args:
        icon_name: Name of the icon file (without extension).

    Returns:
        QIcon object, empty QIcon if not found.
    """
    candidates = [
        # Development path (relative to this file)
        Path(__file__).parent / "imgs" / f"{icon_name}.png",
        # py2app: ../../../../.. = Resources/
        Path(__file__).parent.parent.parent.parent.parent
        / "imgs" / f"{icon_name}.png",
        # py2app (with prefix)
        Path(__file__).parent.parent.parent.parent.parent
        / "launcher" / "ui" / "imgs" / f"{icon_name}.png",
    ]
    for path in candidates:
        if path.exists():
            return QIcon(str(path))
    return QIcon()


class MainWindow(QMainWindow):
    """The main window of pipeline launcher."""

    def __init__(self, user=None, parent: Optional[QWidget] = None) -> None:
        """Initialize the main window.

        Args:
            user: Optional User object from database lookup.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._user = user
        # Modeless settings window: one instance, created on first use (T06).
        self._settings_win: Optional[SettingsPanel] = None
        # Override store a launch layers on top of the derived values.
        # ``None`` means <config dir>/env.yaml; tests point it at a temp file
        # so a developer's own overrides cannot change the assertions.
        self._env_store_path: Optional[str] = None
        self._setup_ui()
        self.project_tree.load_projects()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self.setWindowTitle("Pipeline Hatch")
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
        self._watched_paths: set[str] = set()  # Track watched paths to avoid leaks

        # DCC selection - which application to launch (RoleSelectorWidget reads dcc.yaml)
        self.role_menu = RoleSelectorWidget()

        # Department selection - whose workdir (fx/comp/lighting) to open.
        # The department is the data axis; the DCC above is only the runtime.
        self.department_menu = DepartmentSelectorWidget()
        self.department: str = self.department_menu.current_department()

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
        # Department on the far left (the data axis); the DCC sits directly to
        # its right with a fixed gap, so the pair reads as one context line.
        self.top_left_layout.addWidget(self.department_menu)
        self.top_left_layout.addSpacing(24)
        self.top_left_layout.addWidget(self.role_menu)
        # User info label (from DB, or offline mode)
        self.user_label = QLabel()
        self.user_label.setFont(self.launch_btn.font())  # Match Launch button font
        if self._user:
            self.user_label.setText(
                f"User: {self._user.display_name or self._user.username} [{self._user.role}]"
            )
        else:
            self.user_label.setText("Offline Mode")
            self.user_label.setStyleSheet("color: #aa6600;")

        self.top_right_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.top_right_layout.addWidget(self.user_label)
        self.top_right_layout.addWidget(self.launch_btn)
        self.top_right_layout.addWidget(self.settings_btn)
        self.top_layout.addLayout(self.top_left_layout)
        self.top_layout.addLayout(self.top_right_layout)

        # Project tree
        self.project_label = QLabel('Project:')
        self.project_tree = ProjectTreeWidget()
        self.project_layout = QVBoxLayout()
        self.project_layout.addWidget(self.project_label)
        self.project_layout.addWidget(self.project_tree)

        # Sequence/Shot tree
        self.seq_shot_label = QLabel('Seq/Shot:')
        self.seq_shot_tree = SeqShotTreeWidget()
        self.seq_shot_tree.set_file_watcher(self.file_watcher)
        self.seq_shot_layout = QVBoxLayout()
        self.seq_shot_layout.addWidget(self.seq_shot_label)
        self.seq_shot_layout.addWidget(self.seq_shot_tree)

        # File tree
        self.file_label = QLabel('File:')
        self.file_tree = FileTreeWidget()
        self.file_tree.set_file_watcher(self.file_watcher)
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
        self.project_tree.project_selected.connect(self._on_project_selected)
        self.seq_shot_tree.shot_selected.connect(self._on_shot_selected)
        self.seq_shot_tree.rename_requested.connect(self._on_rename_shot)
        self.role_menu.role_changed.connect(self._on_role_changed)
        self.department_menu.department_changed.connect(self._on_department_changed)
        self.file_watcher.directoryChanged.connect(self._on_directory_changed)
        self.launch_btn.clicked.connect(self._launch_dcc)

    def _watch_path(self, path: str) -> None:
        """Add a path to the file watcher, avoiding duplicate watches.

        Args:
            path: Directory path to watch for changes.
        """
        if path and path not in self._watched_paths:
            self.file_watcher.addPath(path)
            self._watched_paths.add(path)

    def _open_settings(self) -> None:
        """Open the settings window — modeless, one instance for the session.

        Settings apply immediately (no OK/Cancel transaction), so there is
        nothing to read back when the window closes: the project tree and the
        launch paths are kept in sync through ``projects_changed`` and
        ``_on_project_selected``. A second click on the gear raises the window
        that is already open instead of stacking another copy.
        """
        win = self._settings_win
        if win is None:
            # Real backend: the existing projects, read from the launcher
            # database (YAML fallback) plus their on-disk state.
            win = SettingsPanel(data_source=RealSettingsDataSource(),
                                current_user=self._user,
                                context=self._current_context())
            win.projects_changed.connect(self.project_tree.load_projects)
            win.finished.connect(self._on_settings_closed)
            self._settings_win = win

        win.show()
        win.raise_()
        win.activateWindow()

    def _current_context(self) -> SettingsContext:
        """Snapshot of what the next launch would use.

        The settings window copies this once when it opens; it never reads the
        main window live, so clicking around the tree cannot swap the numbers
        under an open window.
        """
        return SettingsContext(
            project=self.project,
            seq=self.sequence,
            shot=self.shot,
            dcc=self.role_menu.current_role() or "",
            department=self.department or "",
        )

    def _on_settings_closed(self, _result: int = 0) -> None:
        """Drop the reference so the next click builds a fresh window."""
        self._settings_win = None

    def _on_project_selected(self, name: str, root: str,
                              publish_root: str = "") -> None:
        """Handle project tree item selection.

        Args:
            name: Project name.
            root: Project root path.
            publish_root: Optional publish root path.
        """
        self.root_path = root
        self.publish_root_path = publish_root or self.publish_root_path
        self.project = name
        self._load_seq_shot(name, root)

    def _load_seq_shot(self, project_name: str, project_root: str) -> None:
        """Load sequence and shot structure via SeqShotTreeWidget.

        Args:
            project_name: Name of the selected project.
            project_root: Root path of the selected project.
        """
        if not project_root:
            return
        self.root_path = project_root
        self.project = project_name
        self._watch_path(os.path.join(project_root, project_name))
        self.seq_shot_tree.load_for_project(project_root, project_name)

    def _rename_source(self):
        """Backend for the rename dialog, built on first use.

        Only a rename needs a settings backend, so the main window does not open
        one at startup; tests inject ``window._data_source`` instead.
        """
        source = getattr(self, "_data_source", None)
        if source is None:
            source = RealSettingsDataSource()
            self._data_source = source
        return source

    def _on_rename_shot(self, sequence: str, shot: str) -> None:
        """Rename one untouched shot, then reload the tree it lives in.

        The tree is populated by scanning the disk, so it only needs to be told
        to look again — no model to keep in sync.
        """
        if not getattr(self, "project", "") or not getattr(self, "root_path", ""):
            return
        dialog = RenameShotDialog(self._rename_source(), self.project,
                                  sequence, shot, parent=self)
        if dialog.exec() != RenameShotDialog.DialogCode.Accepted:
            return
        self._load_seq_shot(self.project, self.root_path)

    def _on_shot_selected(self, seq: str, shot: str) -> None:
        """Handle shot selection from the sequence/shot tree.

        Args:
            seq: Sequence name.
            shot: Shot name.
        """
        self.sequence = seq
        self.shot = shot
        self._load_files()

    def _load_files(self) -> None:
        """Load files for the selected sequence/shot/department workdir."""
        if not self.sequence or not self.shot:
            return

        # Workdir is department-based: <root>/<show>/<seq>/<shot>/<department>.
        # ``self.department`` is kept in sync by _on_department_changed, so the
        # load path has a single source of truth. Until a department is picked
        # there is no workdir to show — stay silent, because the shot list is
        # still browsable; the launch path reports the missing choice.
        if not self.department:
            self.file_path = ""
            self.file_tree.load_for_path("")
            return

        department = self.department
        shot_dir = os.path.join(
            self.root_path,
            self.project,
            self.sequence,
            self.shot,
        )
        # The department owns the folder; the DCC only opens it. Legacy
        # DCC-named trees still resolve through resolve_workdir's fallback.
        self.file_path = resolve_workdir(shot_dir, self.role, department)

        self._watch_path(self.file_path)
        self.file_tree.load_for_path(self.file_path)

    def _on_role_changed(self, role: str) -> None:
        """Handle DCC (role) selection change — the launch target.

        The DCC is only the runtime choice; the workdir belongs to the
        department. Legacy app-named trees (``<shot>/nuke``) still depend on the
        DCC for their fallback folder, so the workdir is re-resolved anyway.
        """
        self.role = role
        if self.sequence and self.shot:
            self._load_files()

    def _on_department_changed(self, department: str) -> None:
        """Handle department selection change — reload the department workdir.

        An empty value means the artist went back to "Select your department":
        the file panel clears and nothing launches until one is chosen.
        """
        self.department = department
        if self.sequence and self.shot:
            self._load_files()
        elif not department:
            self.file_path = ""
            self.file_tree.load_for_path("")

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
        if not self.role or self.role == 'select your dcc...':
            self._show_info('Please select a dcc (Maya/Houdini/Nuke)!')
            logger.warning("Launch attempted without selecting a role")
            return

        if not self.department:
            self._show_info('Please select a department first!')
            logger.warning("Launch attempted without selecting a department")
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

        # A shot added through "Add shots…" has no folder for this department
        # yet: resolve_workdir reports the folder it *should* have, not one that
        # exists. Make it here — only the department level, and only when the
        # shot itself is there, so a stale selection cannot invent shots.
        if self.file_path and os.path.isdir(os.path.dirname(self.file_path)):
            os.makedirs(self.file_path, exist_ok=True)

        # Check if target path exists
        if file_path:
            if not os.path.exists(file_path):
                self._show_info(f'File not found: {file_path}')
                logger.warning(f"File not found: {file_path}")
                return
        elif self.file_path:
            if not os.path.exists(self.file_path):
                shot_dir = os.path.dirname(self.file_path)
                try:
                    available = sorted(
                        d for d in os.listdir(shot_dir)
                        if os.path.isdir(os.path.join(shot_dir, d))
                    )
                except OSError:
                    available = []
                listing = ", ".join(available) if available else "(empty)"
                self._show_info(
                    f'Project path not found: {self.file_path}\n\n'
                    f'{shot_dir} contains: {listing}'
                )
                logger.warning(
                    f"Project path not found: {self.file_path} (available: {available})"
                )
                return

        # Build environment context from the single implementation
        # (launcher.core.launch_env): the settings preview reads the same
        # function, so it cannot drift from what a launch really injects.
        # Two axes: DCC = application, DEPARTMENT = owner of the work.
        env_context = build_env_context(
            root_path=self.root_path,
            publish_root_path=self.publish_root_path,
            project=self.project,
            sequence=self.sequence,
            shot=self.shot,
            department=self.department,
            dcc=self.role,
        )

        # Layer the show's overrides on top of the derived values. Without this
        # the settings panel would be writing a file nobody reads: the values it
        # edits have to be the values a DCC receives, or the preview is a lie.
        env_context = merge_env_store(env_context, self._env_store_path)

        if self.role == 'houdini' and self.file_path:
            env_context['JOB'] = self.file_path

        # A DCC with no project switch and no $JOB (Nuke) is only "in" the shot
        # folder once a script from that folder is open: its save dialog starts
        # in dirname(nuke.scriptName()). Open the newest .nk there, or create
        # <shot>_v001.nk, so File > Save As lands in the department folder.
        # A failure here returns None and Nuke still launches bare.
        if not file_path and self.file_path:
            startup = dcc.startup_script(
                self.file_path,
                shot=self.shot,
                department=self.department,
                fps=env_context.get("FPS", ""),
            )
            if startup:
                file_path = startup
                logger.info(f"Opening {dcc.name} startup script: {startup}")
                self.file_tree.load_for_path(self.file_path)

        # Build and execute command
        if file_path and os.path.exists(file_path):
            command = dcc.build_command(file_path=file_path)
        else:
            command = dcc.build_command(project_path=self.file_path)

        # Merge pipeline env vars on top of current system environment,
        # so the child process inherits PATH, HOME, HOUDINI_PATH, etc.
        env = os.environ.copy()
        env.update(dcc.prepare_environment(**env_context))

        try:
            # ``cwd`` is how a DCC without a project switch (Nuke) is opened
            # "in" the shot workdir; every other DCC returns None and inherits.
            subprocess.Popen(command, env=env, cwd=dcc.launch_cwd(self.file_path))
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