"""The override store must reach the DCC that is being launched.

Written while preparing the demo video (2026-10-30): ``_launch_dcc`` built the
derived context and stopped there, so a value edited in the settings panel was
written to ``config/env.yaml``, shown in the preview — and never injected. The
feature was cosmetic until these three links existed:

* ``merge_env_store`` puts the store on top of the derived context,
  ``${VAR}`` expanded at resolve time;
* the preview and the launch resolve to the same numbers;
* the child process really receives them (``Popen(env=…)``).
"""

import logging

import pytest

from launcher.core.env_store import EnvConfig
from launcher.core.launch_env import (
    build_env_context,
    merge_env_store,
    resolve_env,
)
from launcher.ui import main_window as main_window_module
from launcher.ui.main_window import MainWindow

ROOT = "/Volumes/Development/projects/y_pipeline_projects"
PUBLISH = "/Volumes/Development/projects/y_pipeline_publish"


def _ctx(show="CyberPunk", department="fx", dcc="maya"):
    return build_env_context(
        root_path=ROOT, publish_root_path=PUBLISH, project=show,
        sequence="seq001", shot="sh010", department=department, dcc=dcc)


def _store(path, *layers):
    """Write ``((scope, scope_key, name, value), …)`` into a store at *path*."""
    config = EnvConfig.load(path)
    for scope, scope_key, name, value in layers:
        config.put(scope, scope_key, name, value)
    config.save()
    return path


class TestMerge:
    def test_a_missing_store_leaves_the_derived_values_alone(self, tmp_path):
        ctx = _ctx()

        merged = merge_env_store(ctx, tmp_path / "env.yaml")

        assert merged == ctx

    def test_a_show_override_wins_and_its_placeholder_is_expanded(self, tmp_path):
        ctx = _ctx()
        path = _store(tmp_path / "env.yaml",
                      ("show", "CyberPunk", "ASSET_ROOT", "${DEV}/assets2/${SHOW}"),
                      ("show", "CyberPunk", "OCIO", "${DEV}/color/aces_cg.ocio"))

        merged = merge_env_store(ctx, path)

        assert merged["ASSET_ROOT"] == "/Volumes/Development/assets2/CyberPunk"
        assert merged["OCIO"] == "/Volumes/Development/color/aces_cg.ocio"
        # Everything else is still there and still derived.
        assert merged["SHOT"] == ctx["SHOT"]
        assert merged["PUBLISH_ROOT"] == ctx["PUBLISH_ROOT"]

    def test_the_higher_scope_wins_and_the_losers_are_kept(self, tmp_path):
        ctx = _ctx(department="fx")
        path = _store(tmp_path / "env.yaml",
                      ("show", "CyberPunk", "RENDER_ROOT", "/renders/show"),
                      ("department", "fx", "RENDER_ROOT", "/renders/fx"))

        entries, merged = resolve_env(ctx, path)

        assert merged["RENDER_ROOT"] == "/renders/fx"
        won = next(e for e in entries if e.name == "RENDER_ROOT")
        assert won.source == "department"
        assert [scope for scope, _value in won.shadowed] == ["derived", "show"]

    def test_an_override_for_another_show_is_ignored(self, tmp_path):
        path = _store(tmp_path / "env.yaml",
                      ("show", "DragonLand", "ASSET_ROOT", "/dragon/assets"))

        merged = merge_env_store(_ctx(), path)

        assert merged["ASSET_ROOT"] == "/Volumes/Development/assets/CyberPunk"

    def test_a_broken_store_is_ignored_rather_than_stopping_the_launch(self, tmp_path, caplog):
        path = tmp_path / "env.yaml"
        path.write_text("scopes: [oops\n", encoding="utf-8")
        ctx = _ctx()

        with caplog.at_level(logging.WARNING):
            merged = merge_env_store(ctx, path)

        assert merged == ctx
        assert "Ignoring unusable override store" in caplog.text


class TestPreviewAgreesWithLaunch:
    """The two readers of the store must not drift apart."""

    def test_the_settings_preview_matches_the_launch_mapping(self, tmp_path):
        from launcher.ui.real_source import RealSettingsDataSource

        try:
            from launcher.database.database import DatabaseManager

            db = DatabaseManager()
            db.connect()
            if not db.is_connected:
                pytest.skip("launcher database not available")
        except Exception:
            pytest.skip("launcher database not available")

        path = _store(tmp_path / "env.yaml",
                      ("show", "CyberPunk", "OCIO", "${DEV}/color/aces_cg.ocio"),
                      ("department", "fx", "RENDER_ROOT", "/renders/fx"))
        source = RealSettingsDataSource(db=db, env_store_path=path)

        preview = {row.name: row.value
                   for row in source.resolved("CyberPunk", "maya", "fx")}
        # The preview samples the first shot on disk, so the launch context has
        # to describe that same shot — otherwise SEQ/SHOT differ by construction.
        ctx = build_env_context(
            root_path=ROOT, publish_root_path=PUBLISH, project="CyberPunk",
            sequence=preview["SEQ"], shot=preview["SHOT"],
            department="fx", dcc="maya")
        launch = merge_env_store(ctx, path)

        assert preview == launch


class TestLauncherInjectsIt:
    """One monkeypatched ``Popen``; the rest is the real wiring."""

    @pytest.fixture
    def window(self, qapp, monkeypatch):
        monkeypatch.setattr(
            "launcher.ui.widgets.project_tree.ProjectTreeWidget.load_projects",
            lambda self: None,
        )
        win = MainWindow()
        yield win
        win.close()
        win.deleteLater()

    def test_the_edited_value_is_what_the_dcc_process_receives(
            self, window, tmp_path, monkeypatch):
        path = _store(tmp_path / "env.yaml",
                      ("show", "RainPool", "OCIO", "${DEV}/color/aces_cg.ocio"))
        window._env_store_path = str(path)
        window.role = "nuke"
        window.file_path = ""
        window.root_path = ROOT
        window.publish_root_path = PUBLISH
        window.project = "RainPool"
        window.sequence = "seq001"
        window.shot = "sh010"
        window.department = "comp"
        monkeypatch.setattr(window, "_check_dcc_exists", lambda dcc: True)
        captured = {}

        def fake_popen(command, **kwargs):
            captured.update(kwargs)
            return object()

        monkeypatch.setattr(main_window_module.subprocess, "Popen", fake_popen)

        window._launch_dcc()

        assert captured["env"]["OCIO"] == "/Volumes/Development/color/aces_cg.ocio"
        assert captured["env"]["SHOW"] == "RainPool"
        assert captured["env"]["DEPARTMENT"] == "comp"

    def test_the_object_path_is_still_derived_when_nothing_overrides_it(
            self, window, tmp_path, monkeypatch):
        window._env_store_path = str(tmp_path / "no-store-here.yaml")
        window.role = "nuke"
        window.file_path = ""
        window.root_path = ROOT
        window.publish_root_path = PUBLISH
        window.project = "RainPool"
        window.sequence = "seq001"
        window.shot = "sh010"
        window.department = "comp"
        monkeypatch.setattr(window, "_check_dcc_exists", lambda dcc: True)
        captured = {}

        def fake_popen(command, **kwargs):
            captured.update(kwargs)
            return object()

        monkeypatch.setattr(main_window_module.subprocess, "Popen", fake_popen)

        window._launch_dcc()

        assert captured["env"]["CACHE_ROOT"] == "/Volumes/Development/cache/RainPool"
        assert not captured["env"].get("OCIO")
