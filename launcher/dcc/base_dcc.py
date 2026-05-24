"""Base DCC class and interface definition."""

from abc import ABC, abstractmethod
from pathlib import Path
import platform
from typing import Optional

from launcher.core.config_manager import config_manager


class BaseDCC(ABC):
    """Abstract base class for all DCC applications.

    Each DCC (Maya, Houdini, Nuke) must implement these methods.
    """

    # Standard pipeline environment variables (loaded from config)
    PIPELINE_ENV_KEYS: list[str] = []

    def __init__(self, config: dict):
        """Initialize DCC with configuration.

        Args:
            config: DCC configuration dictionary from YAML.
        """
        self._config = config
        self._name = config.get("name", "")
        self._role = config.get("role", "")
        self._executable = config.get("executable", "")
        self._env_file = config.get("env_file", "")
        self._flags = config.get("flags", {})
        self._app_name = config.get("app_name", "")  # macOS app name for 'open -a'
        self._env_vars = config.get("env_vars", {})

        # Load pipeline env vars from config
        self._load_pipeline_env_keys()

    def _load_pipeline_env_keys(self):
        """Load pipeline environment variable keys from config."""
        try:
            dcc_config = config_manager.get_dcc_config()
            pipeline = dcc_config.get("pipeline", {})
            self.PIPELINE_ENV_KEYS = pipeline.get("env_vars", [])
        except Exception:
            self.PIPELINE_ENV_KEYS = []

    @property
    def name(self) -> str:
        """Return DCC display name."""
        return self._name

    @property
    def role(self) -> str:
        """Return DCC role identifier (maya, houdini, nuke)."""
        return self._role

    @property
    def executable(self) -> str:
        """Return path to DCC executable."""
        return self._executable

    @property
    def env_file(self) -> str:
        """Return path to environment file if exists."""
        return self._env_file

    @property
    def app_name(self) -> str:
        """Return macOS app name for 'open -a' command."""
        return self._app_name

    @property
    def env_vars_config(self) -> dict:
        """Return DCC-specific environment variables from config."""
        return self._env_vars

    def get_pipeline_env_keys(self) -> list[str]:
        """Get list of pipeline environment variable keys from config.

        Returns:
            List of environment variable names.
        """
        return self.PIPELINE_ENV_KEYS

    def executable_exists(self) -> bool:
        """Check if DCC executable exists.

        Searches in order:
        1. Direct executable path (most reliable)
        2. macOS /Applications/ .app bundle (flat layout, e.g. Maya.app)
        3. macOS /Applications/ nested .app bundle (Foundry layout, e.g. Nuke16.0v3/Nuke16.0v3.app)
        4. PATH environment variable (basename only)

        Returns:
            True if DCC is found, False otherwise.
        """
        system = platform.system()

        # 1. Direct executable path check (most reliable)
        if self._executable:
            if Path(self._executable).exists():
                return True

        # 2. macOS: Check /Applications/ for flat .app bundle
        if system == "Darwin" and self._app_name:
            app_path = Path(f"/Applications/{self._app_name}")
            if app_path.exists():
                return True

            # 3. macOS: Search for nested .app bundles (Foundry-style layout)
            # e.g. /Applications/Nuke16.0v3/Nuke16.0v3.app
            for entry in Path("/Applications").iterdir():
                if entry.is_dir():
                    nested_app = entry / self._app_name
                    if nested_app.exists():
                        return True
                    # Also check Contents/MacOS binary inside nested app
                    macos_binary = nested_app / "Contents" / "MacOS"
                    if macos_binary.exists():
                        return True

        # 4. Check in PATH (for executables like "maya", "houdini", "nuke")
        return self.find_in_path() is not None

    def find_in_path(self) -> Optional[str]:
        """Find DCC executable in system PATH.

        Looks for the executable by its basename in the PATH environment
        variable. Works on macOS, Linux, and Windows.

        Returns:
            Full path to executable if found, None otherwise.
        """
        if not self._executable:
            return None

        # Get executable name (basename without directory)
        exec_name = Path(self._executable).name

        # Add platform-specific extensions for Windows
        if platform.system() == "Windows":
            for ext in ["", ".exe", ".bat", ".cmd"]:
                candidate = self._search_path(exec_name + ext)
                if candidate:
                    return candidate
        else:
            candidate = self._search_path(exec_name)
            if candidate:
                return candidate

        return None

    def _search_path(self, name: str) -> Optional[str]:
        """Search for executable in PATH.

        Args:
            name: Executable name to search for.

        Returns:
            Full path if found, None otherwise.
        """
        import os

        path_sep = ";" if platform.system() == "Windows" else ":"
        path_env = os.environ.get("PATH", "")

        for directory in path_env.split(path_sep):
            candidate = Path(directory) / name
            # Check both exact file and executable bit
            if candidate.exists() and os.access(str(candidate), os.X_OK):
                return str(candidate)

        return None

    @abstractmethod
    def build_command(
        self,
        file_path: Optional[str] = None,
        project_path: Optional[str] = None
    ) -> list[str]:
        """Build the command line arguments for launching.

        Args:
            file_path: Optional file to open.
            project_path: Optional project/workspace path.

        Returns:
            List of command arguments.
        """
        pass

    @abstractmethod
    def prepare_environment(self, **kwargs) -> dict[str, str]:
        """Prepare environment variables for DCC launch.

        Args:
            kwargs: Additional environment context (ROLE, SHOW, etc.)

        Returns:
            Dictionary of environment variables.
        """
        pass

    def parse_env_file(self, env_path: Optional[str] = None) -> dict[str, str]:
        """Parse a .env style file.

        Args:
            env_path: Path to env file. Defaults to self._env_file.

        Returns:
            Dictionary of key-value pairs.
        """
        env_path = env_path or self._env_file
        if not env_path:
            return {}

        env_vars = {}
        path = Path(env_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or not line:
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        env_vars[key.strip()] = value.strip()

        return env_vars