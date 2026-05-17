"""Configuration management module.

Loads and manages YAML configuration files for DCC settings and project paths.
"""

from pathlib import Path
from typing import Any

import yaml


class ConfigManager:
    """Central configuration manager for all YAML config files."""

    _instance = None
    _config_cache: dict[str, dict] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._config_dir = Path(__file__).parent.parent.parent / "config"

    def _load_yaml(self, filename: str) -> dict[str, Any]:
        """Load a YAML configuration file.

        Args:
            filename: Name of the YAML file (without .yaml extension).

        Returns:
            Dictionary containing the parsed configuration.
        """
        if filename in self._config_cache:
            return self._config_cache[filename]

        config_path = self._config_dir / f"{filename}.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        self._config_cache[filename] = config
        return config

    def get_dcc_config(self) -> dict[str, Any]:
        """Get DCC configuration."""
        return self._load_yaml("dcc")

    def get_projects_config(self) -> dict[str, Any]:
        """Get projects configuration."""
        return self._load_yaml("projects")

    def get_project_list(self) -> list[dict[str, Any]]:
        """Get list of configured projects.

        Returns:
            List of project dictionaries with name, root, and publish_root.
        """
        config = self.get_projects_config()
        return config.get("projects", [])

    def get_dcc_by_role(self, role: str) -> dict[str, Any] | None:
        """Get DCC configuration by role.

        Args:
            role: DCC role name (maya, houdini, nuke).

        Returns:
            DCC configuration dictionary or None if not found.
        """
        dcc_config = self.get_dcc_config()
        dcc_list = dcc_config.get("dcc", {})
        return dcc_list.get(role)

    def reload(self):
        """Clear cache and reload all configurations."""
        self._config_cache.clear()


# Singleton instance for easy access
config_manager = ConfigManager()