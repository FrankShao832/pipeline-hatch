"""Houdini DCC implementation."""

import os
import platform
from typing import Optional
from .base_dcc import BaseDCC


class HoudiniDCC(BaseDCC):
    """Houdini DCC application handler."""

    def build_command(
        self,
        file_path: Optional[str] = None,
        project_path: Optional[str] = None
    ) -> list[str]:
        """Build Houdini launch command.

        Args:
            file_path: Houdini scene file (.hip/.hipnc) to open.
            project_path: Houdini JOB directory.

        Returns:
            Command list for subprocess.
        """
        # Use 'open' command on macOS for proper GUI app launching
        if platform.system() == "Darwin" and self._app_name:
            cmd = ["open", "-a", self._app_name]
            if file_path:
                cmd.extend(["--args", file_path])
        else:
            cmd = [self._executable]
            if file_path:
                cmd.append(file_path)

        return cmd

    def prepare_environment(self, **kwargs) -> dict[str, str]:
        """Prepare environment for Houdini launch.

        Args:
            **kwargs: Pipeline context (ROLE, PROJECT_ROOT, SHOW, JOB, etc.)

        Returns:
            Environment variables dict.
        """
        env = {}

        # Set Houdini JOB variable (from config or runtime)
        job_from_config = self.env_vars_config.get("JOB", "")
        if job_from_config and "JOB" not in kwargs:
            env["JOB"] = job_from_config
        elif "JOB" in kwargs:
            env["JOB"] = str(kwargs["JOB"])
        elif project_path := kwargs.get("project_path"):
            env["JOB"] = project_path

        # Merge pipeline environment variables from config
        for key in self.get_pipeline_env_keys():
            if key in kwargs:
                env[key] = str(kwargs[key])

        return env