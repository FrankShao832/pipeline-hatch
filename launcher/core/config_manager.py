"""Configuration management module.

Loads and manages YAML configuration files for DCC settings and project paths.
Supports per-machine local overrides via a machine-local ``local.yaml``
(git-ignored in dev; ``~/.pipeline_hatch/config/local.yaml`` in frozen builds):

- any top-level section matching a config filename (e.g. ``dcc``, ``projects``)
  is deep-merged over the shared config (dict sections) or replaces it
  wholesale (list sections);
- ``$VAR`` / ``${VAR}`` placeholders in values are expanded against the
  process environment, so shared files may reference ``${DEV}`` and each
  machine resolves it to its own dev root without forking the shared files.

Design notes (2026-09-05, dual-machine parameterization):
- Shared files hold only platform-independent fields. Machine specifics
  (DCC ``executable``/``app_name``/``env_file``, DB credentials) live in
  ``config/local.yaml``; see ``config/local.yaml.example``.
- ``DEV`` = dev data root (macOS: ``/Volumes/Development``, Linux:
  ``/srv/share/dev``). It is read from the environment first; in dev mode it
  is inferred from the repo layout as a fallback so the launcher still runs
  without an exported ``DEV``.
- Frozen (PyInstaller) builds read shared files from the bundle
  (``sys._MEIPASS/config``) and machine-local overrides from the writable
  ``~/.pipeline_hatch/config/local.yaml``.
"""

import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# Matches $NAME and ${NAME} placeholders.
_ENV_PATTERN = re.compile(
    r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))"
)

# Subdirectory of $DEV holding pipeline tool repos.
_TOOLS_SUBDIR = "tools"


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


def _is_frozen() -> bool:
    """True when running inside a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


class ConfigManager:
    """Central configuration manager for all YAML config files."""

    _instance = None
    _config_cache: dict[str, dict] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if _is_frozen():
            # Shared files ship inside the bundle; machine-local overrides
            # must live somewhere the user can actually write to.
            bundle = getattr(sys, "_MEIPASS", Path(sys.executable).parent)
            self._config_dir = Path(bundle) / "config"
            self._local_dir = Path.home() / ".pipeline_hatch" / "config"
            self._local_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._config_dir = Path(__file__).parent.parent.parent / "config"
            self._local_dir = None  # fall back to _config_dir/local.yaml
        self._inferred_dev = None  # memoized repo-layout DEV inference

    # -- Directory resolution ------------------------------------------------

    def _local_config_path(self) -> Path:
        """Path of the machine-local override file.

        Tests may monkeypatch ``_config_dir`` only; when ``_local_dir`` is not
        set the local file is looked up next to the shared files, preserving
        the original ``config/local.yaml`` contract in dev mode.
        """
        base = self._local_dir or self._config_dir
        return Path(base) / "local.yaml"

    @property
    def config_dir(self) -> Path:
        """Directory holding the shared YAML files (read-only intent)."""
        return self._config_dir

    @property
    def local_config_path(self) -> Path:
        """Writable machine-local override file (used by Settings UI)."""
        return self._local_config_path()

    @property
    def dev_root(self) -> Path:
        """Resolve the $DEV dev-data root (see ``_resolve_dev``)."""
        return self._resolve_dev()

    def _resolve_dev(self) -> Path:
        """Resolve the $DEV dev-data root, warning at most once.

        Priority: ``DEV`` environment variable, then (dev mode only) inference
        from the repo layout ``<dev>/tools/pipeline/pipeline_hatch/launcher/core``.
        Frozen builds cannot infer an external path and must rely on ``DEV``.
        """
        env = os.environ.get("DEV")
        if env:
            return Path(env)
        # Repo-layout fallback (dev mode): config -> pipeline_hatch ->
        # pipeline -> tools -> <dev>
        inferred = self._config_dir.parent.parent.parent.parent
        if self._inferred_dev is None:
            self._inferred_dev = inferred
            from launcher.utils.logger import logger

            if not _is_frozen():
                logger.warning(
                    f"DEV is not set; inferred dev root from repo layout: {inferred}. "
                    "Export DEV (macOS: /Volumes/Development, Linux: /srv/share/dev) "
                    "for portability / frozen builds."
                )
            else:
                logger.warning(
                    "DEV is not set and this is a frozen build — dev-root "
                    "dependent features (publisher paths, KATANA_RESOURCES) "
                    "will not resolve."
                )
        return self._inferred_dev

    def tools_root(self) -> Path:
        """Return ``$DEV/tools`` (home of the pipeline tool repos)."""
        return self.dev_root / _TOOLS_SUBDIR

    # -- Loading -------------------------------------------------------------

    def _expand_value(self, value: str, extra: dict[str, str] | None = None) -> str:
        """Expand ``~`` and ``$VAR``/``${VAR}`` in a config string.

        Undefined variables are left verbatim so misconfiguration stays
        visible instead of silently collapsing to an empty path.

        Args:
            value: The raw string.
            extra: Per-context names (``SHOW``, ``SEQ``, …) that take precedence
                over the process environment — used by the settings layer, where
                an override may reference ``${SHOW}`` and the value has to show
                the way the launch will resolve it.
        """
        value = os.path.expanduser(value)

        def _replace(match):
            name = match.group(1) or match.group(2)
            if extra and name in extra:
                return extra[name]
            if name in os.environ:
                return os.environ[name]
            if name == "DEV":
                # Dev mode: fall back to the inferred repo-layout root so
                # ${DEV} paths still resolve without an exported DEV.
                return str(self._resolve_dev())
            return match.group(0)

        return _ENV_PATTERN.sub(_replace, value)

    def expand_value(self, value: str, extra: dict[str, str] | None = None) -> str:
        """Public form of :meth:`_expand_value` for callers outside the manager."""
        return self._expand_value(value, extra)

    def _expand(self, obj: Any) -> Any:
        """Recursively expand env placeholders through a loaded config tree."""
        if isinstance(obj, dict):
            return {key: self._expand(val) for key, val in obj.items()}
        if isinstance(obj, list):
            return [self._expand(item) for item in obj]
        if isinstance(obj, str):
            return self._expand_value(obj)
        return obj

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

        # ── Machine-local overrides (local.yaml, git-ignored) ──
        local_path = self._local_config_path()
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

        # ── Env-var expansion ($DEV, ${VAR}, ~) after merging ──
        config = self._expand(config)

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

    def get_database_config(self) -> dict[str, Any]:
        """Get database configuration (shared + local + env expansion)."""
        return self._load_yaml("database")

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
