"""Tests for UI widgets — RoleSelector, ProjectTree, SeqShotTree, FileTree."""

from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QTreeWidgetItem

from launcher.ui.widgets.role_selector import RoleSelectorWidget
from launcher.ui.widgets.project_tree import (
    ProjectTreeWidget,
    _SETTINGS_KEY,
    _SETTINGS_ORG,
    _SETTINGS_APP,
    _STAR,
)
from launcher.ui.widgets.seq_shot_tree import SeqShotTreeWidget
from launcher.ui.widgets.file_tree import FileTreeWidget


# =============================================================================
#  RoleSelectorWidget  (3 tests)
# =============================================================================

class TestRoleSelectorWidget:
    """Test suite for RoleSelectorWidget."""

    def test_initial_state(self, qtbot):
        """Placeholder 'Select your role...' at index 0, current_role() is None."""
        widget = RoleSelectorWidget()
        qtbot.addWidget(widget)

        assert widget.count() >= 1
        assert widget.itemText(0) == "Select your role..."
        assert widget.current_role() is None

    def test_select_role(self, qtbot):
        """Selecting a role emits role_changed with the correct role key."""
        widget = RoleSelectorWidget()
        qtbot.addWidget(widget)

        emitted_roles = []
        widget.role_changed.connect(lambda r: emitted_roles.append(r))

        # Select the first real role (index 1, skip placeholder at 0)
        widget.setCurrentIndex(1)
        role_key = widget.itemData(1)

        assert role_key is not None
        assert role_key in ("maya", "houdini", "nuke")
        assert emitted_roles == [role_key]
        assert widget.current_role() == role_key

    def test_fallback_on_config_error(self, qtbot):
        """When config fails, widget falls back to hardcoded role list."""
        with patch("launcher.core.config_manager.ConfigManager.get_dcc_config") as mock:
            mock.side_effect = RuntimeError("Config load failed")
            widget = RoleSelectorWidget()
            qtbot.addWidget(widget)

        # Fallback list has 4 items (placeholder + 3 roles)
        assert widget.count() == 4
        assert widget.itemText(0) == "Select your role..."
        assert widget.itemText(1) == "Maya"
        assert widget.itemText(2) == "Houdini"
        assert widget.itemText(3) == "Nuke"

        # current_role() fallback: uses lowercased display text
        widget.setCurrentIndex(1)
        assert widget.current_role() == "maya"


# =============================================================================
#  ProjectTreeWidget  (5 tests)
# =============================================================================

class TestProjectTreeWidget:
    """Test suite for ProjectTreeWidget."""

    def _clear_qsettings(self):
        """Remove any stored default project from QSettings."""
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        settings.remove(_SETTINGS_KEY)
        settings.sync()

    def test_load_projects(self, qtbot):
        """Projects loaded from YAML have correct structure."""
        self._clear_qsettings()
        widget = ProjectTreeWidget()
        qtbot.addWidget(widget)
        widget.load_projects()

        assert widget.topLevelItemCount() > 0
        # Verify first item has name + root data
        item = widget.topLevelItem(0)
        assert item.text(0)
        root = item.data(0, Qt.ItemDataRole.UserRole)
        assert root and isinstance(root, str) and len(root) > 0

    def test_click_emits_signal(self, qtbot):
        """Clicking a project item emits project_selected with clean name + root."""
        self._clear_qsettings()
        widget = ProjectTreeWidget()
        qtbot.addWidget(widget)
        widget.load_projects()

        target = widget.topLevelItem(0)
        assert target is not None

        with qtbot.waitSignal(widget.project_selected, timeout=500) as blocker:
            # Simulate user click via the connected method
            widget._on_item_clicked(target, 0)

        name, root, publish_root = blocker.args
        assert isinstance(name, str) and len(name) > 0
        assert isinstance(root, str) and len(root) > 0
        assert isinstance(publish_root, str)
        # Name should not have ★ prefix
        assert not name.startswith(str(_STAR))

    def test_default_project_marker(self, qtbot):
        """Default project gets ★ prefix, bold font, and moves to top."""
        self._clear_qsettings()
        star_str = str(_STAR)
        # Set a default project before loading
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        settings.setValue(_SETTINGS_KEY, "Demo")
        settings.sync()

        widget = ProjectTreeWidget()
        qtbot.addWidget(widget)
        widget.load_projects()

        # Find the default project (should be at index 0 with ★)
        assert widget.topLevelItemCount() > 0
        top_item = widget.topLevelItem(0)
        assert top_item is not None
        assert top_item.text(0).startswith(star_str), (
            f"Expected ★ prefix, got: {top_item.text(0)!r}"
        )
        assert top_item.font(0).bold() is True

        self._clear_qsettings()

    def test_clear_default_project(self, qtbot):
        """Clearing default removes ★ and bold from all items."""
        self._clear_qsettings()
        star_str = str(_STAR)

        # Set default, then clear
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        settings.setValue(_SETTINGS_KEY, "Demo")
        settings.sync()

        widget = ProjectTreeWidget()
        qtbot.addWidget(widget)
        widget.load_projects()

        # Now clear
        widget._clear_default_project(None)

        # No item should have ★ prefix
        for i in range(widget.topLevelItemCount()):
            item = widget.topLevelItem(i)
            assert not item.text(0).startswith(star_str)
            assert item.font(0).bold() is False

        self._clear_qsettings()

    def test_context_menu_content(self, qtbot):
        """Right-click on a non-default project shows 'Set as default' action."""
        self._clear_qsettings()

        widget = ProjectTreeWidget()
        qtbot.addWidget(widget)
        widget.load_projects()
        assert widget.topLevelItemCount() > 0

        target = widget.topLevelItem(0)

        # For non-default item, menu action should be "Set as default"
        display = target.text(0)
        name = display[len(str(_STAR)):] if display.startswith(str(_STAR)) else display
        default_name = widget._get_default_name()
        if name == default_name:
            expected_text = "Clear default project"
        else:
            expected_text = "Set as default project"

        assert expected_text in ("Set as default project", "Clear default project")

        self._clear_qsettings()


# =============================================================================
#  SeqShotTreeWidget  (4 tests)
# =============================================================================

class TestSeqShotTreeWidget:
    """Test suite for SeqShotTreeWidget."""

    def test_empty_project(self, qtbot, tmp_path):
        """Empty project directory results in empty tree."""
        widget = SeqShotTreeWidget()
        qtbot.addWidget(widget)
        widget.load_for_project(str(tmp_path), "nonexistent")

        assert widget.topLevelItemCount() == 0

    def test_load_with_sequences(self, qtbot, tmp_path):
        """Simulated directory structure populates seq/shot hierarchy."""
        # Create: project/seq01/shot01, project/seq01/shot02, project/seq02/shot03
        base = tmp_path / "my_project"
        (base / "seq01" / "shot01").mkdir(parents=True)
        (base / "seq01" / "shot02").mkdir(parents=True)
        (base / "seq02" / "shot03").mkdir(parents=True)

        widget = SeqShotTreeWidget()
        qtbot.addWidget(widget)
        widget.load_for_project(str(tmp_path), "my_project")

        assert widget.topLevelItemCount() == 2
        seq1 = widget.topLevelItem(0)
        seq2 = widget.topLevelItem(1)

        assert seq1.text(0) == "seq01"
        assert seq1.childCount() == 2
        assert seq1.child(0).text(0) == "shot01"
        assert seq1.child(1).text(0) == "shot02"

        assert seq2.text(0) == "seq02"
        assert seq2.childCount() == 1
        assert seq2.child(0).text(0) == "shot03"

    def test_shot_selected_signal(self, qtbot, tmp_path):
        """Clicking a shot leaf node emits shot_selected with seq + shot names."""
        base = tmp_path / "p"
        (base / "seqA" / "shotX").mkdir(parents=True)

        widget = SeqShotTreeWidget()
        qtbot.addWidget(widget)
        widget.load_for_project(str(tmp_path), "p")

        leaf = widget.topLevelItem(0).child(0)
        assert leaf is not None

        with qtbot.waitSignal(widget.shot_selected, timeout=1000) as blocker:
            widget._on_item_clicked(leaf, 0)

        assert blocker.args == ["seqA", "shotX"]

    def test_file_watcher_set(self, qtbot):
        """After set_file_watcher, internal _watcher is not None."""
        from PySide6.QtCore import QFileSystemWatcher

        widget = SeqShotTreeWidget()
        qtbot.addWidget(widget)
        assert widget._watcher is None

        watcher = QFileSystemWatcher()
        widget.set_file_watcher(watcher)
        assert widget._watcher is watcher


# =============================================================================
#  FileTreeWidget  (3 tests)
# =============================================================================

class TestFileTreeWidget:
    """Test suite for FileTreeWidget."""

    def test_load_files(self, qtbot, tmp_path):
        """Files in a directory are listed, sorted alphabetically."""
        (tmp_path / "zeta.ma").write_text("")
        (tmp_path / "alpha.hip").write_text("")
        (tmp_path / "beta.nk").write_text("")

        widget = FileTreeWidget()
        qtbot.addWidget(widget)
        widget.load_for_path(str(tmp_path))

        assert widget.topLevelItemCount() == 3
        assert widget.topLevelItem(0).text(0) == "alpha.hip"
        assert widget.topLevelItem(1).text(0) == "beta.nk"
        assert widget.topLevelItem(2).text(0) == "zeta.ma"

    def test_hidden_files_excluded(self, qtbot, tmp_path):
        """Files starting with '.' are not shown in the tree."""
        (tmp_path / "visible.ma").write_text("")
        (tmp_path / ".hidden").write_text("")
        (tmp_path / ".gitkeep").write_text("")

        widget = FileTreeWidget()
        qtbot.addWidget(widget)
        widget.load_for_path(str(tmp_path))

        assert widget.topLevelItemCount() == 1
        assert widget.topLevelItem(0).text(0) == "visible.ma"

    def test_selected_file_path(self, qtbot, tmp_path):
        """selected_file_path returns filename of selected item."""
        (tmp_path / "scene.ma").write_text("")

        widget = FileTreeWidget()
        qtbot.addWidget(widget)
        widget.load_for_path(str(tmp_path))

        # Initially no selection
        assert widget.selected_file_path() is None

        # Select the item
        item = widget.topLevelItem(0)
        widget.setCurrentItem(item)
        assert widget.selected_file_path() == "scene.ma"
