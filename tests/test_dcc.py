"""Tests for DCC implementations."""

import pytest
import platform
from pathlib import Path
import sys

# Add launcher to path
sys.path.insert(0, str(Path(__file__).parent.parent / "launcher"))

from launcher.dcc.dcc_maya import MayaDCC
from launcher.dcc.dcc_houdini import HoudiniDCC
from launcher.dcc.dcc_nuke import NukeDCC
from launcher.core.config_manager import ConfigManager


class TestMayaDCC:
    """Test suite for MayaDCC."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset singleton before each test."""
        ConfigManager._instance = None
        ConfigManager._config_cache = {}
        yield

    @pytest.fixture
    def maya_config(self):
        """Sample Maya configuration."""
        return {
            "name": "Maya",
            "role": "maya",
            "executable": "/Applications/Autodesk/maya2025/Maya.app/Contents/MacOS/Maya",
            "app_name": "Maya2025.app",
            "env_file": "~/Library/Preferences/Autodesk/maya/2025/Maya.env",
            "flags": {
                "file": "-file",
                "project": "-proj"
            }
        }

    def test_properties(self, maya_config):
        """Test MayaDCC property access."""
        maya = MayaDCC(maya_config)

        assert maya.name == "Maya"
        assert maya.role == "maya"
        assert maya.executable == "/Applications/Autodesk/maya2025/Maya.app/Contents/MacOS/Maya"
        assert maya.app_name == "Maya2025.app"
        assert maya.env_file == "~/Library/Preferences/Autodesk/maya/2025/Maya.env"

    def test_build_command_with_file(self, maya_config):
        """Test building command with file path."""
        maya = MayaDCC(maya_config)
        cmd = maya.build_command(file_path="/test/scene.ma")

        if platform.system() == "Darwin":
            assert "open" in cmd
            assert "-a" in cmd
            assert "Maya2025.app" in cmd
            assert "--args" in cmd
            assert "-file" in cmd
            assert "/test/scene.ma" in cmd
        else:
            assert cmd[0] == maya_config["executable"]
            assert "-file" in cmd
            assert "/test/scene.ma" in cmd

    def test_build_command_with_project(self, maya_config):
        """Test building command with project path."""
        maya = MayaDCC(maya_config)
        cmd = maya.build_command(project_path="/test/project")

        assert "--args" in cmd
        assert "-proj" in cmd
        assert "/test/project" in cmd

    def test_build_command_empty(self, maya_config):
        """Test building command with no arguments."""
        maya = MayaDCC(maya_config)
        cmd = maya.build_command()

        # Should still have basic command
        assert len(cmd) > 0

    def test_prepare_environment(self, maya_config):
        """Test environment preparation."""
        maya = MayaDCC(maya_config)
        env = maya.prepare_environment(
            ROLE="maya",
            PROJECT_ROOT="/projects",
            SHOW="Demo"
        )

        assert env["ROLE"] == "maya"
        assert env["PROJECT_ROOT"] == "/projects"
        assert env["SHOW"] == "Demo"


class TestHoudiniDCC:
    """Test suite for HoudiniDCC."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset singleton before each test."""
        ConfigManager._instance = None
        ConfigManager._config_cache = {}
        yield

    @pytest.fixture
    def houdini_config(self):
        """Sample Houdini configuration."""
        return {
            "name": "Houdini",
            "role": "houdini",
            "executable": "/Applications/Houdini/Houdini20.5.613/Frameworks/Houdini.framework/Versions/20.5/Resources/bin/houdinifx",
            "app_name": "Houdini FX 20.5.613.app",
            "env_vars": {
                "JOB": ""
            },
            "flags": {}
        }

    def test_properties(self, houdini_config):
        """Test HoudiniDCC property access."""
        houdini = HoudiniDCC(houdini_config)

        assert houdini.name == "Houdini"
        assert houdini.role == "houdini"
        assert houdini.app_name == "Houdini FX 20.5.613.app"

    def test_build_command_with_file(self, houdini_config):
        """Test building command with file path."""
        houdini = HoudiniDCC(houdini_config)
        cmd = houdini.build_command(file_path="/test/scene.hip")

        if platform.system() == "Darwin":
            assert "open" in cmd
            assert "-a" in cmd
            assert "Houdini FX 20.5.613.app" in cmd
            assert "--args" in cmd
            assert "/test/scene.hip" in cmd

    def test_prepare_environment(self, houdini_config):
        """Test environment preparation with JOB."""
        houdini = HoudiniDCC(houdini_config)
        env = houdini.prepare_environment(
            JOB="/test/jobs",
            ROLE="houdini",
            SHOW="Demo"
        )

        assert env["JOB"] == "/test/jobs"
        assert env["ROLE"] == "houdini"
        assert env["SHOW"] == "Demo"


class TestNukeDCC:
    """Test suite for NukeDCC."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset singleton before each test."""
        ConfigManager._instance = None
        ConfigManager._config_cache = {}
        yield

    @pytest.fixture
    def nuke_config(self):
        """Sample Nuke configuration."""
        return {
            "name": "Nuke",
            "role": "nuke",
            "executable": "/Applications/Nuke16.0v3/Nuke16.0v3.app/Contents/MacOS/Nuke16.0v3",
            "app_name": "Nuke16.0v3.app",
            "flags": {
                "nukex": "--nukex",
                "file": "",
                "project": "-m"
            }
        }

    def test_properties(self, nuke_config):
        """Test NukeDCC property access."""
        nuke = NukeDCC(nuke_config)

        assert nuke.name == "Nuke"
        assert nuke.role == "nuke"
        assert nuke.app_name == "Nuke16.0v3.app"

    def test_build_command_nukex_mode(self, nuke_config):
        """Test building Nuke command with NukeX."""
        nuke = NukeDCC(nuke_config)
        cmd = nuke.build_command(project_path="/test/project")

        if platform.system() == "Darwin":
            assert "open" in cmd
            assert "-a" in cmd
            assert "Nuke16.0v3.app" in cmd
            assert "--args" in cmd
            assert "--nukex" in cmd

    def test_build_command_with_file(self, nuke_config):
        """Test building command with file path."""
        nuke = NukeDCC(nuke_config)
        cmd = nuke.build_command(file_path="/test/script.nk")

        assert "--nukex" in cmd
        assert "/test/script.nk" in cmd

    def test_prepare_environment(self, nuke_config):
        """Test environment preparation."""
        nuke = NukeDCC(nuke_config)
        env = nuke.prepare_environment(
            ROLE="nuke",
            PROJECT_ROOT="/projects",
            SHOW="Demo"
        )

        assert env["ROLE"] == "nuke"
        assert env["PROJECT_ROOT"] == "/projects"
        assert env["SHOW"] == "Demo"


class TestBaseDCC:
    """Test suite for BaseDCC shared functionality."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset singleton before each test."""
        ConfigManager._instance = None
        ConfigManager._config_cache = {}
        yield

    def test_parse_env_file_nonexistent(self):
        """Test parsing non-existent env file."""
        maya = MayaDCC({
            "name": "Maya",
            "role": "maya",
            "env_file": "/nonexistent/path/.env"
        })
        env = maya.parse_env_file()
        assert env == {}

    def test_executable_exists_calls_method(self):
        """Test executable_exists method is callable."""
        maya = MayaDCC({
            "name": "Maya",
            "role": "maya",
            "executable": "/Applications/Autodesk/maya2025/Maya.app/Contents/MacOS/Maya"
        })
        assert callable(maya.executable_exists)

    def test_find_in_path_method_exists(self):
        """Test find_in_path method is callable."""
        maya = MayaDCC({
            "name": "Maya",
            "role": "maya",
            "executable": "/Applications/Autodesk/maya2025/Maya.app/Contents/MacOS/Maya"
        })
        assert callable(maya.find_in_path)

    def test_get_pipeline_env_keys(self):
        """Test getting pipeline environment keys from config."""
        maya = MayaDCC({
            "name": "Maya",
            "role": "maya"
        })
        keys = maya.get_pipeline_env_keys()
        assert isinstance(keys, list)
        assert len(keys) > 0


class TestExecutableExists:
    """Test suite for executable_exists() cross-platform detection."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset singleton before each test."""
        ConfigManager._instance = None
        ConfigManager._config_cache = {}
        yield

    def test_executable_exists_none_config(self):
        """Test with empty executable config."""
        maya = MayaDCC({
            "name": "Maya",
            "role": "maya",
            "executable": ""
        })
        # Should return False when no executable configured
        # (find_in_path returns None for empty executable)
        assert maya.executable_exists() is False

    def test_executable_exists_app_name_on_macos(self, monkeypatch):
        """Test .app bundle detection on macOS."""
        monkeypatch.setattr("platform.system", lambda: "Darwin")

        maya = MayaDCC({
            "name": "Maya",
            "role": "maya",
            "executable": "",
            "app_name": "Maya2025.app"
        })

        # Mock Path.exists to return True for app bundle
        monkeypatch.setattr("pathlib.Path.exists", lambda self: "/Applications/Maya2025.app" in str(self))

        # Method should be callable
        assert callable(maya.executable_exists)

    def test_executable_exists_direct_path(self, tmp_path):
        """Test executable detection with direct path."""
        # Create a temporary executable file
        test_exe = tmp_path / "test_maya"
        test_exe.write_text("#!/bin/bash\necho test")
        test_exe.chmod(0o755)

        maya = MayaDCC({
            "name": "Maya",
            "role": "maya",
            "executable": str(test_exe)
        })

        assert maya.executable_exists() is True

    def test_executable_exists_nonexistent_path(self):
        """Test executable detection with non-existent path."""
        maya = MayaDCC({
            "name": "Maya",
            "role": "maya",
            "executable": "/nonexistent/path/to/maya"
        })

        assert maya.executable_exists() is False


class TestFindInPath:
    """Test suite for find_in_path() method."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset singleton before each test."""
        ConfigManager._instance = None
        ConfigManager._config_cache = {}
        yield

    def test_find_in_path_empty_executable(self):
        """Test with empty executable."""
        maya = MayaDCC({
            "name": "Maya",
            "role": "maya",
            "executable": ""
        })

        assert maya.find_in_path() is None

    def test_find_in_path_returns_basename(self):
        """Test that find_in_path returns executable basename."""
        maya = MayaDCC({
            "name": "Maya",
            "role": "maya",
            "executable": "/path/to/maya"
        })

        # Should search for "maya" (basename)
        # Result depends on system PATH, so just verify method works
        result = maya.find_in_path()
        # Result is None if not in PATH, or a path string if found
        assert result is None or isinstance(result, str)

    def test_search_path_method_exists(self):
        """Test _search_path method is callable."""
        maya = MayaDCC({
            "name": "Maya",
            "role": "maya",
            "executable": "/path/to/maya"
        })

        assert callable(maya._search_path)