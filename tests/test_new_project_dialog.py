"""Tests for the New Project dialog (execution card C7).

The dialog is a **dry run of the real call**, so most of these tests assert
parity rather than behaviour invented here: the number the preview quotes is the
number the run produces, the blockers that disable ``Create`` are the ones the
backend itself reports, and a failed run leaves the dialog open instead of
closing on a half-created project.
"""

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from launcher.ui.fakes import FakeSettingsDataSource
from launcher.ui.viewmodels import ApplySummary, DiagnosticRow
from launcher.ui.widgets.new_project_dialog import NewProjectDialog

ROOT = "/tmp/projects"
PUBLISH = "/tmp/publish"


@pytest.fixture
def ds():
    return FakeSettingsDataSource("rich")


@pytest.fixture
def dialog(qapp, ds):
    widget = NewProjectDialog(ds, root=ROOT, publish_root=PUBLISH)
    yield widget
    widget.deleteLater()


class StubSource:
    """A backend whose ``create_project`` says whatever the test needs."""

    def __init__(self, dry: ApplySummary, real: ApplySummary | None = None):
        self._dry = dry
        self._real = real or dry
        self.calls: list[bool] = []

    def validate_project(self, name, root, publish_root):
        return []

    def create_project(self, name, root, publish_root, options, dry_run):
        self.calls.append(dry_run)
        return self._dry if dry_run else self._real


class TestDefaults:
    def test_the_roots_are_prefilled_from_the_caller(self, dialog):
        assert dialog.root_edit.text() == ROOT
        assert dialog.publish_edit.text() == PUBLISH

    def test_create_is_disabled_until_there_is_a_name(self, dialog):
        assert dialog.create_btn.isEnabled() is False
        assert "Type a name" in dialog.plan_label.text()

        dialog.name_edit.setText("NewShow")

        assert dialog.create_btn.isEnabled() is True


class TestPlanPreview:
    def test_the_preview_counts_folders_and_overrides(self, dialog):
        dialog.name_edit.setText("NewShow")

        text = dialog.plan_label.text()

        # 2 required roots + 3 dev roots (cache/assets/renders) = 5 folders
        assert "Will create 5 folders" in text
        assert "will write 2 overrides" in text

    def test_the_preview_tracks_every_keystroke(self, dialog):
        dialog.name_edit.setText("A")
        first = dialog.plan_label.text()
        dialog.name_edit.setText("ASecondName")

        assert dialog.plan_label.text() == first      # same count, still re-planned
        assert "Will create 5 folders" in dialog.plan_label.text()

    def test_a_bad_name_blocks_and_explains(self, dialog):
        dialog.name_edit.setText("1Bad")

        assert dialog.create_btn.isEnabled() is False
        assert "Invalid project name" in dialog.issues_label.text()

    def test_a_relative_root_blocks(self, dialog):
        dialog.name_edit.setText("NewShow")
        dialog.root_edit.setText("relative/path")

        assert dialog.create_btn.isEnabled() is False
        assert "Root path must be absolute" in dialog.issues_label.text()

    def test_a_backend_failure_is_reported_not_raised(self, qapp):
        class Exploding(StubSource):
            def create_project(self, *args, **kwargs):
                raise RuntimeError("database is on fire")

        widget = NewProjectDialog(Exploding(ApplySummary()), parent=None)
        widget.name_edit.setText("NewShow")

        assert "database is on fire" in widget.issues_label.text()
        assert widget.create_btn.isEnabled() is False
        widget.deleteLater()


class TestCreating:
    def test_creating_adds_the_project_and_seeds_its_environment(self, dialog, ds):
        dialog.name_edit.setText("NewShow")

        dialog.create_btn.click()

        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.project_name == "NewShow"
        assert "NewShow" in {row.name for row in ds.projects()}
        assert dialog.summary.env_written == 2
        seeded = {(r.name, r.scope, r.scope_key): r.value
                  for r in ds.env_rows() if r.scope_key == "NewShow"}
        assert seeded[("OCIO", "show", "NewShow")] == "${DEV}/color/aces_cg.ocio"
        assert seeded[("FPS", "show", "NewShow")] == "24"

    def test_the_run_is_the_plan(self, dialog, ds):
        """The preview's numbers and the real write agree — that is the point."""
        dialog.name_edit.setText("NewShow")
        planned = dialog.planned()

        dialog.create_btn.click()

        assert dialog.summary.env_written == planned.env_written
        assert len(dialog.summary.created) == len(planned.created)

    def test_a_failed_run_keeps_the_dialog_open(self, qapp):
        failure = ApplySummary(
            errors=(("NewShow", "database: could not create row"),),
            diagnostics=(DiagnosticRow("error", "E_PROJECT",
                                       "database: could not create row",
                                       target="NewShow"),))
        source = StubSource(dry=ApplySummary(created=("/tmp/x",), env_written=2),
                            real=failure)
        widget = NewProjectDialog(source, root=ROOT, publish_root=PUBLISH)
        widget.name_edit.setText("NewShow")

        widget.create_btn.click()

        assert widget.result() != QDialog.DialogCode.Accepted
        assert widget.project_name == ""
        assert "could not create row" in widget.issues_label.text()
        widget.deleteLater()

    def test_planning_never_writes(self, dialog, ds):
        dialog.name_edit.setText("NewShow")
        dialog.name_edit.setText("Another")

        assert {row.name for row in ds.projects()} == {
            "CyberPunk", "DragonLand", "SpaceOdyssey"}


class WarningSource(StubSource):
    """A backend whose warnings only show up once a name is typed.

    That is the real shape of it: ``W_ROOT`` / ``W_PUB`` talk about
    ``<root>/<name>``, so an unnamed project has nothing to warn about yet and
    the orange text arrives with the first keystrokes.
    """

    def __init__(self, warnings: int = 2):
        super().__init__(dry=ApplySummary(created=("/tmp/x",), env_written=2))
        self._warnings = warnings

    def validate_project(self, name, root, publish_root):
        if not name:
            return []
        return [
            DiagnosticRow("warn", f"W_TEST{i}",
                          f"Publish folder does not exist: {publish_root}/{name} — "
                          f"repairing the scaffold from the Projects page creates "
                          f"the missing folders and leaves what exists alone ({i})",
                          target=name)
            for i in range(self._warnings)
        ]


@pytest.fixture
def shown(qapp):
    """A shown dialog, so geometry means something (it is right on open)."""
    widgets = []

    def build(warnings: int = 2):
        widget = NewProjectDialog(WarningSource(warnings), root=ROOT,
                                  publish_root=PUBLISH)
        widget.show()
        QApplication.processEvents()
        widgets.append(widget)
        return widget

    yield build
    for widget in widgets:
        widget.close()
        widget.deleteLater()


class TestTheWindowFollowsItsText:
    """Typing a name brings a plan line and, usually, orange warnings.

    The dialog keeps the height it was opened with, so that text used to be
    paid for by the rows above it — the two path fields lost height the moment
    a warning showed up. The window follows the content instead.
    """

    def test_a_warning_makes_the_window_taller(self, shown):
        dialog = shown()
        before = dialog.height()

        dialog.name_edit.setText("NewShow")
        QApplication.processEvents()

        assert dialog.height() > before

    def test_the_window_is_never_shorter_than_its_text(self, shown):
        dialog = shown()
        dialog.name_edit.setText("NewShow")
        QApplication.processEvents()

        assert dialog.height() >= dialog.layout().heightForWidth(dialog.width())

    def test_the_path_rows_keep_their_height(self, shown):
        dialog = shown()
        before = (dialog.name_edit.height(), dialog.root_edit.height(),
                  dialog.publish_edit.height())

        dialog.name_edit.setText("NewShow")
        QApplication.processEvents()

        assert (dialog.name_edit.height(), dialog.root_edit.height(),
                dialog.publish_edit.height()) == before

    def test_wrapped_text_is_never_clipped(self, shown):
        dialog = shown(warnings=3)
        dialog.name_edit.setText("NewShow")
        QApplication.processEvents()

        for label in dialog.findChildren(QLabel):
            if not label.text():
                continue
            assert label.height() >= label.heightForWidth(label.width()), label.text()

    def test_the_window_shrinks_back_when_the_text_goes(self, shown):
        dialog = shown()
        dialog.name_edit.setText("NewShow")
        QApplication.processEvents()
        tall = dialog.height()

        dialog.name_edit.setText("")
        QApplication.processEvents()

        assert dialog.height() < tall

    def test_the_width_does_not_drift(self, shown):
        dialog = shown()
        width = dialog.width()

        dialog.name_edit.setText("NewShow")
        QApplication.processEvents()

        assert dialog.width() == width

    def test_a_wall_of_warnings_stops_at_the_screen_edge(self, shown):
        dialog = shown(warnings=12)
        dialog.name_edit.setText("NewShow")
        QApplication.processEvents()

        assert dialog.height() <= dialog.screen().availableGeometry().height()
