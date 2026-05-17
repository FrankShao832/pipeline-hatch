"""Maya DCC implementation."""

import platform
from typing import Optional
from .base_dcc import BaseDCC


class MayaDCC(BaseDCC):
    """Maya DCC application handler."""

    def build_command(
        self,
        file_path: Optional[str] = None,
        project_path: Optional[str] = None
    ) -> list[str]:
        """Build Maya launch command.

        Args:
            file_path: Maya scene file (.ma/.mb) to open.
            project_path: Maya project directory.

        Returns:
            Command list for subprocess.
        """
        # Use 'open' command on macOS for proper GUI app launching
        if platform.system() == "Darwin" and self._app_name:
            cmd = ["open", "-a", self._app_name]
            if file_path:
                cmd.extend(["--args", "-file", file_path])
            elif project_path:
                cmd.extend(["--args", "-proj", project_path])
        else:
            cmd = [self._executable]
            if file_path:
                cmd.extend([self._flags.get("file", "-file"), file_path])
            elif project_path:
                cmd.extend([self._flags.get("project", "-proj"), project_path])

        return cmd

    def prepare_environment(self, **kwargs) -> dict[str, str]:
        """Prepare environment for Maya launch.

        Args:
            **kwargs: Pipeline context (ROLE, PROJECT_ROOT, SHOW, etc.)

        Returns:
            Environment variables dict.
        """
        # Start with Maya.env file if exists
        env = self.parse_env_file()

        # Merge pipeline environment variables from config
        for key in self.get_pipeline_env_keys():
            if key in kwargs:
                env[key] = str(kwargs[key])

        # Merge DCC-specific env vars from config
        for key, value in self.env_vars_config.items():
            if key in kwargs:
                env[key] = str(kwargs[key])

        return env