"""Houdini DCC implementation."""

import os
import platform
from pathlib import Path
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

        Uses the Houdini executable directly (not `open -a` on macOS)
        so that environment variables set via subprocess.Popen(env=...)
        are properly inherited by the Houdini process.

        Args:
            file_path: Houdini scene file (.hip/.hipnc) to open.
            project_path: Houdini JOB directory (unused in command itself).

        Returns:
            Command list for subprocess.
        """
        cmd = [self._executable]
        if file_path:
            cmd.append(file_path)
        return cmd

    def prepare_environment(self, **kwargs) -> dict[str, str]:
        """Prepare environment for Houdini launch.

        Returns only the pipeline-specific overrides.
        Caller should merge with os.environ.copy() before use.

        Injects:
        - JOB: Houdini project directory
        - HOUDINI_PATH: Directory containing MainMenuCommon.xml for Pipeline menu
        - HOUDINI_STARTUP_PYTHON: Path to publisher startup script (safety net)
        - Pipeline env vars from config (ROLE, SHOW, SEQ, etc.)

        Args:
            **kwargs: Pipeline context (ROLE, PROJECT_ROOT, SHOW, JOB, etc.)

        Returns:
            Environment variables dict (overrides only).
        """
        env = {}

        # --- Houdini JOB ---
        job_from_config = self.env_vars_config.get("JOB", "")
        if job_from_config and "JOB" not in kwargs:
            env["JOB"] = job_from_config
        elif "JOB" in kwargs:
            env["JOB"] = str(kwargs["JOB"])
        elif project_path := kwargs.get("project_path"):
            env["JOB"] = project_path

        # Compute the pipeline_publisher directory path
        publisher_root = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "pipeline_publisher"
        )
        publisher_root_str = str(publisher_root)

        # --- PIPELINE_PUBLISHER_ROOT ---
        # Used by pipeline_publisher.json's $PIPELINE_PUBLISHER variable
        # in the hpath entry that points to this directory.
        publisher_root_str = str(publisher_root)
        env["PIPELINE_PUBLISHER"] = publisher_root_str

        # --- HOUDINI_STARTUP_PYTHON (optional safety net) ---
        # The menu is defined by MainMenuCommon.xml and loaded via the
        # pipeline_publisher.json package. HOUDINI_STARTUP_PYTHON is an
        # optional extra that ensures sys.path is set up.
        startup_path = publisher_root / "scripts" / "python" / "startup.py"
        if startup_path.exists():
            env["HOUDINI_STARTUP_PYTHON"] = str(startup_path)

        # --- HOUDINI_STARTUP_PYTHON (safety net) ---
        # The menu is driven by MainMenuCommon.xml, so HOUDINI_STARTUP_PYTHON
        # is only needed for additional initialization. If the file exists,
        # inject it as a safety net; if not, the menu still works via XML.
        startup_path = publisher_root / "scripts" / "python" / "startup.py"
        if startup_path.exists():
            env["HOUDINI_STARTUP_PYTHON"] = str(startup_path)

        # --- Pipeline environment variables from config ---
        for key in self.get_pipeline_env_keys():
            if key in kwargs:
                env[key] = str(kwargs[key])

        return env
