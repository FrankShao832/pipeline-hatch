"""Tests for the UI view-model contract and its fixtures (plan T04)."""

import pytest
from dataclasses import FrozenInstanceError

from launcher.ui.fakes import FakeSettingsDataSource
from launcher.ui.viewmodels import (
    ApplySummary,
    DiagnosticRow,
    EnvRow,
    ProjectRow,
    ResolvedRow,
    ScaffoldPlanRow,
    SettingsDataSource,
    scope_rank,
)


class TestViewModels:
    def test_rows_are_frozen(self):
        row = ProjectRow(name="A", root="/r", publish_root="/p")
        with pytest.raises(FrozenInstanceError):
            row.name = "B"  # type: ignore[misc]

    def test_defaults_and_empty_summary(self):
        summary = ApplySummary()
        assert summary.created == ()
        assert summary.skipped == ()
        assert summary.errors == ()
        assert summary.diagnostics == ()
        assert summary.ok is True
        assert summary.counts() == (0, 0, 0)

        diag = DiagnosticRow(level="warn", code="W_PATH", message="m")
        assert diag.hint == ""
        assert diag.target == ""

        plan = ScaffoldPlanRow(path="/x", group="required")
        assert plan.required is False
        assert plan.exists is False

    def test_scope_rank_orders_precedence(self):
        assert scope_rank("derived") < scope_rank("global")
        assert scope_rank("global") < scope_rank("show") < scope_rank("dcc")
        assert scope_rank("dcc") < scope_rank("department")
        assert scope_rank("nonsense") == 5

    def test_masking_and_shadow_flags(self):
        assert EnvRow(name="T", value="v", scope="global", secret=True).is_masked() is True
        assert EnvRow(name="T", value="v", scope="global", secret=True).is_masked(True) is False
        assert EnvRow(name="T", value="v", scope="global").is_masked() is False

        plain = ResolvedRow(name="A", value="1", source="global")
        assert plain.is_shadowed is False
        shadowed = ResolvedRow(name="A", value="2", source="show",
                               shadowed=(("global", "1"),))
        assert shadowed.is_shadowed is True

    def test_diagnostic_sort_key_puts_errors_first(self):
        err = DiagnosticRow("error", "E_NAME", "x")
        warn = DiagnosticRow("warn", "W_PATH", "y")
        assert err.sort_key() < warn.sort_key()


class TestFakeRich:
    def setup_method(self):
        self.ds = FakeSettingsDataSource("rich")

    def test_counts(self):
        assert len(self.ds.projects()) == 3
        assert len(self.ds.env_rows()) == 12
        assert len(self.ds.resolved("CyberPunk", "houdini", "fx")) == 26
        assert [d.level for d in self.ds.diagnostics()] == ["warn"]

    def test_scaffold_states_cover_three_cases(self):
        states = [p.scaffold_state for p in self.ds.projects()]
        assert states == ["complete", "missing", "n/a"]
        missing = [p for p in self.ds.projects() if p.scaffold_state == "missing"][0]
        assert missing.scaffold_missing == 2

    def test_injected_to_empty_means_not_in_whitelist(self):
        rows = {r.name: r for r in self.ds.env_rows()}
        assert rows["OCIO"].injected_to == ()
        assert rows["JOB"].injected_to == ("houdini",)
        assert rows["DCC"].injected_to == ("maya", "houdini", "nuke", "katana")

    def test_repair_dry_run_does_not_consume(self):
        first = self.ds.repair("DragonLand", dry_run=True)
        second = self.ds.repair("DragonLand", dry_run=True)
        assert first.created and first.created == second.created

    def test_repair_is_idempotent(self):
        first = self.ds.repair("DragonLand", dry_run=False)
        second = self.ds.repair("DragonLand", dry_run=False)
        assert first.created
        assert second.created == ()
        assert second.skipped

    def test_create_project_dry_run_does_not_add_row(self):
        before = len(self.ds.projects())
        self.ds.create_project("NewShow", "/tmp/r", "/tmp/p", {}, dry_run=True)
        assert len(self.ds.projects()) == before
        self.ds.create_project("NewShow", "/tmp/r", "/tmp/p", {}, dry_run=False)
        assert len(self.ds.projects()) == before + 1


class TestFakeEmptyAndErrors:
    def test_empty_mode_is_all_empty(self):
        ds = FakeSettingsDataSource("empty")
        assert ds.projects() == []
        assert ds.env_rows() == []
        assert ds.diagnostics() == []
        assert ds.resolved("CyberPunk", "houdini", "fx") == []

    def test_errors_mode_raises_on_projects(self):
        ds = FakeSettingsDataSource("errors")
        with pytest.raises(RuntimeError):
            ds.projects()

    def test_errors_mode_reports_two_errors_one_warning(self):
        levels = [d.level for d in FakeSettingsDataSource("errors").diagnostics()]
        assert levels.count("error") == 2
        assert levels.count("warn") == 1

    def test_unknown_mode_rejected(self):
        with pytest.raises(ValueError):
            FakeSettingsDataSource("nope")


class TestProtocol:
    def test_fixture_satisfies_protocol(self):
        for mode in FakeSettingsDataSource.MODES:
            assert isinstance(FakeSettingsDataSource(mode), SettingsDataSource)

    def test_validate_project_flags_bad_input(self):
        ds = FakeSettingsDataSource()
        codes = [d.code for d in ds.validate_project("9bad name", "rel/path", "/abs/publish")]
        assert codes == ["E_NAME", "E_PATHREL"]
        same = [d.code for d in ds.validate_project("GoodName", "/abs/root", "/abs/root")]
        assert same == ["E_PATHREL"]
        assert ds.validate_project("GoodName", "/abs/root", "/abs/publish") == []
