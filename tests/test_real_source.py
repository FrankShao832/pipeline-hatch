"""The settings panel reads the real projects (2026-10-25).

``RealSettingsDataSource`` replaces the fixture backend in the running app, so
these tests pin the things that only a live backend can get wrong: the show list
matches the database, the counts come from the disk, scaffold repair is
idempotent, and the environment preview is the *same* mapping the launcher
injects — not a lookalike.
"""

import os
from dataclasses import replace

import pytest
from PySide6.QtCore import Qt

from launcher.core.env_store import EnvConfig
from launcher.ui import main_window as main_window_module
from launcher.ui.real_source import RealSettingsDataSource
from launcher.ui.viewmodels import EnvRow, ProjectRow


@pytest.fixture
def source(tmp_path):
    """A live backend: the tests below assert against the real database.

    The override store is redirected to a temp file: these assertions describe
    the pipeline, not whichever ``config/env.yaml`` happens to sit on the
    developer's machine.
    """
    from launcher.database.database import DatabaseManager

    db = DatabaseManager()
    db.connect()
    src = RealSettingsDataSource(db=db, env_store_path=tmp_path / "env.yaml")
    if not src.db.is_connected:
        pytest.skip("launcher database not available")
    return src


class TestProjects:
    def test_lists_the_existing_shows(self, source):
        names = {row.name for row in source.projects()}

        assert {"CyberPunk", "DragonLand", "SpaceOdyssey", "RainPool", "Demo"} <= names

    def test_counts_come_from_the_disk(self, source):
        rows = {row.name: row for row in source.projects()}
        cyberpunk = rows["CyberPunk"]

        assert cyberpunk.seqs == 3
        assert cyberpunk.shots == 20
        assert cyberpunk.source == "db"

    def test_scaffold_state_reflects_the_folders(self, source):
        rows = {row.name: row for row in source.projects()}
        cyberpunk = rows["CyberPunk"]

        assert cyberpunk.scaffold_state == "complete"
        assert cyberpunk.scaffold_missing == 0

    def test_scaffold_plan_marks_existing_folders(self, source):
        plan = source.scaffold_plan("CyberPunk")
        required = [row for row in plan if row.required]

        assert len(required) == 2                     # work root + publish root
        assert all(row.exists for row in required)


class TestValidation:
    def test_rejects_a_bad_name(self, source):
        codes = {d.code for d in source.validate_project("9bad name", "/tmp", "/tmp")}
        assert "E_NAME" in codes

    def test_flags_a_duplicate_with_a_different_root(self, source):
        codes = {d.code for d in source.validate_project("CyberPunk", "/tmp/elsewhere", "/tmp")}
        assert "E_DUP" in codes

    def test_warns_when_the_folders_are_missing(self, source):
        codes = {d.code for d in source.validate_project("BrandNewShow", "/tmp/nowhere", "/tmp/nowhere2")}
        assert {"W_ROOT", "W_PUB"} <= codes


class TestRepair:
    def test_repair_creates_then_skips(self, source, tmp_path, monkeypatch):
        """Idempotent by construction: the second run creates nothing."""
        fake_row = ProjectRow(name="RepairProbe", root=str(tmp_path / "root"),
                              publish_root=str(tmp_path / "pub"))
        monkeypatch.setattr(source, "_find", lambda name: fake_row if name == "RepairProbe" else None)

        first = source.repair("RepairProbe", dry_run=False)
        second = source.repair("RepairProbe", dry_run=False)

        assert first.created, "the first repair must create the skeleton"
        assert not first.errors
        assert second.created == (), "a second repair must be a no-op"
        assert os.path.isdir(tmp_path / "root" / "RepairProbe")

    def test_unknown_project_reports_an_error(self, source):
        summary = source.repair("NoSuchShow", dry_run=False)
        assert summary.errors
        assert not summary.ok


class TestEnvironment:
    def test_rows_are_derived_from_the_launch_environment(self, source):
        rows = source.env_rows()
        names = {row.name for row in rows}

        assert {"DCC", "DEPARTMENT", "PROJECT_ROOT", "PUBLISH_ROOT"} <= names
        assert all(row.scope == "derived" for row in rows)

    def test_whitelist_membership_is_real(self, source):
        rows = {row.name: row for row in source.env_rows()}
        whitelist = set(source._env_whitelist())

        for name, row in rows.items():
            if name in whitelist:
                assert row.injected_to, f"{name} is whitelisted so it reaches a DCC"

    def test_resolved_uses_the_selected_show(self, source):
        rows = {r.name: r.value for r in source.resolved("RainPool", "houdini", "fx")}
        assert rows["SHOW"] == "RainPool"
        assert rows["DEPARTMENT"] == "fx"
        assert rows["DCC"] == "houdini"

    def test_saving_writes_the_show_layer_and_creates_the_store(self, source):
        row = next(r for r in source.env_rows() if r.name == "ASSET_ROOT")

        diags = source.save_env_row(EnvRow(name=row.name, value="/tmp/new-assets",
                                           scope="show", scope_key="CyberPunk"))

        assert diags == []
        assert source.env_store_path.exists()
        stored = EnvConfig.load(source.env_store_path)
        assert stored.get("show", "CyberPunk", "ASSET_ROOT").value == "/tmp/new-assets"

    def test_the_saved_value_wins_on_the_next_resolve(self, source):
        source.save_env_row(EnvRow(name="ASSET_ROOT", value="/tmp/winning-assets",
                                   scope="show", scope_key="CyberPunk"))

        rows = {r.name: r for r in source.resolved("CyberPunk", "maya", "")}

        assert rows["ASSET_ROOT"].value == "/tmp/winning-assets"
        assert rows["ASSET_ROOT"].source == "show"
        assert rows["ASSET_ROOT"].shadowed[0][0] == "derived"

    def test_a_key_outside_the_whitelist_is_stored_but_flagged(self, source):
        diags = source.save_env_row(EnvRow(name="NOT_A_LAUNCH_KEY", value="1",
                                           scope="show", scope_key="CyberPunk"))

        assert [d.code for d in diags] == ["W_WHITELIST"]
        assert EnvConfig.load(source.env_store_path).get(
            "show", "CyberPunk", "NOT_A_LAUNCH_KEY").value == "1"

    def test_a_guarded_key_is_stored_but_flagged(self, source):
        diags = source.save_env_row(EnvRow(name="OCIO", value="/color/x.ocio",
                                           scope="show", scope_key="CyberPunk"))

        codes = [d.code for d in diags]
        assert "W_GUARDED" in codes
        # OCIO is not in dcc.yaml: pipeline.env_vars either, so the same write
        # also says the value will never reach a DCC. Both statements are true.
        assert "W_WHITELIST" in codes
        assert "OCIO" in EnvConfig.load(source.env_store_path).scopes["show"]["CyberPunk"]

    def test_a_broken_store_is_never_overwritten(self, source):
        source.env_store_path.parent.mkdir(parents=True, exist_ok=True)
        source.env_store_path.write_text("scopes: [oops\n", encoding="utf-8")

        diags = source.save_env_row(EnvRow(name="ASSET_ROOT", value="/tmp/x",
                                           scope="show", scope_key="CyberPunk"))

        assert [d.code for d in diags] == ["E_ENV_STORE"]
        assert source.env_store_path.read_text(encoding="utf-8") == "scopes: [oops\n"

    def test_an_invalid_name_is_refused_before_anything_is_written(self, source):
        diags = source.save_env_row(EnvRow(name="1BAD NAME", value="x",
                                           scope="show", scope_key="CyberPunk"))

        assert [d.code for d in diags] == ["E_ENV_NAME"]
        assert not source.env_store_path.exists()


class TestEnvOverrides:
    """``config/env.yaml`` layered over the derived values (card C3)."""

    def _store_source(self, source, tmp_path, **values):
        from launcher.core.env_store import EnvConfig

        store = EnvConfig.load(tmp_path / "env.yaml")
        for scope, (scope_key, name, value) in values.items():
            store.put(scope, scope_key, name, value)
        store.save()
        return RealSettingsDataSource(db=source.db, config=source.config,
                                      env_store_path=tmp_path / "env.yaml")

    def test_an_empty_store_leaves_every_row_derived(self, source):
        rows = source.resolved("CyberPunk", "maya", "")

        assert rows
        assert all(row.source == "derived" for row in rows)
        assert all(row.scope_key == "" for row in rows)

    def test_a_show_override_names_its_scope_and_keeps_the_loser(self, source, tmp_path):
        src = self._store_source(
            source, tmp_path,
            show=("CyberPunk", "ASSET_ROOT", "/tmp/show-assets"))

        rows = {row.name: row for row in src.resolved("CyberPunk", "maya", "")}

        won = rows["ASSET_ROOT"]
        assert won.value == "/tmp/show-assets"
        assert won.source == "show"
        assert won.scope_key == "CyberPunk"
        assert won.shadowed[0][0] == "derived"
        assert won.shadowed[0][1] != "/tmp/show-assets"

    def test_an_override_for_an_unknown_key_becomes_a_new_row(self, source, tmp_path):
        src = self._store_source(
            source, tmp_path, show=("CyberPunk", "OCIO", "/color/aces_cg.ocio"))

        rows = {row.name: row for row in src.resolved("CyberPunk", "maya", "")}

        assert rows["OCIO"].value == "/color/aces_cg.ocio"
        assert rows["OCIO"].scope_key == "CyberPunk"
        assert rows["OCIO"].shadowed == ()

    def test_overrides_for_another_show_are_ignored(self, source, tmp_path):
        src = self._store_source(
            source, tmp_path, show=("DragonLand", "ASSET_ROOT", "/tmp/dragon"))

        rows = {row.name: row for row in src.resolved("CyberPunk", "maya", "")}

        assert rows["ASSET_ROOT"].source == "derived"

    def test_env_rows_carry_the_scope_and_the_stored_description(self, source, tmp_path):
        from launcher.core.env_store import EnvConfig

        # Override whichever show the backend samples, so the test does not
        # depend on database row order.
        show = {row.name: row for row in source.env_rows()}["SHOW"].value
        store = EnvConfig.load(tmp_path / "env.yaml")
        store.put("show", show, "OCIO", "/color/aces_cg.ocio",
                  description="ACES for this show")
        store.save()
        src = RealSettingsDataSource(db=source.db, config=source.config,
                                     env_store_path=tmp_path / "env.yaml")

        ocio = {row.name: row for row in src.env_rows()}["OCIO"]

        assert ocio.scope == "show"
        assert ocio.scope_key == show
        assert ocio.value == "/color/aces_cg.ocio"
        assert ocio.description == "ACES for this show"
        assert ocio.injected_to == ()          # OCIO is not in the dcc.yaml whitelist

    def test_a_broken_store_is_reported_not_swallowed(self, source, tmp_path):
        path = tmp_path / "env.yaml"
        path.write_text("scopes: [oops\n", encoding="utf-8")
        src = RealSettingsDataSource(db=source.db, config=source.config,
                                     env_store_path=path)

        codes = {d.code for d in src.diagnostics()}
        assert "E_ENV_STORE" in codes
        # The preview still works, and says honestly that nothing was overridden.
        assert all(row.source == "derived" for row in src.resolved("CyberPunk", "maya", ""))


class TestRevert:
    """Card C6: one click takes back the last write to ``env.yaml``."""

    def test_no_backup_before_the_first_save(self, source):
        assert source.has_env_backup() is False
        assert [d.code for d in source.revert_env()] == ["W_NO_BACKUP"]

    def test_a_save_leaves_a_backup_and_revert_restores_the_old_bytes(self, source):
        source.save_env_row(EnvRow(name="ASSET_ROOT", value="/tmp/first",
                                   scope="show", scope_key="CyberPunk"))
        first_bytes = source.env_store_path.read_text(encoding="utf-8")

        source.save_env_row(EnvRow(name="ASSET_ROOT", value="/tmp/second",
                                   scope="show", scope_key="CyberPunk"))
        assert source.has_env_backup() is True

        assert source.revert_env() == []

        assert source.env_store_path.read_text(encoding="utf-8") == first_bytes
        stored = EnvConfig.load(source.env_store_path)
        assert stored.get("show", "CyberPunk", "ASSET_ROOT").value == "/tmp/first"

    def test_the_newest_backup_wins(self, source, tmp_path):
        import time

        source.save_env_row(EnvRow(name="ASSET_ROOT", value="/tmp/one",
                                   scope="show", scope_key="CyberPunk"))
        time.sleep(0.005)                      # distinct .bak.<epoch-ms> stamps
        source.save_env_row(EnvRow(name="ASSET_ROOT", value="/tmp/two",
                                   scope="show", scope_key="CyberPunk"))
        two_bytes = source.env_store_path.read_text(encoding="utf-8")
        time.sleep(0.005)
        source.save_env_row(EnvRow(name="ASSET_ROOT", value="/tmp/three",
                                   scope="show", scope_key="CyberPunk"))

        source.revert_env()

        assert source.env_store_path.read_text(encoding="utf-8") == two_bytes
        # The backup survives the revert, so a mis-click can be undone again.
        assert source.has_env_backup() is True

    def test_revert_never_leaves_a_temp_file_behind(self, source):
        source.save_env_row(EnvRow(name="ASSET_ROOT", value="/tmp/x",
                                   scope="show", scope_key="CyberPunk"))
        source.revert_env()

        leftovers = [p.name for p in source.env_store_path.parent.iterdir()
                     if p.name.startswith(".")]
        assert leftovers == []


class TestShallowRoot:
    """A root that is not ``<dev>/projects/<name>`` must not invent ``$DEV``."""

    def test_no_dev_folders_are_planned_at_the_filesystem_root(self, source):
        plan = source.create_project("ZzShallow", "/tmp/projects",
                                     "/tmp/publish", {}, True)

        assert not [p for p in plan.created if p.startswith("/cache")
                    or p.startswith("/assets") or p.startswith("/renders")]
        assert [d.code for d in plan.diagnostics].count("W_DEV") == 1
        assert plan.env_written == 2          # the skeleton still applies

    def test_a_proper_layout_still_plans_them(self, source):
        plan = source.create_project("ZzNested", "/tmp/demo/projects/projects",
                                     "/tmp/demo/projects/publish", {}, True)

        assert "/tmp/demo/cache/ZzNested" in plan.created
        assert "W_DEV" not in [d.code for d in plan.diagnostics]


class TestDiagnostics:
    def test_no_database_error_when_connected(self, source):
        codes = {d.code for d in source.diagnostics()}
        assert "E_DB" not in codes

    def test_database_down_falls_back_to_yaml(self, monkeypatch):
        src = RealSettingsDataSource()
        monkeypatch.setattr(type(src), "_db_rows", lambda self: None)
        rows = src.projects()

        assert rows, "YAML fallback must still produce rows"
        assert all(row.source in ("db", "yaml") for row in rows)


@pytest.fixture
def window(qapp, monkeypatch):
    monkeypatch.setattr(
        "launcher.ui.widgets.project_tree.ProjectTreeWidget.load_projects",
        lambda self: None,
    )
    win = main_window_module.MainWindow()
    yield win
    win.close()
    win.deleteLater()


class TestLaunchEquivalence:
    def test_launch_env_is_exactly_the_shared_context(self, window, monkeypatch):
        """The settings preview and the launch call the same function."""
        from launcher.core.launch_env import build_env_context

        window.root_path = "/Volumes/Development/projects/y_pipeline_projects"
        window.publish_root_path = "/Volumes/Development/projects/y_pipeline_publish"
        window.project, window.sequence, window.shot = "CyberPunk", "seq001_city", "cy_city_0010"
        window.role, window.department = "houdini", "fx"
        window.file_path = "/tmp"
        captured = {}

        def fake_popen(command, **kwargs):
            captured.update(kwargs)
            return object()

        monkeypatch.setattr(main_window_module.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(window, "_check_dcc_exists", lambda dcc: True)

        window._launch_dcc()

        expected = build_env_context(
            root_path=window.root_path,
            publish_root_path=window.publish_root_path,
            project=window.project,
            sequence=window.sequence,
            shot=window.shot,
            department=window.department,
            dcc=window.role,
        )
        injected = captured["env"]
        for key, value in expected.items():
            assert injected[key] == value, key


class TestProjectsPage:
    def test_page_renders_every_project(self, qapp, source):
        from launcher.ui.widgets.projects_page import ProjectsPage

        page = ProjectsPage(source)
        try:
            assert page.table.rowCount() == len(source.projects())
            assert page.table.item(0, 0).data(Qt.ItemDataRole.UserRole)
            # The detail strip carries the full paths, unfolded.
            assert source.projects()[0].root in page.detail_label.text()
        finally:
            page.deleteLater()

    def test_repair_button_follows_the_selection(self, qapp, source):
        from launcher.ui.widgets.projects_page import ProjectsPage

        page = ProjectsPage(source)
        try:
            page.table.clearSelection()
            assert not page.repair_btn.isEnabled()
            page.table.selectRow(0)
            assert page.repair_btn.isEnabled()
        finally:
            page.deleteLater()
