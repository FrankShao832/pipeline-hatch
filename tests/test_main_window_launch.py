"""End-to-end launch command tests for ``MainWindow._launch_dcc``.

These exist because of the 2026-10-25 crash: Nuke 17 died with SIGSEGV two
seconds after launch because the launcher ran

    Nuke17.0 --nukex -m /…/RainPool/seq001_pond/rp_pond_0010/comp

``-m`` in Nuke sets the render thread count (``-m n``), so the workdir was
parsed as an integer. The fix drops the flag and delivers the workdir as the
process cwd instead. Unit-level pins live in ``tests/test_dcc.py``; these tests
cover the wiring: the real config, the real ``dcc_manager``, one monkeypatched
``Popen``.
"""

import os
import time
import types

import pytest

from launcher.ui import main_window as main_window_module
from launcher.ui.main_window import MainWindow

@pytest.fixture
def window(qapp, monkeypatch):
    monkeypatch.setattr(
        "launcher.ui.widgets.project_tree.ProjectTreeWidget.load_projects",
        lambda self: None,
    )
    win = MainWindow()
    yield win
    win.close()
    win.deleteLater()


@pytest.fixture
def workdir(tmp_path):
    path = tmp_path / "seq001_pond" / "rp_pond_0010" / "comp"
    path.mkdir(parents=True)
    return path


def _prepare_nuke(window, workdir, monkeypatch, captured):
    window.role = "nuke"
    window.file_path = str(workdir)
    window.root_path = "/fake/projects"
    window.publish_root_path = "/fake/publish"
    window.project = "RainPool"
    window.sequence = "seq001_pond"
    window.shot = "rp_pond_0010"
    window.department = "comp"
    monkeypatch.setattr(window, "_check_dcc_exists", lambda dcc: True)

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(main_window_module.subprocess, "Popen", fake_popen)


class TestNukeLaunchCommand:
    def test_workdir_is_not_passed_as_an_argument(self, window, workdir, monkeypatch):
        captured = {}
        _prepare_nuke(window, workdir, monkeypatch, captured)

        window._launch_dcc()

        command = captured["command"]
        assert "-m" not in command, "the render-thread-count flag must never be used"
        assert str(workdir) not in command

    def test_workdir_is_delivered_as_cwd(self, window, workdir, monkeypatch):
        captured = {}
        _prepare_nuke(window, workdir, monkeypatch, captured)

        window._launch_dcc()

        assert captured.get("cwd") == str(workdir)

    def test_nukex_and_existing_environment_survive(self, window, workdir, monkeypatch):
        captured = {}
        _prepare_nuke(window, workdir, monkeypatch, captured)

        window._launch_dcc()

        assert "--nukex" in captured["command"]
        assert captured["env"]["SHOW"] == "RainPool"
        assert captured["env"]["PROJECT_ROOT"] == "/fake/projects"
        assert captured["env"]["PUBLISH_ROOT"] == "/fake/publish"


class TestWorkdirIsCreatedOnLaunch:
    """A shot added through "Add shots…" arrives with no department folder.

    The folder follows the department chosen at launch time, so the launch is
    where it gets made. Without it the artist is either refused ("Project path
    not found") or, for a DCC that opens on its cwd, dropped somewhere random.
    """

    def test_launch_creates_the_missing_department_folder(
            self, window, tmp_path, monkeypatch):
        shot_dir = tmp_path / "seq001_pond" / "rp_pond_0010"
        shot_dir.mkdir(parents=True)
        workdir = shot_dir / "comp"          # resolved, but not on disk yet
        captured = {}
        _prepare_nuke(window, workdir, monkeypatch, captured)

        window._launch_dcc()

        assert workdir.is_dir()
        assert captured.get("cwd") == str(workdir)

    def test_launch_does_not_invent_a_missing_shot(
            self, window, tmp_path, monkeypatch):
        # Only the department level may be created: a stale selection naming a
        # shot that is gone must not silently rebuild the shot tree.
        workdir = tmp_path / "seq001_pond" / "rp_pond_0010" / "comp"
        captured = {}
        shown = []
        _prepare_nuke(window, workdir, monkeypatch, captured)
        monkeypatch.setattr(window, "_show_info", shown.append)

        window._launch_dcc()

        assert not workdir.exists()
        assert captured == {}, "no DCC should be spawned"
        assert "Project path not found" in shown[0]



class TestHoudiniStartsInTheShot:
    """Houdini gets no workdir argument, so the cwd *is* the shot folder.

    Before the 2026-11-01 rehearsal fix it inherited the launcher's own cwd (the
    repo root) while ``JOB`` pointed at the shot — the file browser and every
    relative path opened in the wrong place.
    """

    def _prepare_houdini(self, window, workdir, monkeypatch, captured):
        window.role = "houdini"
        window.file_path = str(workdir)
        window.root_path = "/fake/projects"
        window.publish_root_path = "/fake/publish"
        window.project = "Rehearsal01"
        window.sequence = "test"
        window.shot = "re_test_001"
        window.department = "fx"
        monkeypatch.setattr(window, "_check_dcc_exists", lambda dcc: True)

        def fake_popen(command, **kwargs):
            captured["command"] = command
            captured.update(kwargs)
            return object()

        monkeypatch.setattr(main_window_module.subprocess, "Popen", fake_popen)

    def test_houdini_is_spawned_inside_the_shot_department_folder(
            self, window, tmp_path, monkeypatch):
        workdir = tmp_path / "Rehearsal01" / "test" / "re_test_001" / "fx"
        workdir.mkdir(parents=True)
        captured = {}
        self._prepare_houdini(window, workdir, monkeypatch, captured)

        window._launch_dcc()

        assert captured.get("cwd") == str(workdir)
        assert captured["env"]["JOB"] == str(workdir)


class TestNukeOpensAScriptFromTheShot:
    """Nuke's project folder is the folder of the open script (A2).

    ``nuke.script_directory()`` is empty when nothing is open, so File > Save As
    started in Nuke's own last-used folder instead of the shot. Opening a script
    from the department folder fixes it — and it has to be one the artist can
    keep saving to, hence ``<shot>_v001.nk`` on first open.
    """

    def test_empty_workdir_gets_a_version_001_script(
            self, window, workdir, monkeypatch):
        captured = {}
        _prepare_nuke(window, workdir, monkeypatch, captured)

        window._launch_dcc()

        created = workdir / "rp_pond_0010_v001.nk"
        assert created.is_file()
        assert captured["command"][-1] == str(created)

    def test_existing_script_is_reopened_not_duplicated(
            self, window, workdir, monkeypatch):
        existing = workdir / "rp_pond_0010_v003.nk"
        existing.write_text("Root {\n}\n", encoding="utf-8")
        captured = {}
        _prepare_nuke(window, workdir, monkeypatch, captured)

        window._launch_dcc()

        assert captured["command"][-1] == str(existing)
        assert [p.name for p in workdir.iterdir()] == ["rp_pond_0010_v003.nk"]

    def test_selected_file_still_wins_over_the_startup_script(
            self, window, workdir, monkeypatch):
        """Picking a file in the launcher must not be second-guessed."""
        chosen = workdir / "artist_work_v010.nk"
        chosen.write_text("Root {\n}\n", encoding="utf-8")
        new = workdir / "rp_pond_0010_v001.nk"
        new.write_text("Root {\n}\n", encoding="utf-8")
        old = time.time() - 3600
        os.utime(chosen, (old, old))
        captured = {}
        _prepare_nuke(window, workdir, monkeypatch, captured)
        monkeypatch.setattr(
            window.file_tree, "currentItem",
            lambda: types.SimpleNamespace(text=lambda _col: chosen.name),
        )
        monkeypatch.setattr(window.file_tree, "topLevelItemCount", lambda: 1)

        window._launch_dcc()

        assert captured["command"][-1] == str(chosen)
