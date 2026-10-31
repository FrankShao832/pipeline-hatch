"""Tests for the Environment and Preflight pages (first cut, 2026-10-25).

Both pages exist to make the preview column legible: Environment shows the raw
layers the preview merges, Preflight shows what is wrong with the rows it
resolves. These tests pin the wiring, the counts and the degradation paths —
not pixels.
"""

import pytest
from PySide6.QtGui import QGuiApplication

from launcher.ui.fakes import FakeSettingsDataSource
from launcher.ui.widgets.environment_page import EnvironmentPage
from launcher.ui.widgets.preflight_page import PreflightPage


@pytest.fixture
def env_page(qapp):
    page = EnvironmentPage(FakeSettingsDataSource("rich"))
    yield page
    page.deleteLater()


@pytest.fixture
def preflight_page(qapp):
    page = PreflightPage(FakeSettingsDataSource("rich"))
    yield page
    page.deleteLater()


def _names(page) -> list[str]:
    return [page.table.item(row, 0).text() for row in range(page.table.rowCount())]


class TestEnvironmentPage:
    def test_lists_every_layer_row(self, env_page):
        """12 fixture keys → at least 12 rows, sorted by key then precedence."""
        assert env_page.table.rowCount() == len(env_page._rows)
        assert env_page.table.rowCount() >= 12
        assert env_page.status_label.text().startswith(
            f"{env_page.table.rowCount()} row(s)")

    def test_rows_are_grouped_by_key_then_scope(self, env_page):
        seen: dict[str, int] = {}
        for row in env_page._rows:
            from launcher.ui.viewmodels import scope_rank

            rank = scope_rank(row.scope)
            assert rank >= seen.get(row.name, -1) or row.name not in seen
            seen[row.name] = rank
        names = _names(env_page)
        assert names == sorted(names)          # keys read alphabetically

    def test_scope_column_carries_the_badge(self, env_page):
        texts = {env_page.table.item(row, 2).text() for row in range(env_page.table.rowCount())}
        assert all(text.startswith("[") and text.endswith("]") for text in texts)
        assert any(":" in text for text in texts)      # [show:CyberPunk] style

    def test_search_filters_by_key(self, env_page):
        total = env_page.table.rowCount()
        env_page.search_edit.setText("ocio")
        assert 0 < env_page.table.rowCount() < total
        assert all("OCIO" in name for name in _names(env_page))
        env_page.search_edit.setText("")
        assert env_page.table.rowCount() == total

    def test_scope_filter_shows_one_layer(self, env_page):
        env_page.scope_combo.setCurrentIndex(env_page.scope_combo.findData("global"))
        scopes = {env_page.table.item(row, 2).text() for row in range(env_page.table.rowCount())}
        assert scopes and all(text.startswith("[global") for text in scopes)
        env_page.scope_combo.setCurrentIndex(0)
        assert env_page.table.rowCount() == len(env_page._rows)

    def test_selection_explains_the_layer(self, env_page):
        env_page.table.selectRow(0)
        text = env_page.detail_label.text()
        assert "@" in text
        assert "injected to" in text or "whitelist" in text

    def test_disabled_rows_are_marked(self, qapp):
        source = FakeSettingsDataSource("rich")
        rows = source.env_rows()
        from launcher.ui.viewmodels import EnvRow

        if not any(not row.enabled for row in rows):
            source.save_env_row(EnvRow(name="DEV_OLD", value="/tmp",
                                       scope="global", enabled=False))
        page = EnvironmentPage(source)
        assert any(name.endswith("(off)") for name in _names(page))
        page.deleteLater()

    def test_empty_source_shows_a_hint(self, qapp):
        page = EnvironmentPage(FakeSettingsDataSource("empty"))
        assert page.table.rowCount() == 0
        assert "No environment keys" in page.status_label.text()
        page.deleteLater()

    def test_broken_source_does_not_raise(self, qapp):
        class _Stub:
            def env_rows(self):
                raise RuntimeError("yaml exploded")

        page = EnvironmentPage(_Stub())  # type: ignore[arg-type]
        assert page.table.rowCount() == 0
        assert "Could not load environment" in page.status_label.text()
        page.deleteLater()


class TestPreflightPage:
    def test_rich_fixture_has_one_warning(self, preflight_page):
        assert preflight_page.table.rowCount() == 1
        assert preflight_page.counts() == (0, 1)
        assert preflight_page.table.item(0, 0).text() == "warn"
        assert "1 warning" in preflight_page.status_label.text()

    def test_errors_come_first(self, qapp):
        page = PreflightPage(FakeSettingsDataSource("errors"))
        levels = [page.table.item(row, 0).text()
                  for row in range(page.table.rowCount())]
        assert levels == ["error", "error", "warn"]
        assert page.counts() == (2, 1)
        page.deleteLater()

    def test_clean_source_says_so(self, qapp):
        page = PreflightPage(FakeSettingsDataSource("empty"))
        assert page.table.rowCount() == 0
        assert "No problems found" in page.status_label.text()
        page.deleteLater()

    def test_counts_signal_fires_on_refresh(self, qapp):
        seen = []
        page = PreflightPage(FakeSettingsDataSource("rich"))
        page.diagnostics_changed.connect(lambda errors, warnings: seen.append((errors, warnings)))
        page.refresh()
        assert seen == [(0, 1)]
        page.deleteLater()

    def test_hint_shows_for_the_selected_issue(self, preflight_page):
        preflight_page.table.selectRow(0)
        assert preflight_page.detail_label.text()      # the fix hint

    def test_report_text_and_clipboard(self, preflight_page):
        text = preflight_page.report_text()
        assert text.startswith("[WARN] W_KEY_NOT_INJECTED")
        preflight_page.copy_btn.click()
        assert QGuiApplication.clipboard().text() == text

    def test_broken_source_does_not_raise(self, qapp):
        class _Stub:
            def diagnostics(self):
                raise RuntimeError("db down")

        page = PreflightPage(_Stub())  # type: ignore[arg-type]
        assert page.table.rowCount() == 0
        assert "Could not run checks" in page.status_label.text()
        assert page.counts() == (0, 0)
        page.deleteLater()
