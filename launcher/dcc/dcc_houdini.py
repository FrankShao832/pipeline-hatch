"""Houdini DCC implementation."""

from pathlib import Path
from typing import Optional

from launcher.core.config_manager import config_manager
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
        - PIPELINE_PUBLISHER: Publisher repo root (startup/menu/launcher resolve via it)
        - HOUDINI_STARTUP_PYTHON: Publisher startup script — installs the
          'Pipeline > Publish...' Qt menu at session start (primary path).
          MainMenuCommon.xml is NOT auto-discovered: no Houdini package json
          adds the publisher root to HOUDINI_PATH, so we don't inject it.
        - Pipeline env vars from config (ROLE, SHOW, SEQ, etc.)

        Tool paths follow the $DEV/tools/<repo> convention and are resolved
        through the ConfigManager (env var first, repo-layout inference in
        dev mode) — never via brittle ``__file__`` backtracking.

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

        # --- PIPELINE_PUBLISHER_ROOT ---
        # $DEV/tools/pipeline/pipeline_publisher — resolved by the publisher
        # startup/menu/launcher modules (env-var strategy, no __file__ tricks).
        publisher_root = (
            config_manager.dev_root / "tools" / "pipeline" / "pipeline_publisher"
        )
        env["PIPELINE_PUBLISHER"] = str(publisher_root)

        # --- HOUDINI_STARTUP_PYTHON (menu installation, primary path) ---
        # scripts/python/startup.py imports publisher.dcc.houdini.menu and
        # schedules the Qt 'Pipeline > Publish...' menu once the UI is ready.
        startup_path = publisher_root / "scripts" / "python" / "startup.py"
        if startup_path.exists():
            env["HOUDINI_STARTUP_PYTHON"] = str(startup_path)

        # --- Pipeline environment variables from config ---
        for key in self.get_pipeline_env_keys():
            if key in kwargs:
                env[key] = str(kwargs[key])

        return env
