"""Nuke DCC implementation."""

import os
import platform
import tempfile
from typing import Optional

from launcher.utils.logger import logger

from .base_dcc import BaseDCC

#: Version a shot's script starts at when the folder has none yet. The stem is
#: ``<shot>_v001.nk`` — what the existing shot folders already use
#: (``dl_for_0020_v001.nk``, ``demo_shot_v001.nk``); the department is the
#: folder, so it stays out of the file name.
SCRIPT_VERSION = 1

#: Frame rate written into a new script when the launch context carries none.
DEFAULT_FPS = "24"

#: Reference resolution for a new script. Nothing in the pipeline context
#: describes a format yet, so this is deliberately Nuke's own default.
DEFAULT_FORMAT = "1920 1080 0 0 1920 1080 1 HD_1080"

_SCRIPT_SUFFIX = ".nk"


def _normalise_fps(fps: str) -> str:
    """Return *fps* as Nuke script text, or :data:`DEFAULT_FPS` when unusable."""
    try:
        value = float(str(fps))
    except (TypeError, ValueError):
        return DEFAULT_FPS
    if value <= 0:
        return DEFAULT_FPS
    return f"{value:g}"


def find_newest_script(workdir: str) -> Optional[str]:
    """Newest ``.nk`` directly inside *workdir*, or ``None``.

    "Newest" is mtime, with the name breaking ties. Only the folder itself is
    scanned: department folders are flat by convention, and walking down would
    sooner pick up a backup script from a subfolder than the artist's work.
    """
    if not workdir or not os.path.isdir(workdir):
        return None

    found: list[tuple[float, str]] = []
    try:
        with os.scandir(workdir) as entries:
            for entry in entries:
                if not entry.name.lower().endswith(_SCRIPT_SUFFIX):
                    continue
                if not entry.is_file():
                    continue
                try:
                    found.append((entry.stat().st_mtime, entry.path))
                except OSError:
                    continue
    except OSError:
        return None

    if not found:
        return None
    found.sort()
    return found[-1][1]


def script_text(script_path: str, fps: str = "") -> str:
    """Text of a minimal Nuke script that opens *script_path* from its folder.

    Verified against Nuke 17.0v4 (``Nuke17.0 -t <file> -x``): the file loads
    without error and ``nuke.root().fps()`` comes back as the value written
    here. ``Root.name`` is the load-bearing line — ``nuke.script_directory()``
    is the dirname of the open script, and that is where File > Save As starts.

    Args:
        script_path: Absolute path of the script being created.
        fps: ``FPS`` from the launch context; non-numeric falls back to
            :data:`DEFAULT_FPS`.

    Returns:
        The script text.
    """
    return (
        "Root {\n"
        " inputs 0\n"
        f" name {script_path}\n"
        " frame 1\n"
        f" fps {_normalise_fps(fps)}\n"
        f' format "{DEFAULT_FORMAT}"\n'
        "}\n"
    )


def ensure_startup_script(workdir: str, shot: str, fps: str = "") -> Optional[str]:
    """The script Nuke should open so that its save dialog lands in *workdir*.

    Resolution order:

    1. any ``.nk`` in the folder → the newest one, never touched;
    2. none → create ``<shot>_v001.nk`` and return it;
    3. no shot name / no folder / write failed → ``None``, so Nuke launches
       bare. A wrong script would be worse than none.

    The file is written through a temporary name and ``os.replace``, so Nuke
    can never be handed a half-written script.

    Args:
        workdir: Department folder resolved for the shot.
        shot: Shot name (``SHOT``); empty means "do not invent a file name".
        fps: ``FPS`` from the launch context.

    Returns:
        Path of the script to open, or ``None``.
    """
    if not workdir or not os.path.isdir(workdir):
        return None

    newest = find_newest_script(workdir)
    if newest:
        return newest

    if not shot:
        logger.info(f"Nuke startup script skipped: no shot name for {workdir}")
        return None

    path = os.path.join(workdir, f"{shot}_v{SCRIPT_VERSION:03d}{_SCRIPT_SUFFIX}")
    if os.path.exists(path):
        return path

    tmp_path: Optional[str] = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=workdir, prefix=".nuke_startup_", suffix=".nk.tmp"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(script_text(path, fps))
        os.replace(tmp_path, path)
    except OSError as exc:
        logger.warning(f"Could not create Nuke startup script {path}: {exc}")
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return None

    logger.info(f"Created Nuke startup script: {path}")
    return path


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

    def startup_script(self, workdir: Optional[str] = None, **context) -> Optional[str]:
        """Open (or create) the script that anchors Nuke inside the workdir.

        Nuke has no project switch and no ``$JOB``: unlike Houdini, whose
        ``JOB`` names the folder, Nuke's "project folder" *is* the folder of the
        open script — ``nuke.script_directory()`` is what File > Save As starts
        from, and it is empty until something is open. Launching Nuke with
        nothing open therefore drops the artist into Nuke's own last-used
        folder, which is how a save ended up outside the shot.

        Args:
            workdir: Department folder resolved for this shot.
            **context: ``shot`` / ``fps`` from the launch context.

        Returns:
            Path of the script to open, or ``None`` to launch bare Nuke.
        """
        return ensure_startup_script(
            workdir or "",
            str(context.get("shot") or ""),
            str(context.get("fps") or ""),
        )

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