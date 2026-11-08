"""Nuke only knows a folder through the script that is open in it (A2).

Why this exists: Nuke has no project switch (``-m`` is the render thread count,
and passing the workdir as an argument crashed Nuke 17 on 2026-10-25) and no
``$JOB`` equivalent. Measured on Nuke 17.0v4: with a script open,
``nuke.script_directory()`` returns that script's folder — with nothing open it
is empty, and File > Save As falls back to Nuke's own last-used directory, which
is why an artist's first save landed outside the shot.

So the launcher opens the newest ``.nk`` in the department folder, creating
``<shot>_v001.nk`` when there is none. The template itself was verified by
loading it in ``Nuke17.0 -t <file> -x`` (no error, ``fps`` honoured).
"""

import os
import time

import pytest

from launcher.dcc.dcc_houdini import HoudiniDCC
from launcher.dcc.dcc_maya import MayaDCC
from launcher.dcc.dcc_nuke import (
    DEFAULT_FPS,
    NukeDCC,
    ensure_startup_script,
    find_newest_script,
    script_text,
)


@pytest.fixture
def nuke_config():
    """Minimal Nuke configuration (no DCC installed needed)."""
    return {
        "name": "Nuke",
        "role": "nuke",
        "executable": "/Applications/Nuke17.0v4/Nuke17.0v4.app/Contents/MacOS/Nuke17.0",
        "app_name": "Nuke17.0v4.app",
        "flags": {"nukex": "--nukex", "file": "", "project": ""},
    }


@pytest.fixture
def workdir(tmp_path):
    """A department folder with nothing in it yet."""
    path = tmp_path / "seq001_pond" / "rp_pond_0010" / "comp"
    path.mkdir(parents=True)
    return path


class TestFindNewestScript:
    def test_returns_none_for_an_empty_folder(self, workdir):
        assert find_newest_script(str(workdir)) is None

    def test_returns_none_for_a_missing_folder(self, tmp_path):
        assert find_newest_script(str(tmp_path / "nope")) is None

    def test_picks_the_newest_mtime(self, workdir):
        old = workdir / "shot_v001.nk"
        new = workdir / "shot_v002.nk"
        old.write_text("Root {\n}\n", encoding="utf-8")
        new.write_text("Root {\n}\n", encoding="utf-8")
        past = time.time() - 3600
        os.utime(old, (past, past))

        assert find_newest_script(str(workdir)) == str(new)

    def test_ignores_other_extensions_and_subfolders(self, workdir):
        (workdir / "notes.txt").write_text("x", encoding="utf-8")
        sub = workdir / "backup"
        sub.mkdir()
        (sub / "deep_v009.nk").write_text("Root {\n}\n", encoding="utf-8")

        assert find_newest_script(str(workdir)) is None


class TestEnsureStartupScript:
    def test_creates_version_001_when_the_folder_is_empty(self, workdir):
        created = ensure_startup_script(str(workdir), "rp_pond_0010")

        assert created == str(workdir / "rp_pond_0010_v001.nk")
        assert os.path.isfile(created)
        assert [p.name for p in workdir.iterdir()] == ["rp_pond_0010_v001.nk"]

    def test_created_script_is_a_nuke_root_with_its_own_path(self, workdir):
        created = ensure_startup_script(str(workdir), "rp_pond_0010", fps="25")

        text = open(created, encoding="utf-8").read()
        assert text.startswith("Root {\n")
        assert f" name {created}\n" in text
        assert " fps 25\n" in text
        assert " format \"" in text

    def test_fps_falls_back_to_default(self, workdir):
        for fps in ("", "nonsense", "0", "-24"):
            created = ensure_startup_script(str(workdir), "shot", fps=fps)
            assert f" fps {DEFAULT_FPS}\n" in open(created, encoding="utf-8").read()
            os.unlink(created)

    def test_existing_script_wins_and_nothing_is_created(self, workdir):
        existing = workdir / "artist_sandbox_v007.nk"
        existing.write_text("Root {\n}\n", encoding="utf-8")

        assert ensure_startup_script(str(workdir), "rp_pond_0010") == str(existing)
        assert [p.name for p in workdir.iterdir()] == ["artist_sandbox_v007.nk"]

    def test_never_overwrites_an_existing_script(self, workdir):
        kept = workdir / "rp_pond_0010_v001.nk"
        kept.write_text("Root {\n name /artist/edits\n}\n", encoding="utf-8")

        assert ensure_startup_script(str(workdir), "rp_pond_0010") == str(kept)
        assert "artist/edits" in kept.read_text(encoding="utf-8")

    def test_no_shot_name_means_no_invented_file(self, workdir):
        assert ensure_startup_script(str(workdir), "") is None
        assert list(workdir.iterdir()) == []

    def test_missing_folder_is_not_created(self, tmp_path):
        missing = tmp_path / "seq" / "shot" / "comp"

        assert ensure_startup_script(str(missing), "shot") is None
        assert not missing.exists()

    def test_write_failure_degrades_to_none(self, workdir, monkeypatch):
        def boom(*args, **kwargs):
            raise OSError("read-only export")

        monkeypatch.setattr("launcher.dcc.dcc_nuke.os.replace", boom)

        assert ensure_startup_script(str(workdir), "rp_pond_0010") is None
        # No temp file may survive a failed write.
        assert list(workdir.iterdir()) == []


class TestScriptText:
    def test_shape_is_minimal_and_loadable(self, tmp_path):
        path = str(tmp_path / "shot_v001.nk")
        text = script_text(path, fps="23.976")

        assert text == (
            "Root {\n"
            " inputs 0\n"
            f" name {path}\n"
            " frame 1\n"
            " fps 23.976\n"
            ' format "1920 1080 0 0 1920 1080 1 HD_1080"\n'
            "}\n"
        )


class TestNukeStartupScriptMethod:
    def test_opens_the_script_through_build_command(self, nuke_config, workdir):
        nuke = NukeDCC(nuke_config)

        path = nuke.startup_script(str(workdir), shot="rp_pond_0010", fps="24")

        assert path and nuke.build_command(file_path=path)[-1] == path

    def test_no_workdir_returns_none(self, nuke_config):
        nuke = NukeDCC(nuke_config)

        assert nuke.startup_script(None, shot="rp_pond_0010") is None
        assert nuke.startup_script("", shot="rp_pond_0010") is None


class TestOtherDccsUnaffected:
    def test_houdini_and_maya_open_nothing(self):
        """Only Nuke needs a file: Maya has -proj, Houdini gets $JOB."""
        assert HoudiniDCC({"name": "Houdini", "role": "houdini"}).startup_script(
            "/tmp"
        ) is None
        assert MayaDCC({"name": "Maya", "role": "maya"}).startup_script("/tmp") is None
