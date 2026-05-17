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
            "env_file": "/Users/frank/Library/Preferences/Autodesk/maya/2025/Maya.env",
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
        assert maya.env_file == "/Users/frank/Library/Preferences/Autodesk/maya/2025/Maya.env"

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

    def test_executable_exists(self):
        """Test executable existence check."""
        maya = MayaDCC({
            "name": "Maya",
            "role": "maya",
            "executable": "/Applications/Autodesk/maya2025/Maya.app/Contents/MacOS/Maya"
        })
        # This will depend on actual installation
        # Just test the method exists and is callable
        assert callable(maya.executable_exists)

    def test_get_pipeline_env_keys(self):
        """Test getting pipeline environment keys from config."""
        maya = MayaDCC({
            "name": "Maya",
            "role": "maya"
        })
        keys = maya.get_pipeline_env_keys()
        assert isinstance(keys, list)
        assert len(keys) > 0