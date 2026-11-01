"""Add Shots: the batch rules, the two backends, and the dialog.

The thing worth testing here is the *classification*, not the widgets: a shot
folder either already exists, or is about to be created, or cannot be named at
all — and the answer must be the same one the preview showed. So the pure
functions get the most attention, both backends are checked against them, and
the dialog is pinned only where it could drift (badges, totals, the prefill on
``+ Add row``, and what ``Create`` actually sends).
"""

import os

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from launcher.ui.fakes import FakeSettingsDataSource
from launcher.ui.real_source import RealSettingsDataSource
from launcher.ui.viewmodels import (
    SHOT_STATUS_DUPLICATE,
    SHOT_STATUS_EXISTS,
    SHOT_STATUS_INVALID,
    SHOT_STATUS_NEW,
    classify_shots,
    next_shot_name,
    shot_counts,
    shot_name_problem,
    split_field,
)
from launcher.ui.widgets.add_shots_dialog import ROW_HEIGHT, AddShotsDialog


# -- Pure rules -------------------------------------------------------------

class TestNames:
    def test_split_field_accepts_commas_semicolons_and_whitespace(self):
        assert split_field("shot010, shot011;shot012  shot013") == [
            "shot010", "shot011", "shot012", "shot013"]

    def test_split_field_of_empty_is_empty(self):
        assert split_field("") == []
        assert split_field("   ") == []

    @pytest.mark.parametrize("name,problem", [
        ("", "empty"),
        ("seq/001", 'no "/"'),
        ("seq\\001", 'no "/"'),
        ("..", "no leading ."),
        (".hidden", "no leading ."),
        ("sh 010", "no spaces"),
        ("sh010", ""),
        ("sh_010", ""),
    ])
    def test_shot_name_problem(self, name, problem):
        assert shot_name_problem(name) == problem

    @pytest.mark.parametrize("previous,expected", [
        ("shot001", "shot002"),
        ("shot009", "shot010"),
        ("sh_0010", "sh_0011"),
        ("shot9", "shot10"),
        ("shot", ""),
        ("", ""),
    ])
    def test_next_shot_name_continues_the_typed_pattern(self, previous, expected):
        assert next_shot_name(previous) == expected


class TestClassify:
    def _classify(self, pairs, existing=()):
        existing = set(existing)
        return classify_shots(
            pairs,
            lambda seq, shot: f"/show/{seq}/{shot}" if shot else f"/show/{seq}",
            lambda path: path in existing,
        )

    def test_new_existing_and_duplicate(self):
        rows = self._classify(
            [("seq001", "sh010"), ("seq001", "sh010")],
            existing={"/show/seq001", "/show/seq001/sh010"})

        assert [row.status for row in rows] == [
            SHOT_STATUS_EXISTS, SHOT_STATUS_DUPLICATE]

    def test_new_shot_in_existing_sequence_is_not_a_new_sequence(self):
        rows = self._classify([("seq001", "sh030")], existing={"/show/seq001"})

        assert rows[0].status == SHOT_STATUS_NEW
        assert rows[0].new_sequence is False

    def test_new_shot_in_unknown_sequence_reports_the_new_sequence(self):
        rows = self._classify([("seq009", "sh010")], existing=set())

        assert rows[0].status == SHOT_STATUS_NEW
        assert rows[0].new_sequence is True

    def test_invalid_names_never_get_a_path(self):
        rows = self._classify([("seq/001", "sh010"), ("seq001", "..")])

        assert [row.status for row in rows] == [SHOT_STATUS_INVALID] * 2
        assert rows[0].path == ""
        assert rows[0].message == 'sequence no "/"'
        assert rows[1].message == "shot no leading ."

    def test_order_is_preserved(self):
        rows = self._classify(
            [("seq002", "sh010"), ("seq001", "sh030")],
            existing={"/show/seq002"})

        assert [(r.sequence, r.shot) for r in rows] == [
            ("seq002", "sh010"), ("seq001", "sh030")]

    def test_counts_include_every_status(self):
        rows = self._classify([("seq001", "sh030")], existing={"/show/seq001"})

        assert shot_counts(rows) == {
            SHOT_STATUS_NEW: 1, SHOT_STATUS_EXISTS: 0,
            SHOT_STATUS_DUPLICATE: 0, SHOT_STATUS_INVALID: 0}


# -- Backends ---------------------------------------------------------------

class TestFakeBackend:
    def test_sequences_come_from_the_fixture_state(self):
        source = FakeSettingsDataSource()

        assert source.sequences("CyberPunk") == ["seq001", "seq002"]
        assert source.sequences("DragonLand") == []       # scaffold_state: missing

    def test_shots_come_from_the_fixture_state(self):
        source = FakeSettingsDataSource()

        assert source.shots("CyberPunk", "seq001") == ["sh010", "sh020"]
        assert source.shots("CyberPunk", "seq009") == []

    def test_plan_mixes_existing_and_new(self):
        source = FakeSettingsDataSource()

        rows = source.plan_shots("CyberPunk", [("seq001", "sh010"),
                                              ("seq001", "sh030")])

        assert [row.status for row in rows] == [SHOT_STATUS_EXISTS, SHOT_STATUS_NEW]

    def test_dry_run_does_not_move_the_fixture(self):
        source = FakeSettingsDataSource()

        summary = source.add_shots("CyberPunk", [("seq001", "sh030")], dry_run=True)

        assert summary.created
        assert source.plan_shots("CyberPunk", [("seq001", "sh030")])[0].status \
            == SHOT_STATUS_NEW

    def test_second_run_is_idempotent(self):
        source = FakeSettingsDataSource()
        batch = [("seq001", "sh030"), ("seq001", "sh031")]

        first = source.add_shots("CyberPunk", batch, dry_run=False)
        second = source.add_shots("CyberPunk", batch, dry_run=False)

        assert len(first.created) == 2
        assert second.created == ()
        assert len(second.skipped) == 2

    def test_invalid_rows_block_the_whole_batch(self):
        source = FakeSettingsDataSource()

        summary = source.add_shots("CyberPunk", [("seq001", "sh030"),
                                                ("seq/001", "sh031")],
                                   dry_run=False)

        assert not summary.ok
        assert summary.created == ()
        assert any("E_SHOTNAME" == row.code for row in summary.diagnostics)
        # Nothing was applied: the valid row is still new.
        assert source.plan_shots("CyberPunk", [("seq001", "sh030")])[0].status \
            == SHOT_STATUS_NEW


@pytest.fixture
def real_source(tmp_path):
    """Live backend, read-only here: these tests never write to the show tree."""
    from launcher.database.database import DatabaseManager

    db = DatabaseManager()
    db.connect()
    src = RealSettingsDataSource(db=db, env_store_path=tmp_path / "env.yaml")
    if not src.db.is_connected:
        pytest.skip("launcher database not available")
    return src


class TestRealBackend:
    def test_plan_reads_the_tree_on_disk(self, real_source):
        rows = real_source.projects()
        show = next((row for row in rows if row.seqs and row.shots), None)
        if show is None:
            pytest.skip("no project with sequences and shots on disk")
        sequences = real_source.sequences(show.name)
        shot = os.listdir(os.path.join(show.root, show.name, sequences[0]))[0]

        plan = real_source.plan_shots(show.name, [
            (sequences[0], shot), (sequences[0], "zz_made_up_shot")])

        assert [row.status for row in plan] == [SHOT_STATUS_EXISTS, SHOT_STATUS_NEW]

    def test_shots_come_from_the_tree_on_disk(self, real_source):
        show = next((row for row in real_source.projects() if row.seqs), None)
        if show is None:
            pytest.skip("no project with sequences on disk")
        sequence = real_source.sequences(show.name)[0]

        assert real_source.shots(show.name, sequence) == sorted(
            os.listdir(os.path.join(show.root, show.name, sequence)))
        assert real_source.shots(show.name, "") == []

    def test_dry_run_creates_nothing(self, real_source):
        rows = real_source.projects()
        show = next((row for row in rows if row.seqs), None)
        if show is None:
            pytest.skip("no project with sequences on disk")
        sequence = real_source.sequences(show.name)[0]

        summary = real_source.add_shots(
            show.name, [(sequence, "zz_dry_run_shot")], dry_run=True)

        assert summary.created
        assert all(not os.path.exists(path) for path in summary.created)

    def test_unknown_project_is_an_error_not_a_crash(self, real_source):
        summary = real_source.add_shots("NoSuchShow", [("seq001", "sh010")],
                                        dry_run=False)

        assert not summary.ok
        assert summary.diagnostics[0].code == "E_PROJECT"


# -- Dialog -----------------------------------------------------------------

@pytest.fixture
def dialog(qapp):
    source = FakeSettingsDataSource()
    win = AddShotsDialog(source, "CyberPunk")
    win.show()                      # geometry is real only once shown
    yield win
    win._timer.stop()
    win.close()


class TestDialog:
    def test_opens_with_one_row_and_the_last_sequence(self, dialog):
        assert len(dialog._rows) == 1
        assert dialog._rows[0].entry() == ("seq002", "")
        assert not dialog._rows[0].remove_btn.isEnabled()

    def test_add_row_inherits_the_sequence_and_continues_the_number(self, dialog):
        dialog._rows[0].shot_edit.setText("shot001")

        dialog.add_row()

        assert dialog._rows[1].entry() == ("seq002", "shot002")
        assert dialog._rows[0].remove_btn.isEnabled()

    def test_remove_keeps_at_least_one_row(self, dialog):
        second = dialog.add_row()

        dialog.remove_row(dialog._rows[0])

        assert dialog._rows == [second]
        assert not second.remove_btn.isEnabled()

    def test_badges_say_new_exists_and_invalid(self, dialog):
        row = dialog._rows[0]
        row.seq_edit.setCurrentText("seq001")
        row.shot_edit.setText("sh010")
        dialog.refresh_plan()
        assert row.status_label.text() == "exists"

        row.shot_edit.setText("sh030")
        dialog.refresh_plan()
        assert row.status_label.text() == "new"

        row.seq_edit.setCurrentText("seq/001")
        dialog.refresh_plan()
        assert row.status_label.text() == 'sequence no "/"'

    def test_totals_quote_the_plan(self, dialog):
        row = dialog._rows[0]
        row.seq_edit.setCurrentText("seq001")
        row.shot_edit.setText("sh030")
        dialog.refresh_plan()

        assert "Will create 1 folder" in dialog.plan_label.text()
        assert dialog.create_btn.isEnabled()

    def test_existing_shots_are_reported_not_blocked(self, dialog):
        row = dialog._rows[0]
        row.seq_edit.setCurrentText("seq001")
        row.shot_edit.setText("sh010")
        dialog.refresh_plan()

        assert "0 folders" in dialog.plan_label.text()
        assert "1 already there" in dialog.plan_label.text()
        assert dialog.create_btn.isEnabled()

    def test_invalid_name_disables_create(self, dialog):
        row = dialog._rows[0]
        row.seq_edit.setCurrentText("seq001")
        row.shot_edit.setText("sh/030")
        dialog.refresh_plan()

        assert not dialog.create_btn.isEnabled()

    def test_empty_row_disables_create(self, dialog):
        dialog._rows[0].seq_edit.setCurrentText("")
        dialog.refresh_plan()

        assert not dialog.create_btn.isEnabled()
        assert "Type a sequence" in dialog.plan_label.text()

    def test_one_shot_field_may_hold_several_names(self, dialog):
        row = dialog._rows[0]
        row.seq_edit.setCurrentText("seq001")
        row.shot_edit.setText("sh030, sh031")
        dialog.refresh_plan()

        assert dialog.entries() == [("seq001", "sh030"), ("seq001", "sh031")]
        assert "2 new" == row.status_label.text()

    def test_several_sequences_in_one_batch(self, dialog):
        first = dialog._rows[0]
        first.seq_edit.setCurrentText("seq001")
        first.shot_edit.setText("sh030")
        second = dialog.add_row(sequence="seq009", shot="sh001")
        dialog.refresh_plan()

        assert "1 new sequence" in dialog.plan_label.text()
        assert second.status_label.text() == "new"

    def test_create_sends_the_batch_and_reports_the_last_shot(self, dialog):
        row = dialog._rows[0]
        row.seq_edit.setCurrentText("seq001")
        row.shot_edit.setText("sh030, sh031")
        dialog.refresh_plan()

        dialog._on_create()

        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.summary is not None and dialog.summary.ok
        assert len(dialog.summary.created) == 2
        assert dialog.last_created == ("seq001", "sh031")

    def test_shot_placeholder_continues_the_naming_already_in_use(self, dialog):
        dialog.refresh_plan()

        # seq002 already holds sh010 / sh020, so the hint shows the next number
        # in that pattern rather than a generic example.
        assert dialog._rows[0].shot_edit.placeholderText() == "e.g. sh021"

    def test_shot_tooltip_lists_what_is_already_there(self, dialog):
        dialog.refresh_plan()

        tooltip = dialog._rows[0].shot_edit.toolTip()
        assert "sh010" in tooltip and "sh020" in tooltip

    def test_new_sequence_falls_back_to_a_generic_example(self, dialog):
        row = dialog._rows[0]
        row.seq_edit.setCurrentText("seq009")

        dialog.refresh_plan()

        assert row.shot_edit.placeholderText() == "e.g. shot001"
        assert row.shot_edit.toolTip() == "No shots in this sequence yet"

    def test_window_grows_when_rows_are_added(self, dialog):
        before = dialog.height()

        dialog.add_row()
        dialog.add_row()

        assert dialog.height() > before

    def test_window_shrinks_when_rows_are_removed(self, dialog):
        second = dialog.add_row()
        dialog.add_row()
        tall = dialog.height()

        dialog.remove_row(second)

        assert dialog.height() < tall

    def test_huge_batch_scrolls_instead_of_running_off_screen(self, dialog):
        # Enough rows to pass whatever the screen allows, so this holds on a
        # laptop and on a 27" alike.
        needed = dialog._max_list_height() // ROW_HEIGHT + 5
        for _ in range(needed):
            dialog.add_row(sequence="seq001", shot="sh001")
        QApplication.processEvents()

        assert dialog.scroll.verticalScrollBar().maximum() > 0
        assert dialog.height() <= dialog.screen().availableGeometry().height()

    def test_half_filled_row_says_no_shot_yet(self, dialog):
        dialog.refresh_plan()

        # The default row has a sequence but no shot: it is not an error, it is
        # simply not part of the batch yet.
        assert dialog._rows[0].status_label.text() == "no shot yet"
        assert dialog.entries() == []
        assert not dialog.create_btn.isEnabled()

    def test_shot_without_a_sequence_is_invalid(self, dialog):
        row = dialog._rows[0]
        row.seq_edit.setCurrentText("")
        row.shot_edit.setText("sh010")
        dialog.refresh_plan()

        assert row.status_label.text() == "sequence empty"
        assert "not usable" in dialog.plan_label.text()
        assert not dialog.create_btn.isEnabled()
