"""Workdir resolution tests — department first, DCC only as a legacy fallback.

Vocabulary (see ``docs/VOCABULARY.md``): the **department** owns the work folder
and the **DCC** is only the application that opens it. ``resolve_workdir``
therefore resolves ``<shot>/<department>`` first.

Two layouts still exist on disk (2026-10-25 audit):

* ``<shot>/comp`` / ``fx`` / ``lighting`` — the department-named shape (the
  target);
* ``<shot>/nuke`` — the app-named shape left by the seeded projects
  (CyberPunk / DragonLand / SpaceOdyssey / Demo), accepted as a fallback so
  those shots stay launchable until the trees are migrated.
"""

import os

import pytest

from launcher.ui import main_window as main_window_module
from launcher.ui.main_window import MainWindow, resolve_workdir


@pytest.fixture
def shot_dir(tmp_path):
    shot = tmp_path / "CyberPunk" / "seq001_city" / "cy_city_0010"
    shot.mkdir(parents=True)
    return shot


class TestResolveWorkdir:
    def test_prefers_the_department_folder(self, shot_dir):
        """Both shapes present: the department owns the work, so it wins."""
        (shot_dir / "nuke").mkdir()
        (shot_dir / "comp").mkdir()

        assert resolve_workdir(str(shot_dir), "nuke", "comp") == str(shot_dir / "comp")

    def test_falls_back_to_the_legacy_dcc_folder(self, shot_dir):
        """Seeded trees only have ``nuke`` — transitional fallback keeps them usable."""
        (shot_dir / "nuke").mkdir()

        assert resolve_workdir(str(shot_dir), "nuke", "comp") == str(shot_dir / "nuke")

    def test_every_dcc_falls_back_on_an_app_named_tree(self, shot_dir):
        for name in ("maya", "houdini", "nuke"):
            (shot_dir / name).mkdir()

        assert resolve_workdir(str(shot_dir), "maya", "comp").endswith("maya")
        assert resolve_workdir(str(shot_dir), "houdini", "fx").endswith("houdini")
        assert resolve_workdir(str(shot_dir), "nuke", "lighting").endswith("nuke")

    def test_dcc_fallback_never_beats_a_department_folder(self, shot_dir):
        """The department folder stays authoritative even when a DCC folder exists."""
        for name in ("comp", "fx", "lighting", "nuke"):
            (shot_dir / name).mkdir()

        assert resolve_workdir(str(shot_dir), "nuke", "fx").endswith("fx")
        assert resolve_workdir(str(shot_dir), "houdini", "lighting").endswith("lighting")

    def test_nested_department_and_dcc_is_the_most_specific(self, shot_dir):
        """A department running several apps: ``fx/houdini`` wins over ``fx``."""
        (shot_dir / "fx" / "houdini").mkdir(parents=True)
        (shot_dir / "comp" / "nuke").mkdir(parents=True)

        assert resolve_workdir(str(shot_dir), "houdini", "fx") == str(shot_dir / "fx" / "houdini")
        assert resolve_workdir(str(shot_dir), "nuke", "comp") == str(shot_dir / "comp" / "nuke")

    def test_nested_wins_even_when_the_department_folder_also_exists(self, shot_dir):
        (shot_dir / "comp").mkdir()
        (shot_dir / "comp" / "nuke").mkdir()

        assert resolve_workdir(str(shot_dir), "nuke", "comp") == str(shot_dir / "comp" / "nuke")

    def test_missing_folders_yield_the_expected_department_path(self, shot_dir):
        """Nothing to pick: report the department path the user asked for."""
        assert resolve_workdir(str(shot_dir), "nuke", "comp") == str(shot_dir / "comp")

    def test_empty_inputs_are_safe(self, tmp_path):
        assert resolve_workdir("") == ""
        assert resolve_workdir(str(tmp_path)) == str(tmp_path)


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


class TestMainWindowWorkdir:
    def _select_shot(self, window, shot_dir, role="nuke", department="comp"):
        window.root_path = str(shot_dir.parents[2])
        window.project = "CyberPunk"
        window.sequence = shot_dir.parent.name
        window.shot = shot_dir.name
        window.role = role
        # The real flow: the combo emits department_changed → the handler sets
        # self.department before reloading.
        window.department = department

    def test_rainpool_shot_opens_its_department_folder(self, window, shot_dir, monkeypatch):
        (shot_dir / "comp").mkdir()
        self._select_shot(window, shot_dir)

        window._load_files()

        assert window.file_path == str(shot_dir / "comp")

    def test_legacy_app_named_shot_still_opens(self, window, shot_dir, monkeypatch):
        """CyberPunk has ``nuke`` only; the department folder is preferred but absent."""
        (shot_dir / "nuke").mkdir()
        self._select_shot(window, shot_dir)

        window._load_files()

        assert window.file_path == str(shot_dir / "nuke")

    def test_switching_department_reloads_the_workdir(self, window, shot_dir, monkeypatch):
        (shot_dir / "comp").mkdir()
        (shot_dir / "fx").mkdir()
        self._select_shot(window, shot_dir)
        window._load_files()
        assert window.file_path == str(shot_dir / "comp")

        window._on_department_changed("fx")

        assert window.file_path == str(shot_dir / "fx")
        assert window.department == "fx"

    def test_switching_dcc_re_resolves_the_legacy_fallback(self, window, shot_dir, monkeypatch):
        """App-named trees depend on the DCC, so a DCC switch must re-resolve."""
        (shot_dir / "nuke").mkdir()
        (shot_dir / "maya").mkdir()
        self._select_shot(window, shot_dir)
        window._load_files()
        assert window.file_path == str(shot_dir / "nuke")

        window._on_role_changed("maya")

        assert window.file_path == str(shot_dir / "maya")
