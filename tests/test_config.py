"""Tests for config_manager module."""

import pytest
from pathlib import Path
import sys

# Add launcher to path
sys.path.insert(0, str(Path(__file__).parent.parent / "launcher"))

from launcher.core.config_manager import ConfigManager


class TestConfigManager:
    """Test suite for ConfigManager."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton instance before each test."""
        ConfigManager._instance = None
        ConfigManager._config_cache = {}
        yield

    def test_singleton_pattern(self):
        """Test that ConfigManager is a singleton."""
        manager1 = ConfigManager()
        manager2 = ConfigManager()
        assert manager1 is manager2

    def test_load_dcc_config(self):
        """Test loading DCC configuration."""
        manager = ConfigManager()
        config = manager.get_dcc_config()

        assert "dcc" in config
        assert "maya" in config["dcc"]
        assert "houdini" in config["dcc"]
        assert "nuke" in config["dcc"]

    def test_load_projects_config(self):
        """Test loading projects configuration."""
        manager = ConfigManager()
        config = manager.get_projects_config()

        assert "projects" in config

    def test_get_project_list(self):
        """Test getting project list."""
        manager = ConfigManager()
        projects = manager.get_project_list()

        assert isinstance(projects, list)
        assert len(projects) > 0
        assert "name" in projects[0]
        assert "root" in projects[0]
        assert "publish_root" in projects[0]

    def test_get_dcc_by_role(self):
        """Test getting DCC config by role."""
        manager = ConfigManager()

        maya_config = manager.get_dcc_by_role("maya")
        assert maya_config is not None
        assert maya_config["role"] == "maya"
        assert "executable" in maya_config
        assert "app_name" in maya_config

    def test_get_dcc_by_invalid_role(self):
        """Test getting DCC config with invalid role."""
        manager = ConfigManager()
        config = manager.get_dcc_by_role("invalid_dcc")
        assert config is None

    def test_config_caching(self):
        """Test that config is cached."""
        manager = ConfigManager()

        # First call
        config1 = manager.get_dcc_config()
        # Second call should return cached version
        config2 = manager.get_dcc_config()

        # Both should be the same object (cached)
        assert config1 is config2

    def test_reload_clears_cache(self):
        """Test that reload clears the cache."""
        manager = ConfigManager()

        # Load config to populate cache
        config1 = manager.get_dcc_config()

        # Reload
        manager.reload()

        # Load again
        config2 = manager.get_dcc_config()

        # Should be equal but not the same object (reloaded)
        assert config1 == config2

    def test_dcc_config_structure(self):
        """Test DCC config has expected structure."""
        manager = ConfigManager()
        config = manager.get_dcc_config()

        for role in ["maya", "houdini", "nuke"]:
            dcc = config["dcc"][role]
            assert "name" in dcc
            assert "role" in dcc
            assert "executable" in dcc
            assert "app_name" in dcc
            assert "flags" in dcc

    def test_pipeline_env_vars(self):
        """Test pipeline environment variables are loaded."""
        manager = ConfigManager()
        config = manager.get_dcc_config()

        assert "pipeline" in config
        assert "env_vars" in config["pipeline"]
        env_vars = config["pipeline"]["env_vars"]
        assert "ROLE" in env_vars
        assert "PROJECT_ROOT" in env_vars
        assert "SHOW" in env_vars