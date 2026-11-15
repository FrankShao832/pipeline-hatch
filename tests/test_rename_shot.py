"""Rename Shot: only untouched shots, and the reasons a refusal is a refusal.

The interesting part is the gate, not the dialog: "is it empty?" is what makes a
rename safe, because an empty shot can never have reached a published filename
or an asset-library row. So ``shot_is_empty`` gets the most attention, the two
backends are checked for the same verdicts, and the dialog is pinned where it
could drift (enablement and the message the user actually reads).
"""

import os

import pytest
from PySide6.QtWidgets import QDialog, QTreeWidget, QTreeWidgetItem

from launcher.ui.fakes import FakeSettingsDataSource
from launcher.ui.real_source import shot_is_empty
from launcher.ui.widgets.rename_shot_dialog import RenameShotDialog
from launcher.ui.widgets.seq_shot_tree import SeqShotTreeWidget


# -- The gate ---------------------------------------------------------------

class TestShotIsEmpty:
    def test_empty_folder_is_empty(self, tmp_path):
        assert shot_is_empty(str(tmp_path)) is True

    def test_only_hidden_files_still_count_as_empty(self, tmp_path):
        # Finder writes .DS_Store just by looking at a folder; that is not work.
        (tmp_path / ".DS_Store").write_bytes(b"\x00")
        assert shot_is_empty(str(tmp_path)) is True

    def test_empty_department_folders_still_count_as_empty(self, tmp_path):
        # "Created the shot, launched a DCC once, saved nothing" is exactly the
        # case this feature exists for.
        (tmp_path / "fx").mkdir()
        (tmp_path / "comp").mkdir()
        assert shot_is_empty(str(tmp_path)) is True

    def test_a_file_anywhere_disqualifies_the_shot(self, tmp_path):
        (tmp_path / "fx").mkdir()
        (tmp_path / "fx" / "shot001_v001.hip").write_bytes(b"")
        assert shot_is_empty(str(tmp_path)) is False

    def test_a_file_at_the_top_disqualifies_the_shot(self, tmp_path):
        (tmp_path / "notes.txt").write_text("look at this")
        assert shot_is_empty(str(tmp_path)) is False


# -- Fake backend -----------------------------------------------------------

@pytest.fixture
def source():
    """Fixture backend with one freshly created (empty) shot in seq009."""
    src = FakeSettingsDataSource()
    src.add_shots("CyberPunk", [("seq009", "shot001")], dry_run=False)
    return src


class TestFakeBackend:
    def test_renames_an_untouched_shot(self, source):
        summary = source.rename_shot("CyberPunk", "seq009", "shot001", "shot031",
                                     dry_run=False)

        assert summary.ok
        assert summary.created[0].endswith("seq009/shot031")
        plan = source.plan_shots("CyberPunk", [("seq009", "shot031"),
                                               ("seq009", "shot001")])
        assert [row.status for row in plan] == ["exists", "new"]

    def test_dry_run_moves_nothing(self, source):
        summary = source.rename_shot("CyberPunk", "seq009", "shot001", "shot031",
                                     dry_run=True)

        assert summary.ok
        plan = source.plan_shots("CyberPunk", [("seq009", "shot001")])
        assert plan[0].status == "exists"

    def test_shot_with_work_in_it_is_refused(self, source):
        summary = source.rename_shot("CyberPunk", "seq001", "sh010", "sh011",
                                     dry_run=True)

        assert not summary.ok
        assert summary.diagnostics[0].code == "E_NOT_EMPTY"

    @pytest.mark.parametrize("new_name,code", [
        ("shot/031", "E_NAME"),
        ("shot 031", "E_NAME"),
        ("..", "E_NAME"),
        ("shot001", "E_SAME"),
    ])
    def test_unusable_names_are_refused(self, source, new_name, code):
        summary = source.rename_shot("CyberPunk", "seq009", "shot001", new_name,
                                     dry_run=True)

        assert not summary.ok
        assert summary.diagnostics[0].code == code

    def test_rename_never_overwrites(self, source):
        source.add_shots("CyberPunk", [("seq009", "shot002")], dry_run=False)

        summary = source.rename_shot("CyberPunk", "seq009", "shot001", "shot002",
                                     dry_run=True)

        assert not summary.ok
        assert summary.diagnostics[0].code == "E_EXISTS"

    def test_unknown_shot_is_refused(self, source):
        summary = source.rename_shot("CyberPunk", "seq009", "nope", "shot031",
                                     dry_run=True)

        assert not summary.ok
        assert summary.diagnostics[0].code == "E_NO_SHOT"


# -- Dialog -----------------------------------------------------------------

@pytest.fixture
def source_with_empty_shot():
    src = FakeSettingsDataSource()
    src.add_shots("CyberPunk", [("seq009", "shot001")], dry_run=False)
    return src


@pytest.fixture
def dialog(qapp, source_with_empty_shot):
    win = RenameShotDialog(source_with_empty_shot, "CyberPunk", "seq009", "shot001")
    win.show()
    yield win
    win._timer.stop()
    win.close()


class TestDialog:
    def test_opens_with_the_current_name_selected(self, dialog):
        assert dialog.edit.text() == "shot001"
        assert dialog.edit.selectedText() == "shot001"
        assert not dialog.rename_btn.isEnabled()      # nothing changed yet

    def test_arrow_shows_the_destination(self, dialog):
        dialog.edit.setText("shot031")
        dialog.refresh_plan()

        assert dialog.path_label.text() == "seq009/shot001  →  seq009/shot031"
        assert dialog.rename_btn.isEnabled()
        assert dialog.status_label.text() == "Will rename 1 folder"

    def test_malformed_name_blocks_the_button(self, dialog):
        dialog.edit.setText("shot/031")

        dialog.refresh_plan()

        assert not dialog.rename_btn.isEnabled()
        assert dialog.status_label.text() == 'shot no "/"'

    def test_unchanged_name_blocks_the_button(self, dialog):
        dialog.refresh_plan()

        assert not dialog.rename_btn.isEnabled()
        assert "nothing to rename" in dialog.status_label.text()

    def test_a_shot_with_work_in_it_is_refused_in_the_dialog(self, qapp,
                                                             source_with_empty_shot):
        win = RenameShotDialog(source_with_empty_shot, "CyberPunk", "seq001", "sh010")
        win.edit.setText("sh011")

        summary = win.refresh_plan()

        assert not win.rename_btn.isEnabled()
        assert "already has files" in win.status_label.text()
        assert summary is not None and not summary.ok
        win.close()

    def test_accept_renames_and_closes(self, dialog, source_with_empty_shot):
        dialog.edit.setText("shot031")
        dialog.refresh_plan()

        dialog._on_accept()

        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.summary is not None and dialog.summary.ok
        assert dialog.new_name == "shot031"
        plan = source_with_empty_shot.plan_shots("CyberPunk", [("seq009", "shot031")])
        assert plan[0].status == "exists"


# -- Tree -------------------------------------------------------------------

class TestTreeSignal:
    def test_shot_node_asks_for_a_rename(self, qapp):
        tree = SeqShotTreeWidget()
        sequence = QTreeWidgetItem(tree)
        sequence.setText(0, "seq009")
        shot = QTreeWidgetItem(sequence)
        shot.setText(0, "shot001")
        asked = []
        tree.rename_requested.connect(lambda seq, name: asked.append((seq, name)))

        assert tree._emit_rename_for(shot) is True
        assert asked == [("seq009", "shot001")]

    def test_sequence_node_has_nothing_to_rename(self, qapp):
        tree = SeqShotTreeWidget()
        sequence = QTreeWidgetItem(tree)
        sequence.setText(0, "seq009")
        asked = []
        tree.rename_requested.connect(lambda seq, name: asked.append((seq, name)))

        assert tree._emit_rename_for(sequence) is False
        assert asked == []
