"""Add Shots — a batch of (sequence, shot) pairs, previewed before it is made.

Creating a project is a 0 -> 1 act and happens once. Shots arrive in batches for
the whole life of the show, and a sequence shows up with forty of them at once —
which is why the interesting part of this dialog is not the form but the
*classification*: which rows are new, which already exist, which contradict each
other, decided before the first ``mkdir``.

Three things the dialog deliberately does not do:

* **It never invents a shot number.** ``+ Add row`` may continue the pattern the
  user just typed (``shot001`` -> ``shot002``), but that is sparing typing, not
  assigning numbers — those belong to editorial.
* **It never creates a sequence on its own.** An empty sequence folder is noise,
  so a sequence is only ever the parent of a shot: typed, inherited from the row
  above, or picked from what is already on disk.
* **It never reports an existing shot as a failure.** Re-running the batch says
  ``0 created · 3 already there``; only an unusable name blocks.

Every judgement comes from :func:`launcher.ui.viewmodels.classify_shots` — the
same function the real backend applies — so the badges cannot drift from what
``Create`` actually does.

The plan is recomputed on a short timer rather than on every keystroke: the
backend answers by reading the project row (a database round trip), and typing
``shot001`` would otherwise ask twelve times.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from launcher.ui.viewmodels import (
    SHOT_STATUS_DUPLICATE,
    SHOT_STATUS_EXISTS,
    SHOT_STATUS_INVALID,
    SHOT_STATUS_NEW,
    ApplySummary,
    DiagnosticRow,
    SettingsDataSource,
    ShotPlanRow,
    next_shot_name,
    shot_counts,
    split_field,
)

MUTED = "color: #8b94a3;"
ERROR = "color: #e5484d;"
OK = "color: #30a46c;"

#: How long typing may pause before the plan is recomputed (milliseconds).
PLAN_DELAY_MS = 120

#: Badge colours, as bare hex values — the badge stylesheet adds the property.
_STATUS_COLORS = {
    SHOT_STATUS_NEW: "#30a46c",
    SHOT_STATUS_EXISTS: "#8b94a3",
    SHOT_STATUS_DUPLICATE: "#8b94a3",
    SHOT_STATUS_INVALID: "#e5484d",
}

#: Width of the per-row badge, shared with the caption row so the columns line up.
STATUS_WIDTH = 96

#: One row's height in the list (the fields plus the layout spacing).
ROW_HEIGHT = 30

#: Everything in the dialog except the row list: intro, captions, the button
#: row, the summary line and the margins. Used to decide how many rows still
#: fit on screen before the list has to scroll.
CHROME_HEIGHT = 260


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


class ShotRow(QWidget):
    """One editable ``(sequence, shot)`` row: ✕ on the left, then the two fields.

    Signals:
        changed: Emitted whenever a field is edited, so the dialog can re-plan.
        remove_requested: Emitted with ``self`` when ✕ is pressed; the dialog
            owns the row list and decides whether removal is allowed.
        submitted: Emitted when Enter is pressed in the shot field (the dialog
            uses it to grow a new row, Excel style).
    """

    changed = Signal()
    remove_requested = Signal(object)
    submitted = Signal()

    def __init__(self, sequences: Sequence[str], sequence: str = "",
                 shot: str = "", parent: QWidget | None = None) -> None:
        """Build one row.

        Args:
            sequences: Sequence folders already on disk (autocompletion only —
                a new name may still be typed).
            sequence: Initial sequence name.
            shot: Initial shot name.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        # ✕ on the left: the eye lands on the row, not on a column of buttons at
        # the far right edge, and removing is a row-level act.
        self.remove_btn = QPushButton("\u00d7")
        self.remove_btn.setFixedWidth(22)
        self.remove_btn.setStyleSheet("font-size: 14px;")
        self.remove_btn.setToolTip("Remove this row")
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        row.addWidget(self.remove_btn)

        self.seq_edit = QComboBox()
        self.seq_edit.setEditable(True)
        self.seq_edit.addItem("")
        self.seq_edit.addItems(list(sequences))
        self.seq_edit.setCurrentText(sequence)
        if self.seq_edit.lineEdit() is not None:
            self.seq_edit.lineEdit().setPlaceholderText("seq001")
        self.seq_edit.currentTextChanged.connect(lambda _text: self.changed.emit())
        row.addWidget(self.seq_edit, 2)

        self.shot_edit = QLineEdit(shot)
        self.shot_edit.setPlaceholderText("shot001")
        self.shot_edit.textChanged.connect(lambda _text: self.changed.emit())
        self.shot_edit.returnPressed.connect(self.submitted.emit)
        row.addWidget(self.shot_edit, 3)

        self.status_label = QLabel("")
        self.status_label.setFixedWidth(STATUS_WIDTH)
        self.status_label.setToolTip(
            "new · will be created   exists · skipped   "
            "duplicate · listed twice   invalid · cannot be used")
        row.addWidget(self.status_label)

    # -- Data --------------------------------------------------------------

    def entry(self) -> tuple[str, str]:
        """Return the trimmed ``(sequence, shot)`` currently in the fields."""
        return (self.seq_edit.currentText().strip(), self.shot_edit.text().strip())

    def set_name_hint(self, existing: Sequence[str]) -> None:
        """Show the naming already in use in this sequence as the placeholder.

        The example is the *next* number after the last existing shot, because
        that is what the pattern on disk implies. It is a placeholder, never a
        value: editorial owns shot numbers, so nothing here is typed for the
        user, and nothing is silently written.
        """
        sample = existing[-1] if existing else ""
        following = next_shot_name(sample) or sample or "shot001"
        self.shot_edit.setPlaceholderText(f"e.g. {following}")
        if existing:
            shown = ", ".join(existing[:8]) + (" …" if len(existing) > 8 else "")
            self.shot_edit.setToolTip(
                f"Already in this sequence ({len(existing)}): {shown}")
        else:
            self.shot_edit.setToolTip("No shots in this sequence yet")

    def set_status(self, status: str, message: str = "") -> None:
        """Show the row's verdict: a short word, coloured by severity."""
        self.status_label.setText(message or status)
        self.status_label.setStyleSheet(
            f"color: {_STATUS_COLORS.get(status, '#8b94a3')}; font-size: 11px;")


class AddShotsDialog(QDialog):
    """Bulk-create shot folders under one project, with a live preview.

    Signals:
        None — the caller reads :attr:`summary` and :attr:`last_created` after
        ``exec()`` returns ``Accepted``.
    """

    def __init__(self, data_source: SettingsDataSource, project: str,
                 sequence: str = "", parent: QWidget | None = None) -> None:
        """Build the dialog for one project.

        Args:
            data_source: Backend implementing ``SettingsDataSource``.
            project: Show to add shots to (the panel's selected project).
            sequence: Sequence to start with; the last existing one is used when
                empty, because new shots usually join the sequence in progress.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._data_source = data_source
        self.project = project
        self.summary: ApplySummary | None = None
        self.last_created: tuple[str, str] = ("", "")
        #: The plan the rows currently show — reused by ``_on_create`` so the
        #: reported "last created" is what the preview promised.
        self.plan_rows: tuple[ShotPlanRow, ...] = ()

        self._sequences = self._load_sequences()
        #: ``sequence -> shot names`` for the placeholder hint. Cached because a
        #: hint is a nicety, not a gate: it must never slow typing or block a row.
        self._hints: dict[str, list[str]] = {}
        self._rows: list[ShotRow] = []

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(PLAN_DELAY_MS)
        self._timer.timeout.connect(self.refresh_plan)

        self.setWindowTitle("Add Shots")
        self.setModal(True)
        self.setMinimumWidth(560)
        self._build_ui(sequence or (self._sequences[-1] if self._sequences else ""))
        self.refresh_plan()

    # -- Construction ------------------------------------------------------

    def _load_sequences(self) -> list[str]:
        """Sequence folders already on disk, for autocompletion only."""
        try:
            return list(self._data_source.sequences(self.project))
        except Exception:                       # noqa: BLE001 — a lookup, not a gate
            return []

    def _shots_in(self, sequence: str) -> list[str]:
        """Existing shot names in *sequence*, cached for the naming hint."""
        if not sequence:
            return []
        if sequence not in self._hints:
            try:
                self._hints[sequence] = list(
                    self._data_source.shots(self.project, sequence))
            except Exception:                   # noqa: BLE001 — a hint, not a gate
                self._hints[sequence] = []
        return self._hints[sequence]

    def _build_ui(self, sequence: str) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 12)
        outer.setSpacing(8)

        intro = QLabel(f"Add shots to <b>{self.project}</b>.")
        intro.setWordWrap(True)
        intro.setStyleSheet(MUTED)
        outer.addWidget(intro)

        caption = QHBoxLayout()
        caption.setContentsMargins(0, 0, 0, 0)
        caption.setSpacing(6)
        caption.addSpacing(28)                  # the ✕ column
        for text, stretch in (("Sequence", 2), ("Shot", 3)):
            label = QLabel(text)
            label.setStyleSheet(MUTED)
            caption.addWidget(label, stretch)
        caption.addSpacing(STATUS_WIDTH)
        outer.addLayout(caption)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setMinimumHeight(ROW_HEIGHT + 8)
        holder = QWidget()
        #: The row container; its minimum height is what makes the list scroll
        #: once the window may not grow any further.
        self.holder = holder
        self.rows_box = QVBoxLayout(holder)
        self.rows_box.setContentsMargins(0, 0, 0, 0)
        self.rows_box.setSpacing(6)
        self.rows_box.addStretch(1)
        self.scroll.setWidget(holder)
        outer.addWidget(self.scroll)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        add_row.addStretch(1)
        self.add_row_btn = QPushButton("+ Add row")
        self.add_row_btn.setToolTip("Add another sequence/shot pair")
        self.add_row_btn.clicked.connect(lambda: self.add_row())
        add_row.addWidget(self.add_row_btn)
        outer.addLayout(add_row)

        self.plan_label = QLabel("")
        self.plan_label.setWordWrap(True)
        outer.addWidget(self.plan_label)

        self.issues_label = QLabel("")
        self.issues_label.setWordWrap(True)
        self.issues_label.setStyleSheet(ERROR)
        self.issues_label.setVisible(False)
        outer.addWidget(self.issues_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok)
        self.create_btn = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.create_btn.setText("Create")
        self.buttons.accepted.connect(self._on_create)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

        self.add_row(sequence=sequence)

    # -- Rows --------------------------------------------------------------

    def add_row(self, sequence: str | None = None,
                shot: str | None = None) -> ShotRow:
        """Append a row, inheriting the sequence above and continuing its number.

        Args:
            sequence: Sequence name; defaults to the row above (Excel behaviour —
                most batches stay inside one sequence and retyping invites the
                ``seq001``/``seq00l`` split).
            shot: Shot name; defaults to the previous row's name with its
                trailing number advanced.

        Returns:
            The new row.
        """
        if self._rows:
            previous_sequence, previous_shot = self._rows[-1].entry()
        else:
            previous_sequence, previous_shot = "", ""
        if sequence is None:
            sequence = previous_sequence
        if shot is None:
            shot = next_shot_name(previous_shot)

        row = ShotRow(self._sequences, sequence, shot, self)
        row.changed.connect(self._schedule_plan)
        row.remove_requested.connect(self.remove_row)
        row.submitted.connect(self._on_submitted)
        self._rows.append(row)
        self.rows_box.insertWidget(len(self._rows) - 1, row)
        self._sync_remove_buttons()
        self._fit_rows(reveal=row)
        self._schedule_plan()
        return row

    def remove_row(self, row: ShotRow) -> None:
        """Drop *row*; the last remaining row is never removable."""
        if len(self._rows) <= 1 or row not in self._rows:
            return
        self._rows.remove(row)
        self.rows_box.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._sync_remove_buttons()
        self._fit_rows()
        self._schedule_plan()

    def _fit_rows(self, reveal: ShotRow | None = None) -> None:
        """Grow or shrink the window with the row count — no scrolling to do it.

        Adding a row must be visible immediately, so the list is sized to its
        content and the dialog is re-fitted each time. The one thing the window
        may not do is run off the screen: past the available height the list
        starts scrolling instead of growing, which keeps ``Create`` reachable on
        a laptop while a forty-shot batch still works.
        """
        content = ROW_HEIGHT * len(self._rows) + 8
        # A resizable scroll area squeezes its child to the viewport, so the
        # child has to declare how tall it really is — that minimum is what
        # turns "40 rows" into a scrollbar instead of overlapping rows.
        self.holder.setMinimumHeight(content)
        self.scroll.setFixedHeight(min(content, self._max_list_height()))
        self.adjustSize()
        if reveal is not None:
            self.scroll.ensureWidgetVisible(reveal)

    def _max_list_height(self) -> int:
        """Tallest the list may get before it scrolls: the screen, minus chrome.

        The chrome (intro, captions, button row, summary, margins) is measured
        from the live geometry rather than trusted to the constant: whatever the
        platform and font add, the dialog keeps the same margin to the screen
        edge. ``CHROME_HEIGHT`` is only the estimate used before the first
        layout pass.
        """
        screen = self.screen()
        available = screen.availableGeometry().height() if screen is not None else 900
        chrome = self.height() - self.scroll.height() if self.scroll.height() \
            else CHROME_HEIGHT
        # Never clamp below a few rows: a tiny screen should still show a batch.
        return max(ROW_HEIGHT * 5 + 8, available - chrome)

    def _sync_remove_buttons(self) -> None:
        removable = len(self._rows) > 1
        for row in self._rows:
            row.remove_btn.setEnabled(removable)

    def _on_submitted(self) -> None:
        """Enter in a shot field grows a new row underneath (Excel behaviour)."""
        self.add_row()

    # -- Planning ----------------------------------------------------------

    def entries(self) -> list[tuple[str, str]]:
        """The batch as ``(sequence, shot)`` pairs, one name per shot.

        A row whose shot field holds ``shot010, shot011`` contributes two pairs;
        a completely empty row contributes nothing.
        """
        out: list[tuple[str, str]] = []
        for row in self._rows:
            sequence, shot = row.entry()
            names = split_field(shot)
            # A row only counts once it names a shot: a sequence on its own is
            # not something to create, so half-filled rows stay out of the batch
            # and are reported as "no shot yet" rather than as errors.
            for name in names:
                out.append((sequence, name))
        return out

    def _schedule_plan(self) -> None:
        self._timer.start()

    def refresh_plan(self) -> tuple[ShotPlanRow, ...]:
        """Re-classify the batch and repaint badges, totals and Create.

        Returns:
            The plan, so tests (and callers) can assert on it without waiting
            for the timer.
        """
        entries = self.entries()
        self._timer.stop()          # the pending timer would repeat this work
        self.plan_rows = tuple(
            self._data_source.plan_shots(self.project, entries)) if entries else ()
        self._render_badges()
        self._render_totals(entries)
        return self.plan_rows

    def _render_badges(self) -> None:
        """Give each row the verdict for the names it produced (in order)."""
        index = 0
        for row in self._rows:
            sequence, shot = row.entry()
            names = split_field(shot)
            chunk = self.plan_rows[index:index + len(names)]
            index += len(names)
            row.set_name_hint(self._shots_in(sequence))
            if not chunk:
                row.set_status("", "no shot yet" if sequence or names else "")
                continue
            row.set_status(*self._badge(chunk))

    def _badge(self, chunk: Sequence[ShotPlanRow]) -> tuple[str, str]:
        if not chunk:
            return ("", "")
        blocking = [row for row in chunk if row.blocks]
        if blocking:
            return (SHOT_STATUS_INVALID, blocking[0].message)
        counts = shot_counts(chunk)
        if counts[SHOT_STATUS_NEW] and counts[SHOT_STATUS_EXISTS]:
            return (SHOT_STATUS_NEW,
                    f"{counts[SHOT_STATUS_NEW]} new · {counts[SHOT_STATUS_EXISTS]} there")
        if counts[SHOT_STATUS_NEW]:
            return (SHOT_STATUS_NEW, "" if len(chunk) == 1
                    else f"{counts[SHOT_STATUS_NEW]} new")
        if counts[SHOT_STATUS_EXISTS]:
            return (SHOT_STATUS_EXISTS, "" if len(chunk) == 1
                    else f"{counts[SHOT_STATUS_EXISTS]} there")
        return (SHOT_STATUS_DUPLICATE, "duplicate")

    def _render_totals(self, entries: Sequence[tuple[str, str]]) -> None:
        if not entries:
            self.plan_label.setText(
                "Type a sequence and a shot — nothing is created until you press "
                "Create.")
            self.plan_label.setStyleSheet(MUTED)
            self.create_btn.setEnabled(False)
            return
        counts = shot_counts(self.plan_rows)
        new_sequences = len({row.sequence for row in self.plan_rows if row.new_sequence})
        parts = [f"Will create {_plural(counts[SHOT_STATUS_NEW], 'folder')}"]
        already = counts[SHOT_STATUS_EXISTS] + counts[SHOT_STATUS_DUPLICATE]
        if already:
            parts.append(f"{already} already there")
        if new_sequences:
            parts.append(_plural(new_sequences, "new sequence"))
        if counts[SHOT_STATUS_INVALID]:
            parts.append(f"{counts[SHOT_STATUS_INVALID]} not usable")
        self.plan_label.setText(" · ".join(parts))
        self.plan_label.setStyleSheet(MUTED)
        self.create_btn.setEnabled(counts[SHOT_STATUS_INVALID] == 0)

    # -- Creating ----------------------------------------------------------

    def _on_create(self) -> None:
        """Run the batch; only a clean result closes the dialog."""
        try:
            summary = self._data_source.add_shots(
                self.project, self.entries(), dry_run=False)
        except Exception as exc:                # noqa: BLE001 — surface, don't crash
            summary = ApplySummary(
                errors=((self.project, str(exc)),),
                diagnostics=(DiagnosticRow("error", "E_SHOTS",
                                           f"Cannot add shots: {exc}",
                                           target=self.project),))
        self.summary = summary
        if not summary.ok:
            self._render_issues([row for row in summary.diagnostics
                                 if row.level == "error"])
            return
        created = [row for row in self.plan_rows if row.status == SHOT_STATUS_NEW]
        if created:
            self.last_created = (created[-1].sequence, created[-1].shot)
        self.accept()

    def _render_issues(self, rows: Sequence[DiagnosticRow]) -> None:
        if not rows:
            self.issues_label.setText("")
            self.issues_label.setVisible(False)
            return
        self.issues_label.setText("\n".join(f"• {row.message}" for row in rows))
        self.issues_label.setVisible(True)
