"""Entry-point tests (plan U1.5 ②: the launcher must be runnable as a file).

``python launcher/main.py`` puts ``launcher/`` on ``sys.path[0]`` instead of the
repo root, so ``import launcher.*`` fails unless main.py bootstraps the path.
This was a real bug: the README advertised the form and it raised
``ModuleNotFoundError: No module named 'launcher'``.

The test executes main.py in a subprocess with script-mode path semantics but
with ``__name__ != "__main__"``, so the GUI is never started.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "launcher" / "main.py"

_PROBE = (
    "import sys, importlib.util\n"
    "sys.path.pop(0)\n"                       # drop the cwd entry of -c mode
    "sys.path.insert(0, 'launcher')\n"        # script mode: sys.path[0] = launcher/
    "spec = importlib.util.spec_from_file_location('hatch_main_probe', 'launcher/main.py')\n"
    "mod = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(mod)\n"          # __name__ != '__main__' -> no GUI
    "assert callable(mod.main)\n"
    "print('ok')\n"
)


def test_main_py_imports_in_script_mode():
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(ROOT), capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, (
        "launcher/main.py cannot be run directly:\n"
        f"stdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert "ok" in proc.stdout


def test_main_py_has_no_import_side_effects():
    """Importing the module must not create a QApplication or touch the DB."""
    probe = (
        "import sys\n"
        "sys.path.insert(0, '.')\n"
        "import launcher.main as m\n"
        "from PySide6.QtWidgets import QApplication\n"
        "assert QApplication.instance() is None\n"
        "print('clean')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(ROOT), capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "clean" in proc.stdout


def test_app_naming_separates_series_and_tool():
    """Y Pipeline is the series, Pipeline Hatch is this tool."""
    source = MAIN.read_text(encoding="utf-8")
    assert 'setApplicationName("Pipeline Hatch")' in source
    assert 'setOrganizationName("Y Pipeline")' in source
    assert 'setApplicationName("Y Pipeline")' not in source
    window_source = (ROOT / "launcher" / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert 'setWindowTitle("Pipeline Hatch")' in window_source
