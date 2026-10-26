#!/usr/bin/env python3
"""Cross-platform thin launcher for Pipeline Hatch (plan U1.5 ③).

Locates the project-scoped env and runs the app **from the repo**, so a
double-click always executes the current working tree instead of a stale
PyInstaller bundle (whose ``datas`` whitelist silently drops ``config/env.yaml``).

    macOS   Pipeline Hatch.app/Contents/MacOS/pipeline-hatch -> launch.py
    Linux   Pipeline Hatch.desktop  Exec=/usr/bin/python3 .../launch.py
    Windows PipelineHatch.bat -> pythonw launch.py

Layout expectation (relative to this file):

    <project root>/launcher/launch.py
    <project root>/env/bin/python                      (macOS / Linux)
    <project root>/env/bin/pipeline-hatch              (console entry point)
    <project root>/env/Scripts/{pythonw,python}.exe    (Windows)
    <project root>/env/Scripts/pipeline-hatch.exe      (Windows entry point)

Design rules
------------
- **Stdlib only (Python 3.8+)**: the desktop shells may invoke whatever
  ``python3`` the OS happens to have; it must not need PySide6 to get going.
- **No hard-coded machine paths**: the project root is derived from ``__file__``,
  so the same tree works on the Mac development volume and on the Linux mirror.
- **Entry point first, module fallback**: prefer the installed
  ``pipeline-hatch`` console script, otherwise
  ``[env python, "-m", "launcher.main"]``. The fallback keeps the tool usable
  without ``pip install -e .``.
- **A broken entry point is not a launch failure**: these project envs were
  copied between machines, so ``env/bin/*`` may carry a shebang pointing at a
  path that no longer exists (the retired development volume). Such an entry
  point is detected and skipped in favour of the module fallback.
- **Never fail silently**: launched from Finder/dock there is no terminal, so a
  missing env or interpreter raises a GUI alert (osascript / zenity / MessageBox)
  and also writes to stderr.
- On Unix the launcher replaces itself via ``os.execv`` so no stray intermediate
  python process lingers in the process tree.

Debugging
---------
``python3 launcher/launch.py --print-command`` prints the command line it would
exec and exits 0 — use it to verify a desktop shell without opening the GUI.
"""

import os
import subprocess
import sys
from pathlib import Path

APP_NAME = "Pipeline Hatch"
ENTRY_POINT = "pipeline-hatch"
PACKAGE_MODULE = "launcher.main"


# -- Location ---------------------------------------------------------------


def project_root() -> Path:
    """Project root = parent of the ``launcher/`` directory holding this file."""
    return Path(__file__).resolve().parents[1]


def env_dir(root: Path) -> Path:
    return root / "env"


def env_python(root: Path):
    """Return the project env interpreter, or ``None`` when it is missing."""
    if os.name == "nt":
        candidates = [
            root / "env" / "Scripts" / "pythonw.exe",
            root / "env" / "Scripts" / "python.exe",
        ]
    else:
        candidates = [root / "env" / "bin" / "python"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _shebang_usable(path: Path) -> bool:
    """True when ``path`` is executable *as a program* on this machine.

    Returns False for scripts whose shebang interpreter does not exist -- the
    classic "env copied between machines, shebang still points at the long-gone
    development volume" failure. Files without a shebang are left to the OS to
    reject.
    """
    if os.name == "nt":
        return True
    try:
        with path.open("rb") as handle:
            first = handle.readline(256)
    except OSError:
        return False
    if not first.startswith(b"#!"):
        return True
    parts = first[2:].decode("utf-8", "replace").strip().split()
    if not parts:
        return False
    interpreter = parts[0]
    if interpreter.endswith("/env"):  # "#!/usr/bin/env python3" -> PATH lookup
        return True
    return Path(interpreter).exists()


def entry_script(root: Path):
    """Return the installed console entry point, or ``None`` when unusable."""
    if os.name == "nt":
        candidates = [
            root / "env" / "Scripts" / f"{ENTRY_POINT}.exe",
            root / "env" / "Scripts" / f"{ENTRY_POINT}.py",
        ]
    else:
        candidates = [root / "env" / "bin" / ENTRY_POINT]
    for candidate in candidates:
        if candidate.is_file() and _shebang_usable(candidate):
            return candidate
    return None


# -- Failure reporting ------------------------------------------------------


def alert(message: str) -> None:
    """Best-effort GUI alert (desktop launch has no terminal)."""
    try:
        if sys.platform == "darwin":
            safe = message.replace('"', "'").replace("\n", "\\n")
            subprocess.run(
                ["osascript", "-e",
                 'display dialog "' + safe + '" with title "'
                 + APP_NAME + '" buttons {"OK"} default button "OK"'],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif os.name == "nt":
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)
        else:
            subprocess.run(
                ["zenity", "--error", "--no-wrap", "--text", message],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass  # headless box: no GUI alert possible
    print(f"[{APP_NAME}] {message}", file=sys.stderr)


# -- Command assembly -------------------------------------------------------


def build_command(root: Path):
    """Assemble the launch command, or ``None`` when the env is unusable."""
    exe = env_python(root)
    if exe is None:
        return None
    entry = entry_script(root)
    if entry is not None:
        return [str(entry)]
    # Fallback: run the package entry module with the env interpreter.
    return [str(exe), "-m", PACKAGE_MODULE]


def _shell_cmd(argv) -> str:
    """Human-readable one-liner (for --print-command and log lines)."""
    out = []
    for item in argv:
        out.append(f'"{item}"' if " " in item else item)
    return " ".join(out)


# -- Entry ------------------------------------------------------------------


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    print_command = "--print-command" in args
    if print_command:
        args = [item for item in args if item != "--print-command"]

    root = project_root()

    if not env_dir(root).is_dir():
        alert(
            "Pipeline Hatch project env not found.\n\n"
            "Is the project volume mounted?\nExpected: "
            + str(env_dir(root))
        )
        return 1

    command = build_command(root)
    if command is None:
        alert(
            "Python interpreter missing inside the project env.\n\n"
            "Expected: "
            + str(env_dir(root) / ("Scripts" if os.name == "nt" else "bin"))
        )
        return 1

    argv_final = command + args

    if print_command:
        print(f"root: {root}")
        print(f"cmd:  {_shell_cmd(argv_final)}")
        return 0

    # Config/log paths are resolved from __file__ / $HOME, but the DB and any
    # user-supplied relative argument should still behave as if started from
    # the project root (Finder launches apps with cwd "/").
    try:
        os.chdir(root)
    except OSError:
        pass

    if os.name != "nt":
        try:
            # Replace this process: correct Dock identity and signal handling.
            os.execv(argv_final[0], argv_final)
        except OSError as exc:
            alert(f"Failed to launch {APP_NAME}:\n{exc}")
            return 1

    # Windows has no usable execv for GUI apps: spawn and relay the exit code.
    try:
        return subprocess.call(argv_final)
    except OSError as exc:
        alert(f"Failed to launch {APP_NAME}:\n{exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
