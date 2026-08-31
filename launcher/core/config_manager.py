"""Configuration management module.

Loads and manages YAML configuration files for DCC settings and project paths.
Supports per-machine local overrides via ``config/local.yaml`` (git-ignored):
any top-level section matching a config filename (e.g. ``dcc``, ``projects``)
is deep-merged over the shared config, so each machine can point at its own
DCC executables and project roots without forking the shared files.
"""

from pathlib import Path
from typing import Any

import yaml


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge ``override`` into ``base`` (override wins)."""
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


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
        """Load a YAML configuration file, merged with machine-local overrides.

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

        # ── Machine-local overrides (config/local.yaml, git-ignored) ──
        local_path = self._config_dir / "local.yaml"
        if local_path.exists():
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    local = yaml.safe_load(f) or {}
                section = local.get(filename)
                if section is not None:
                    if (
                        isinstance(config.get(filename), dict)
                        and isinstance(section, dict)
                    ):
                        # dict section (e.g. dcc): deep-merge into config[filename]
                        config[filename] = _deep_merge(
                            config[filename], section
                        )
                    else:
                        # non-dict section (e.g. projects list): replace wholesale
                        config[filename] = section
            except Exception:
                # Local override must never break startup; log and continue.
                from launcher.utils.logger import logger
                logger.warning(
                    f"Failed to apply local.yaml override for '{filename}'"
                )

        self._config_cache[filename] = config

        # Import logger here to avoid circular imports
        from launcher.utils.logger import logger
        if filename == "dcc":
            dcc_count = len(config.get("dcc", {}))
            logger.debug(f"DCC config loaded: {dcc_count} applications")
        elif filename == "projects":
            project_count = len(config.get("projects", []))
            logger.debug(f"Projects config loaded: {project_count} projects")

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
        from launcher.utils.logger import logger
        logger.info("Reloading all configurations")
        self._config_cache.clear()


# Singleton instance for easy access
config_manager = ConfigManager()