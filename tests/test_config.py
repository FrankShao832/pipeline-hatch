"""Tests for config_manager module.

Contract under test (2026-09-05 batch-1 parameterization):
- shared YAML files hold platform-independent fields only;
- DCC executable/app_name/env_file come from machine-local local.yaml;
- ${VAR} placeholders (e.g. ${DEV}) are expanded after merging.
"""

import pytest
import textwrap
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
        """Test getting DCC config by role (platform-independent fields)."""
        manager = ConfigManager()

        maya_config = manager.get_dcc_by_role("maya")
        assert maya_config is not None
        assert maya_config["role"] == "maya"
        # Machine-specific fields come from local.yaml; only structure is
        # guaranteed here.
        assert "flags" in maya_config
        assert "name" in maya_config

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
        """Shared DCC config guarantees platform-independent structure only."""
        manager = ConfigManager()
        config = manager.get_dcc_config()

        for role in ["maya", "houdini", "nuke"]:
            dcc = config["dcc"][role]
            assert "name" in dcc
            assert "role" in dcc
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

    def test_database_config_has_no_hardcoded_user(self):
        """Shared database.yaml must not hardcode a personal username."""
        manager = ConfigManager()
        config = manager.get_database_config()

        assert "database" in config
        db = config["database"]
        assert "user" not in db or not db.get("user")


class TestLocalOverride:
    """Tests for config/local.yaml machine-local overrides."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        ConfigManager._instance = None
        ConfigManager._config_cache = {}
        yield

    def test_deep_merge_dict(self, tmp_path, monkeypatch):
        """Dict sections (dcc) are deep-merged into the shared config."""
        import shutil
        from launcher.core.config_manager import ConfigManager

        src = Path(__file__).parent.parent / "config"
        shutil.copy(src / "dcc.yaml", tmp_path / "dcc.yaml")
        shutil.copy(src / "projects.yaml", tmp_path / "projects.yaml")
        (tmp_path / "local.yaml").write_text(
            textwrap.dedent(
                """\
                dcc:
                  houdini:
                    executable: /opt/hfs20.5/bin/houdini
                """
            )
        )

        mgr = ConfigManager()
        monkeypatch.setattr(mgr, "_config_dir", tmp_path)
        cfg = mgr._load_yaml("dcc")
        assert cfg["dcc"]["houdini"]["executable"] == "/opt/hfs20.5/bin/houdini"
        # untouched sibling preserved
        assert "nuke" in cfg["dcc"]

    def test_local_provides_machine_paths(self, tmp_path, monkeypatch):
        """local.yaml supplies the executable/app_name shared YAML dropped."""
        import shutil
        from launcher.core.config_manager import ConfigManager

        src = Path(__file__).parent.parent / "config"
        shutil.copy(src / "dcc.yaml", tmp_path / "dcc.yaml")
        shutil.copy(src / "projects.yaml", tmp_path / "projects.yaml")
        (tmp_path / "local.yaml").write_text(
            textwrap.dedent(
                """\
                dcc:
                  maya:
                    app_name: Maya2026.app
                    executable: /Applications/Autodesk/maya2026/Maya.app/Contents/MacOS/Maya
                """
            )
        )

        mgr = ConfigManager()
        monkeypatch.setattr(mgr, "_config_dir", tmp_path)
        cfg = mgr._load_yaml("dcc")
        maya = cfg["dcc"]["maya"]
        assert maya["app_name"] == "Maya2026.app"
        assert maya["executable"].endswith("/Maya")
        # other DCCs are untouched and still lack machine fields
        assert "executable" not in cfg["dcc"]["nuke"]

    def test_env_expansion_dev(self, tmp_path, monkeypatch):
        """${DEV} placeholders expand from the environment after merging."""
        import shutil
        from launcher.core.config_manager import ConfigManager

        monkeypatch.setenv("DEV", "/fake/dev/root")
        src = Path(__file__).parent.parent / "config"
        shutil.copy(src / "dcc.yaml", tmp_path / "dcc.yaml")
        shutil.copy(src / "projects.yaml", tmp_path / "projects.yaml")

        mgr = ConfigManager()
        monkeypatch.setattr(mgr, "_config_dir", tmp_path)
        cfg = mgr._load_yaml("projects")
        root = cfg["projects"][0]["root"]
        assert root.startswith("/fake/dev/root/projects/")
        assert "${DEV}" not in root

    def test_env_expansion_undefined_left_verbatim(self, tmp_path, monkeypatch):
        """Unknown variables are left visible instead of collapsing."""
        import shutil
        from launcher.core.config_manager import ConfigManager

        monkeypatch.delenv("DEV", raising=False)
        src = Path(__file__).parent.parent / "config"
        shutil.copy(src / "dcc.yaml", tmp_path / "dcc.yaml")
        shutil.copy(src / "projects.yaml", tmp_path / "projects.yaml")
        (tmp_path / "local.yaml").write_text(
            textwrap.dedent(
                """\
                projects:
                  - name: Tmp
                    root: "${UNKNOWN_VAR}/projects/x"
                    publish_root: "${UNKNOWN_VAR}/projects/y"
                    enabled: true
                """
            )
        )

        mgr = ConfigManager()
        monkeypatch.setattr(mgr, "_config_dir", tmp_path)
        cfg = mgr._load_yaml("projects")
        root = cfg["projects"][0]["root"]
        # left verbatim — visible misconfiguration rather than an empty path
        assert "${UNKNOWN_VAR}" in root

    def test_env_expansion_dev_inferred_when_unset(self, tmp_path, monkeypatch):
        """Without DEV env, ${DEV} falls back to the inferred dev root."""
        import shutil
        from launcher.core.config_manager import ConfigManager

        monkeypatch.delenv("DEV", raising=False)
        src = Path(__file__).parent.parent / "config"
        shutil.copy(src / "dcc.yaml", tmp_path / "dcc.yaml")
        shutil.copy(src / "projects.yaml", tmp_path / "projects.yaml")

        mgr = ConfigManager()
        monkeypatch.setattr(mgr, "_config_dir", tmp_path)
        cfg = mgr._load_yaml("projects")
        root = cfg["projects"][0]["root"]
        # expanded (dev-mode inference) rather than left as a literal
        assert "${DEV}" not in root
        assert root.startswith("/")

    def test_replace_list(self, tmp_path, monkeypatch):
        """List sections (projects) are replaced wholesale."""
        import shutil
        from launcher.core.config_manager import ConfigManager

        src = Path(__file__).parent.parent / "config"
        shutil.copy(src / "dcc.yaml", tmp_path / "dcc.yaml")
        shutil.copy(src / "projects.yaml", tmp_path / "projects.yaml")
        (tmp_path / "local.yaml").write_text(
            textwrap.dedent(
                """\
                projects:
                  - name: LinuxOnly
                    root: /srv/share/dev/projects/x
                    publish_root: /srv/share/dev/projects/y
                    enabled: true
                """
            )
        )

        mgr = ConfigManager()
        monkeypatch.setattr(mgr, "_config_dir", tmp_path)
        cfg = mgr._load_yaml("projects")
        assert [p["name"] for p in cfg["projects"]] == ["LinuxOnly"]

    def test_no_local_file(self, tmp_path, monkeypatch):
        """Without local.yaml, shared config loads unchanged."""
        import shutil
        from launcher.core.config_manager import ConfigManager

        src = Path(__file__).parent.parent / "config"
        shutil.copy(src / "dcc.yaml", tmp_path / "dcc.yaml")
        shutil.copy(src / "projects.yaml", tmp_path / "projects.yaml")

        mgr = ConfigManager()
        monkeypatch.setattr(mgr, "_config_dir", tmp_path)
        cfg = mgr._load_yaml("dcc")
        assert "maya" in cfg["dcc"]
        assert "houdini" in cfg["dcc"]
        assert "nuke" in cfg["dcc"]
