"""Nuke DCC implementation."""

import platform
from typing import Optional
from .base_dcc import BaseDCC


class NukeDCC(BaseDCC):
    """Nuke DCC application handler."""

    def build_command(
        self,
        file_path: Optional[str] = None,
        project_path: Optional[str] = None
    ) -> list[str]:
        """Build Nuke launch command.

        Args:
            file_path: Nuke script (.nk) to open.
            project_path: Nuke project directory.

        Returns:
            Command list for subprocess.
        """
        # Use direct executable path on all platforms.
        # macOS: avoid ``open -a`` which strips PATH passed via env=
        # and causes child processes (e.g. ffmpeg) to be unfindable.
        cmd = [self._executable]
        if self._flags.get("nukex"):
            cmd.append(self._flags["nukex"])
        if file_path:
            cmd.append(file_path)
        elif project_path:
            cmd.extend([self._flags.get("project", "-m"), project_path])

        return cmd

    def prepare_environment(self, **kwargs) -> dict[str, str]:
        """Prepare environment for Nuke launch.

        Args:
            **kwargs: Pipeline context (ROLE, PROJECT_ROOT, SHOW, etc.)

        Returns:
            Environment variables dict.
        """
        env = {}

        # Merge pipeline environment variables from config
        for key in self.get_pipeline_env_keys():
            if key in kwargs:
                env[key] = str(kwargs[key])

        return env