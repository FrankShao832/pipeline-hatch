"""Nuke DCC implementation."""

import os
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
            project_path: Working directory to open in (delivered as the
                process cwd, not as an argument — see ``launch_cwd``).

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
        else:
            # Nuke has no "project directory" switch. ``-m`` is the render
            # thread count (``-m n``), so handing it a path made Nuke 17 die
            # with SIGSEGV right after launch. Only pass the configured flag
            # when it is actually set — an empty value must not become a
            # dangling argument either.
            flag = self._flags.get("project") or ""
            if project_path and flag:
                cmd.extend([flag, project_path])

        return cmd

    def launch_cwd(self, project_path: Optional[str] = None) -> Optional[str]:
        """Open Nuke *in* the shot workdir by spawning it there.

        Nuke's file browser starts in the process working directory, which is
        the only way to make "open this shot's comp folder" work without a
        command-line flag.
        """
        if project_path and os.path.isdir(project_path):
            return project_path
        return None

    def prepare_environment(self, **kwargs) -> dict[str, str]:
        """Prepare environment for Nuke launch.

        Args:
            **kwargs: Pipeline context (DCC, DEPARTMENT, PROJECT_ROOT, SHOW, etc.)

        Returns:
            Environment variables dict.
        """
        env = {}

        # Merge pipeline environment variables from config
        for key in self.get_pipeline_env_keys():
            if key in kwargs:
                env[key] = str(kwargs[key])

        return env