"""Katana DCC implementation.

Katana is Linux-only (runs on the backup/render machine). Unlike Maya,
we always launch the executable directly (not `open -a`) so environment
variables set via subprocess.Popen(env=...) are inherited properly.
"""

from pathlib import Path
from typing import Optional

from .base_dcc import BaseDCC


class KatanaDCC(BaseDCC):
    """Katana DCC application handler."""

    def build_command(
        self,
        file_path: Optional[str] = None,
        project_path: Optional[str] = None
    ) -> list[str]:
        """Build Katana launch command.

        Katana is launched by its binary directly:
          katanaBin [file.katana]

        Args:
            file_path: Katana scene file (.katana) to open.
            project_path: Katana project/workspace directory (unused in
                          the command itself; Katana has no -proj flag).

        Returns:
            Command list for subprocess.
        """
        cmd = [self._executable]
        if file_path:
            cmd.append(file_path)
        return cmd

    def prepare_environment(self, **kwargs) -> dict[str, str]:
        """Prepare environment for Katana launch.

        Returns only the pipeline-specific overrides; the caller merges
        with os.environ.copy() before use.

        Injects:
        - KATANA_RESOURCES: Katana plugin/resource search path pointing
          at $DEV/tools/katana if it exists (same convention as
          HOUDINI_PATH for Houdini).
        - Pipeline env vars from config (ROLE, PROJECT_ROOT, SHOW, etc.)

        Args:
            **kwargs: Pipeline context (ROLE, PROJECT_ROOT, SHOW, JOB, etc.)

        Returns:
            Environment variables dict (overrides only).
        """
        env = {}

        # --- KATANA_RESOURCES (optional) ---
        # Follows the $DEV/tools/<dcc> convention from the dual-machine
        # design: any tools/katana dir is appended to KATANA_RESOURCES.
        tools_katana = (
            Path(__file__).resolve().parent.parent.parent.parent / "katana"
        )
        if tools_katana.is_dir():
            env["KATANA_RESOURCES"] = str(tools_katana)

        # --- Pipeline environment variables from config ---
        for key in self.get_pipeline_env_keys():
            if key in kwargs:
                env[key] = str(kwargs[key])

        return env
