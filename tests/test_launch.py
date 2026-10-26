"""Thin-shell tests (plan U1.5 ③: desktop launch runs the working tree).

Covers the resolution rules in ``launcher/launch.py``:

- entry point first, module fallback second;
- an entry point whose shebang interpreter is gone (env copied between
  machines) must fall back instead of raising;
- missing env / missing interpreter => ``None`` (the caller raises a GUI alert);
- the three platform shells exist, carry exactly one machine-specific path and
  actually delegate to ``launch.py``.
"""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

import launch

ROOT = Path(__file__).resolve().parents[1]
LAUNCH_PY = ROOT / "launcher" / "launch.py"
MAC_APP = ROOT / "launcher" / "macos" / "Pipeline Hatch.app"
LINUX_ENTRY = ROOT / "launcher" / "linux" / "Pipeline Hatch.desktop"
WIN_SHELL = ROOT / "launcher" / "windows" / "PipelineHatch.bat"


def _fake_env(root: Path, entry: str | None = None) -> Path:
    """Build a throw-away ``<root>/env`` layout; returns the root."""
    bin_dir = root / "env" / "bin"
    bin_dir.mkdir(parents=True)
    py = bin_dir / "python"
    py.write_text("#!/bin/sh\n")
    py.chmod(0o755)
    if entry is not None:
        script = bin_dir / "pipeline-hatch"
        script.write_text(entry + "\n")
        script.chmod(0o755)
    return root


# -- Location ---------------------------------------------------------------


def test_project_root_is_repo_root():
    assert launch.project_root() == ROOT
    assert (launch.project_root() / "pyproject.toml").is_file()


def test_real_project_env_interpreter_is_found():
    exe = launch.env_python(ROOT)
    assert exe is not None, "project env interpreter missing"
    assert exe.is_file()
    assert str(exe).startswith(str(ROOT))


# -- Resolution order -------------------------------------------------------


def test_entry_point_is_preferred_when_installed(tmp_path):
    root = _fake_env(tmp_path, entry="#!/bin/sh")
    assert launch.entry_script(root) == root / "env" / "bin" / "pipeline-hatch"
    assert launch.build_command(root) == [str(root / "env" / "bin" / "pipeline-hatch")]


def test_module_fallback_when_entry_point_missing(tmp_path):
    root = _fake_env(tmp_path)
    assert launch.entry_script(root) is None
    assert launch.build_command(root) == [
        str(root / "env" / "bin" / "python"), "-m", "launcher.main",
    ]


def test_broken_shebang_entry_point_falls_back(tmp_path):
    """Regression pin: env copied from a machine whose python path is gone."""
    root = _fake_env(tmp_path, entry="#!/nonexistent/void/python3")
    assert launch._shebang_usable(root / "env" / "bin" / "pipeline-hatch") is False
    assert launch.entry_script(root) is None
    assert launch.build_command(root) == [
        str(root / "env" / "bin" / "python"), "-m", "launcher.main",
    ]


def test_env_style_shebang_is_usable(tmp_path):
    root = _fake_env(tmp_path, entry="#!/usr/bin/env python3")
    assert launch._shebang_usable(root / "env" / "bin" / "pipeline-hatch") is True
    assert launch.build_command(root)[0].endswith("pipeline-hatch")


def test_missing_env_returns_none(tmp_path):
    (tmp_path / "launcher").mkdir()
    assert launch.env_python(tmp_path) is None
    assert launch.build_command(tmp_path) is None


def test_env_without_interpreter_returns_none(tmp_path):
    (tmp_path / "env" / "bin").mkdir(parents=True)
    assert launch.env_python(tmp_path) is None
    assert launch.build_command(tmp_path) is None


def test_missing_env_alerts_and_exits_1(tmp_path, monkeypatch):
    """main() on an env-less root must alert and exit 1, never traceback."""
    alerts = []
    monkeypatch.setattr(launch, "project_root", lambda: tmp_path)
    monkeypatch.setattr(launch, "alert", alerts.append)
    assert launch.main(["--print-command"]) == 1
    assert alerts and "env not found" in alerts[0]


def test_alert_never_raises(capsys, monkeypatch):
    """No notifier available (headless Linux) must not break the exit path."""
    def boom(*args, **kwargs):
        raise OSError("no notifier")

    monkeypatch.setattr(launch.subprocess, "run", boom)
    launch.alert("no notifier here")  # raises nothing
    assert "no notifier here" in capsys.readouterr().err


# -- Command-line contract --------------------------------------------------


def test_print_command_reports_resolved_command():
    proc = subprocess.run(
        [sys.executable, str(LAUNCH_PY), "--print-command"],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "root:" in proc.stdout and "cmd:" in proc.stdout
    assert ("pipeline-hatch" in proc.stdout) or ("launcher.main" in proc.stdout)


def test_launch_py_is_stdlib_only():
    tree = ast.parse(LAUNCH_PY.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"os", "subprocess", "sys", "pathlib", "ctypes"}, imported


def test_launch_py_has_no_machine_paths():
    source = LAUNCH_PY.read_text(encoding="utf-8")
    assert "/Volumes/" not in source
    assert "/srv/" not in source
    assert "C:\\" not in source


# -- Platform shells --------------------------------------------------------


def test_macos_bundle_structure():
    plist = (MAC_APP / "Contents" / "Info.plist").read_text(encoding="utf-8")
    assert "<string>pipeline-hatch</string>" in plist          # CFBundleExecutable
    assert "com.molei.pipelinehatch" in plist
    binary = MAC_APP / "Contents" / "MacOS" / "pipeline-hatch"
    assert binary.is_file()
    assert os.access(binary, os.X_OK), "bundle executable is not chmod +x"
    assert (MAC_APP / "Contents" / "Resources" / "pipeline_hatch.icns").is_file()

    shell = binary.read_text(encoding="utf-8")
    assert shell.startswith("#!/bin/bash")
    assert "launcher/launch.py" in shell
    assert 'exec "$PY" "$LAUNCHER"' in shell


def test_macos_bundle_delegates_to_launch_py():
    """End-to-end: shell -> system python3 -> launch.py, GUI-free."""
    if sys.platform != "darwin":
        pytest.skip("macOS bundle shell")
    binary = MAC_APP / "Contents" / "MacOS" / "pipeline-hatch"
    proc = subprocess.run([str(binary), "--print-command"],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert str(ROOT) in proc.stdout
    assert "cmd:" in proc.stdout


def test_linux_desktop_entry():
    text = LINUX_ENTRY.read_text(encoding="utf-8")
    assert text.startswith("[Desktop Entry]")
    assert "Type=Application" in text
    assert "Terminal=false" in text
    assert "launcher/launch.py" in text
    exec_lines = [ln for ln in text.splitlines() if ln.startswith("Exec=")]
    assert len(exec_lines) == 1 and "python3" in exec_lines[0]


def test_windows_batch_shell():
    text = WIN_SHELL.read_text(encoding="utf-8")
    assert text.lstrip().lower().startswith("@echo off")
    assert "launch.py" in text
    assert "pythonw" in text
