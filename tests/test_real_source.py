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

from launcher.ui import main_window as main_window_module
from launcher.ui.real_source import RealSettingsDataSource
from launcher.ui.viewmodels import ProjectRow


@pytest.fixture
def source():
    """A live backend: the tests below assert against the real database."""
    from launcher.database.database import DatabaseManager

    db = DatabaseManager()
    db.connect()
    src = RealSettingsDataSource(db=db)
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

    def test_editing_reports_the_missing_store(self, source):
        row = source.env_rows()[0]
        diags = source.save_env_row(row)

        assert [d.code for d in diags] == ["W_NO_STORE"]


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
