"""Rename one shot folder — narrow on purpose.

The scope is a single case: a shot that was just created with a wrong name and
still has nothing in it. That is not laziness, it is the only case where a rename
is complete:

* no files  -> nothing was ever published
* nothing published -> the old name is not yet inside ``shot001_v001.ma``, not yet
  in a publish path, not yet in an ``assets.name``
* so an ``os.rename`` is the *whole* operation, not the first third of one

Two refusals the dialog does not negotiate:

* **files already in the shot** — the name is in the files by then;
* **the target name already exists** — renaming never overwrites a shot.

Everything else (rename after publish, delete, batch renames) is deliberately
out of scope and gets its own shape later.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from launcher.ui.viewmodels import (
    ApplySummary,
    SettingsDataSource,
    shot_name_problem,
)

MUTED = "color: #8b94a3;"
ERROR = "color: #e5484d;"
OK = "color: #30a46c;"

#: How long typing may pause before the backend is asked (milliseconds).
PLAN_DELAY_MS = 120


class RenameShotDialog(QDialog):
    """Rename a shot, with the refusal reasons shown before the click."""

    def __init__(self, data_source: SettingsDataSource, project: str,
                 sequence: str, shot: str, parent: QWidget | None = None) -> None:
        """Build the dialog.

        Args:
            data_source: Backend implementing ``SettingsDataSource``.
            project: Show the shot belongs to.
            sequence: Sequence holding the shot.
            shot: Current shot name (the one to replace).
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._data_source = data_source
        self.project = project
        self.sequence = sequence
        self.old_name = shot
        self.new_name = shot
        self.summary: ApplySummary | None = None
        #: Result of the last successful dry run, kept for tests and preview.
        self.preview: ApplySummary | None = None

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(PLAN_DELAY_MS)
        self._timer.timeout.connect(self.refresh_plan)

        self.setWindowTitle("Rename Shot")
        self.setModal(True)
        self.setMinimumWidth(420)
        self._build_ui()
        self.refresh_plan()

    # -- Construction ------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 12)
        outer.setSpacing(8)

        intro = QLabel(
            f"Rename <b>{self.sequence}/{self.old_name}</b> in {self.project}.")
        intro.setWordWrap(True)
        outer.addWidget(intro)

        self.edit = QLineEdit(self.old_name)
        self.edit.setPlaceholderText("shot001")
        self.edit.setToolTip("Letters, digits, underscores, hyphens — one path segment")
        self.edit.textChanged.connect(lambda _text: self._timer.start())
        self.edit.returnPressed.connect(self._on_accept)
        outer.addWidget(self.edit)

        self.path_label = QLabel("")
        self.path_label.setStyleSheet(MUTED)
        self.path_label.setWordWrap(True)
        outer.addWidget(self.path_label)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok)
        self.rename_btn = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.rename_btn.setText("Rename")
        self.rename_btn.setEnabled(False)
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

        self.edit.selectAll()
        self.edit.setFocus()

    # -- Planning ----------------------------------------------------------

    def refresh_plan(self) -> ApplySummary | None:
        """Re-check the typed name and enable ``Rename`` only when it can work.

        Returns:
            The dry run that made the current verdict, or ``None`` when the name
            never reached the backend (empty, malformed, unchanged).
        """
        self._timer.stop()
        name = self.edit.text().strip()
        self.new_name = name
        self.preview = None
        self.path_label.setText(f"{self.sequence}/{self.old_name}  →  "
                                f"{self.sequence}/{name or '…'}")

        if not name:
            self._verdict("Type a new name.", MUTED, enabled=False)
            return None
        problem = shot_name_problem(name)
        if problem:
            self._verdict(f"shot {problem}", ERROR, enabled=False)
            return None
        if name == self.old_name:
            self._verdict("Same name — nothing to rename.", MUTED, enabled=False)
            return None

        try:
            summary = self._data_source.rename_shot(
                self.project, self.sequence, self.old_name, name, dry_run=True)
        except Exception as exc:                # noqa: BLE001 — surface, don't crash
            self._verdict(f"Cannot check: {exc}", ERROR, enabled=False)
            return None

        self.preview = summary
        if not summary.ok:
            reason = summary.diagnostics[0].message if summary.diagnostics \
                else "Not possible."
            self._verdict(reason, ERROR, enabled=False)
            return summary

        self._verdict("Will rename 1 folder", OK, enabled=True)
        return summary

    def _verdict(self, text: str, colour: str, enabled: bool) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(colour)
        self.rename_btn.setEnabled(enabled)

    # -- Applying ----------------------------------------------------------

    def _on_accept(self) -> None:
        """Run the rename; only a clean result closes the dialog."""
        if not self.rename_btn.isEnabled():
            return
        try:
            summary = self._data_source.rename_shot(
                self.project, self.sequence, self.old_name, self.new_name,
                dry_run=False)
        except Exception as exc:                # noqa: BLE001 — surface, don't crash
            self._verdict(f"Rename failed: {exc}", ERROR, enabled=False)
            return
        self.summary = summary
        if not summary.ok:
            reason = summary.diagnostics[0].message if summary.diagnostics \
                else "Rename failed."
            self._verdict(reason, ERROR, enabled=False)
            return
        self.accept()
