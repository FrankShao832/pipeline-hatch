"""Tests for dcc_manager module."""

import pytest
from pathlib import Path
import sys

# Add launcher to path
sys.path.insert(0, str(Path(__file__).parent.parent / "launcher"))

from launcher.core.dcc_manager import DCCManager
from launcher.core.config_manager import ConfigManager


class TestDCCManager:
    """Test suite for DCCManager."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset singleton instances before each test."""
        ConfigManager._instance = None
        ConfigManager._config_cache = {}
        DCCManager._instance = None
        DCCManager._dcc_cache = {}
        yield

    def test_singleton_pattern(self):
        """Test that DCCManager is a singleton."""
        manager1 = DCCManager()
        manager2 = DCCManager()
        assert manager1 is manager2

    def test_get_available_dccs(self):
        """Test getting list of available DCCs."""
        manager = DCCManager()
        dccs = manager.get_available_dccs()

        assert isinstance(dccs, list)
        assert "maya" in dccs
        assert "houdini" in dccs
        assert "nuke" in dccs

    def test_get_dcc_maya(self):
        """Test getting Maya DCC."""
        manager = DCCManager()
        maya = manager.get_dcc("maya")

        assert maya is not None
        assert maya.name == "Maya"
        assert maya.role == "maya"

    def test_get_dcc_houdini(self):
        """Test getting Houdini DCC."""
        manager = DCCManager()
        houdini = manager.get_dcc("houdini")

        assert houdini is not None
        assert houdini.name == "Houdini"
        assert houdini.role == "houdini"

    def test_get_dcc_nuke(self):
        """Test getting Nuke DCC."""
        manager = DCCManager()
        nuke = manager.get_dcc("nuke")

        assert nuke is not None
        assert nuke.name == "Nuke"
        assert nuke.role == "nuke"

    def test_get_dcc_invalid_role(self):
        """Test getting invalid DCC role."""
        manager = DCCManager()
        dcc = manager.get_dcc("invalid")
        assert dcc is None

    def test_dcc_caching(self):
        """Test that DCC instances are cached."""
        manager = DCCManager()

        # First call
        maya1 = manager.get_dcc("maya")
        # Second call should return cached instance
        maya2 = manager.get_dcc("maya")

        assert maya1 is maya2

    def test_dcc_instance_reload(self):
        """Test that reload clears DCC cache."""
        manager = DCCManager()

        # Get DCC to populate cache
        maya1 = manager.get_dcc("maya")

        # Reload
        manager.reload()

        # Get again
        maya2 = manager.get_dcc("maya")

        # Should be a new instance
        assert maya1 is not maya2

    def test_list_all_configured_dccs(self):
        """Test listing all configured DCCs."""
        manager = DCCManager()
        dccs = manager.list_all_configured_dccs()

        assert isinstance(dccs, dict)
        assert "maya" in dccs
        assert "houdini" in dccs
        assert "nuke" in dccs

    def test_case_insensitive_role(self):
        """Test that role lookup is case insensitive."""
        manager = DCCManager()

        maya_lower = manager.get_dcc("maya")
        maya_upper = manager.get_dcc("MAYA")
        maya_mixed = manager.get_dcc("Maya")

        assert maya_lower is not None
        assert maya_upper is not None
        assert maya_mixed is not None
        assert maya_lower is maya_upper
        assert maya_upper is maya_mixed