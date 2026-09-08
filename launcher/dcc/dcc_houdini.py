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
        Menu note: the 'Pipeline > Publish...' menu is NOT installed here.
        It comes from the package at
        ~/Library/Preferences/houdini/20.5/packages/pipeline_publisher.json
        whose hpath puts the publisher root on HOUDINI_PATH, so Houdini
        merges its MainMenuCommon.xml natively. A Qt injection via
        HOUDINI_STARTUP_PYTHON was tried and removed (2026-09-08): Houdini
        20.5's menu bar is not reliably editable via findChild(QMenuBar).
        - Pipeline env vars from config (ROLE, SHOW, SEQ, etc.)

        Tool paths follow the $DEV/tools/<repo> convention and are resolved
        through the ConfigManager (env var first, repo-layout inference in
        dev mode) — never via brittle ``__file__`` backtracking.

        Args:
            **kwargs: Pipeline context (DCC, DEPARTMENT, PROJECT_ROOT, SHOW, JOB, etc.)

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

        # --- Pipeline environment variables from config ---
        for key in self.get_pipeline_env_keys():
            if key in kwargs:
                env[key] = str(kwargs[key])

        return env
