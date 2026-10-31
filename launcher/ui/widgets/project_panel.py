"""Project column — the TD's control surface for one show's environment.

The right-most column of the settings window (2026-10-26 r7 layout). It replaces
the old seven-column Projects table: the context bar already picks the project,
so listing all of them twice was a second source of truth, and seven columns
never fit a settings column.

The content is a **verdict plus the evidence for it**, in five stacked cards:

    HEALTH       one sentence: ready, or what is broken (and the repair button)
    PATHS        root / publish / cache / asset / render, with ✓ ✗ and the source
    CONTENTS     how many sequences, shots and show-scoped vars, plus vocabulary
    ENVIRONMENT  which layers this show owns, and any guarded key it forks
    DANGER       collapsed: renaming/deleting a project is a four-layer migration

Reads only ``SettingsDataSource`` (plan G1/G2): no YAML, no ORM, no disk.
Path existence comes from ``scaffold_plan()``'s ``exists`` flags — the data
source does the ``isdir``, this widget only renders the answer.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QFrame,
)

from launcher.ui.viewmodels import (
    SCOPE_ORDER,
    ApplySummary,
    DiagnosticRow,
    ProjectRow,
    ScaffoldPlanRow,
    SettingsContext,
    SettingsDataSource,
    GUARDED_SCOPE_KEYS,
)
from launcher.ui.widgets.new_project_dialog import NewProjectDialog
from launcher.ui.widgets.style import COLUMN_TITLE_QSS

MUTED = "color: #8b94a3; font-size: 11px;"
# Body text keeps the palette's own colour: hard-coding a dark grey makes the
# card unreadable under a dark theme (and this app runs on system dark mode).
BODY = ""
VALUE_QSS = ("font-family: monospace; font-size: 11px;"
             " background: transparent; border: none;")
CARD_TITLE = "font-weight: bold; font-size: 11px; color: #8b94a3;"

COLOR_OK = "#16a34a"
COLOR_WARN = "#f59e0b"
COLOR_ERROR = "#dc2626"
COLOR_MUTED = "#8b94a3"

MARK_EXISTS = "✓"
MARK_MISSING = "✗"
MARK_UNKNOWN = "—"

#: Guarded keys explain *why* the warning exists rather than only what happened.
GUARDED_HINT = ("Colour management, USD and fps have to stay comparable across "
                "departments — an override here forks the look.")


def _clear_layout(layout) -> None:
    """Remove and destroy every widget a layout holds."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


def _plural(count: int, noun: str) -> str:
    """``1 warning`` / ``2 warnings`` — no ``(s)`` placeholders."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _dev_label(path: str) -> str:
    """``/dev/cache/CyberPunk`` -> ``Cache`` — the $DEV subdir that owns the path."""
    parts = [part for part in path.rstrip("/").split("/") if part]
    if len(parts) < 2:
        return "Path"
    return parts[-2].replace("_", " ").capitalize()


class ProjectPanel(QWidget):
    """Health, paths, contents and env layers of the context's project.

    Signals:
        project_created: Emitted with the new project's name after the New
            Project dialog succeeded, so the window can move its context onto
            the show that was just created instead of leaving it blank.
    """

    project_created = Signal(str)

    def __init__(self, data_source: SettingsDataSource,
                 parent: QWidget | None = None) -> None:
        """Build the panel.

        Args:
            data_source: Backend implementing ``SettingsDataSource``.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._data_source = data_source
        self.project = ""
        self._row: ProjectRow | None = None
        self._plan: list[ScaffoldPlanRow] = []
        self._issues: list[DiagnosticRow] = []
        self._env = []
        self._build_ui()
        self.refresh()

    # -- Construction ------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self.title_label = QLabel("Project")
        self.title_label.setStyleSheet(COLUMN_TITLE_QSS)
        self.hint_label = QLabel("What this show's environment is made of.")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet(MUTED)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        title_row.addWidget(self.title_label)
        title_row.addStretch(1)
        self.new_project_btn = QPushButton("+")
        self.new_project_btn.setFixedWidth(26)
        self.new_project_btn.setToolTip("New project…")
        self.new_project_btn.clicked.connect(self._on_new_project)
        title_row.addWidget(self.new_project_btn)

        outer.addLayout(title_row)
        outer.addWidget(self.hint_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        self.body_box = QVBoxLayout(body)
        self.body_box.setContentsMargins(0, 0, 0, 0)
        self.body_box.setSpacing(14)
        self._build_health_card()
        self._build_paths_card()
        self._build_contents_card()
        self._build_layers_card()
        self._build_danger_card()
        self.body_box.addStretch(1)
        self.scroll.setWidget(body)
        outer.addWidget(self.scroll, 1)

    def _card(self, heading: str) -> tuple[QWidget, QVBoxLayout]:
        """Add one titled card to the scroll body and return it."""
        card = QWidget()
        box = QVBoxLayout(card)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        label = QLabel(heading)
        label.setStyleSheet(CARD_TITLE)
        box.addWidget(label)
        self.body_box.addWidget(card)
        return (card, box)

    def _build_health_card(self) -> None:
        _, box = self._card("HEALTH")
        self.verdict_label = QLabel("—")
        self.verdict_label.setWordWrap(True)
        self.verdict_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.health_detail = QLabel("")
        self.health_detail.setWordWrap(True)
        self.health_detail.setStyleSheet(MUTED)
        # The column answers for *this show* only; the checks themselves are
        # the middle column's job, so they are reported here but never allowed
        # to colour the verdict (otherwise every show looks broken).
        self.checks_label = QLabel("")
        self.checks_label.setWordWrap(True)
        self.checks_label.setStyleSheet(MUTED)

        self.rerun_btn = QPushButton("Re-run")
        self.rerun_btn.setToolTip("Re-read the project row, the disk and the checks")
        self.rerun_btn.clicked.connect(self.refresh)
        self.repair_btn = QPushButton("Repair scaffold…")
        self.repair_btn.setToolTip("Create the missing skeleton folders")
        self.repair_btn.clicked.connect(self._on_repair)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.addWidget(self.rerun_btn)
        buttons.addWidget(self.repair_btn)
        buttons.addStretch(1)

        self.repair_status = QLabel("")
        self.repair_status.setWordWrap(True)
        self.repair_status.setStyleSheet(MUTED)

        box.addWidget(self.verdict_label)
        box.addWidget(self.health_detail)
        box.addWidget(self.checks_label)
        box.addLayout(buttons)
        box.addWidget(self.repair_status)

    def _build_paths_card(self) -> None:
        _, box = self._card("PATHS")
        self.paths_grid = QGridLayout()
        self.paths_grid.setContentsMargins(0, 0, 0, 0)
        self.paths_grid.setHorizontalSpacing(6)
        self.paths_grid.setVerticalSpacing(2)
        self.paths_grid.setColumnStretch(2, 1)
        self.source_label = QLabel("")
        self.source_label.setWordWrap(True)
        self.source_label.setStyleSheet(MUTED)
        box.addLayout(self.paths_grid)
        box.addWidget(self.source_label)

    def _build_contents_card(self) -> None:
        _, box = self._card("CONTENTS")
        self.counts_label = QLabel("")
        self.counts_label.setWordWrap(True)
        self.counts_label.setStyleSheet(BODY)
        self.vocab_label = QLabel("")
        self.vocab_label.setWordWrap(True)
        self.vocab_label.setStyleSheet(MUTED)

        self.open_root_btn = QPushButton("Open root")
        self.open_root_btn.clicked.connect(self._on_open_root)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.addWidget(self.open_root_btn)
        buttons.addStretch(1)

        box.addWidget(self.counts_label)
        box.addWidget(self.vocab_label)
        box.addLayout(buttons)

    def _build_layers_card(self) -> None:
        _, box = self._card("ENVIRONMENT")
        self.layers_label = QLabel("")
        self.layers_label.setWordWrap(True)
        self.layers_label.setStyleSheet(BODY)
        self.guarded_label = QLabel("")
        self.guarded_label.setWordWrap(True)
        self.guarded_label.setStyleSheet(MUTED)
        box.addWidget(self.layers_label)
        box.addWidget(self.guarded_label)

    def _build_danger_card(self) -> None:
        self.danger_toggle = QToolButton()
        self.danger_toggle.setText("Danger zone")
        self.danger_toggle.setCheckable(True)
        self.danger_toggle.setChecked(False)
        self.danger_toggle.setArrowType(Qt.ArrowType.RightArrow)
        # Arrow buttons are ToolButtonIconOnly by default — without this the
        # label disappears and all that is left is a stray ">".
        self.danger_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.danger_toggle.setAutoRaise(True)
        self.danger_toggle.setStyleSheet(CARD_TITLE)
        self.danger_toggle.toggled.connect(self._on_danger_toggled)

        self.danger_body = QWidget()
        body = QVBoxLayout(self.danger_body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(4)
        self.deactivate_btn = QPushButton("Deactivate project…")
        self.deactivate_btn.setEnabled(False)
        self.deactivate_btn.setToolTip("Not wired yet")
        self.delete_btn = QPushButton("Delete project…")
        self.delete_btn.setEnabled(False)
        self.delete_btn.setToolTip("Not wired yet")
        note = QLabel("Not wired yet: renaming or deleting a project touches four "
                      "layers — the disk tree, the database row, the env scope key "
                      "and the publish root. It needs a migration wizard, not a "
                      "button.")
        note.setWordWrap(True)
        note.setStyleSheet(MUTED)
        body.addWidget(self.deactivate_btn)
        body.addWidget(self.delete_btn)
        body.addWidget(note)
        self.danger_body.setVisible(False)

        card = QWidget()
        box = QVBoxLayout(card)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        box.addWidget(self.danger_toggle)
        box.addWidget(self.danger_body)
        self.body_box.addWidget(card)

    # -- Creation ----------------------------------------------------------

    def _default_roots(self) -> tuple[str, str]:
        """Roots to pre-fill: this show's own, else any existing show's.

        Reusing the volume the pipeline already lives on is the whole point —
        a retyped path is where most typos in a project row come from.
        """
        try:
            rows = list(self._data_source.projects())
        except Exception:
            rows = []
        for row in rows:
            if self._row is not None and row.name == self._row.name:
                return row.root, row.publish_root
        if rows:
            return rows[0].root, rows[0].publish_root
        return "", ""

    def _on_new_project(self) -> None:
        """Open the dialog; on success announce the new show and show it."""
        root, publish_root = self._default_roots()
        dialog = NewProjectDialog(self._data_source, root=root,
                                  publish_root=publish_root, parent=self)
        if dialog.exec() != NewProjectDialog.DialogCode.Accepted:
            return
        self.project_created.emit(dialog.project_name)
        self.set_project(dialog.project_name)
        summary = dialog.summary
        self.repair_status.setText(
            f"Created {dialog.project_name} · "
            f"{len(summary.created) if summary else 0} folder(s), "
            f"{summary.env_written if summary else 0} override(s)")

    def _on_danger_toggled(self, checked: bool) -> None:
        self.danger_body.setVisible(checked)
        self.danger_toggle.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    # -- Data --------------------------------------------------------------

    def set_context(self, context: SettingsContext) -> None:
        """Point the panel at the context's project (the notifier path)."""
        self.set_project(getattr(context, "project", "") or "")

    def set_project(self, name: str) -> None:
        """Point the panel at one project and re-render."""
        self.project = name or ""
        self.refresh()

    def _safe_plan(self, name: str) -> list[ScaffoldPlanRow]:
        try:
            return list(self._data_source.scaffold_plan(name))
        except Exception:
            return []

    def _safe_diagnostics(self) -> list[DiagnosticRow]:
        try:
            return list(self._data_source.diagnostics())
        except Exception:
            return []

    def _safe_env(self) -> list:
        try:
            return list(self._data_source.env_rows())
        except Exception:
            return []

    def refresh(self) -> None:
        """Reload the project row and everything derived from it."""
        try:
            rows = {row.name: row for row in self._data_source.projects()}
        except Exception as exc:                     # database down, YAML unreadable
            self._render_blocked(f"Could not load projects: {exc}", error=True)
            return
        row = rows.get(self.project)
        if row is None:
            self._render_blocked("No project selected" if not self.project
                                 else f"Unknown project: {self.project}")
            return

        self._row = row
        self._plan = self._safe_plan(row.name)
        self._issues = self._safe_diagnostics()
        self._env = self._safe_env()
        self._render_health(row)
        self._render_paths(row)
        self._render_contents(row)
        self._render_layers()

    def _render_blocked(self, message: str, error: bool = False) -> None:
        """Empty/error state: one honest sentence, no leftover numbers."""
        self._row = None
        self._plan = []
        self._issues = []
        self._env = []
        self.verdict_label.setText(message)
        self.verdict_label.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: "
            f"{COLOR_ERROR if error else COLOR_MUTED};")
        self.health_detail.setText("")
        self.checks_label.setText("")
        self.repair_status.setText("")
        self.repair_btn.setEnabled(False)
        _clear_layout(self.paths_grid)
        self.source_label.setText("")
        self.counts_label.setText("")
        self.vocab_label.setText("")
        self.open_root_btn.setEnabled(False)
        self.layers_label.setText("")
        self.guarded_label.setText("")

    # -- Health ------------------------------------------------------------

    def missing_paths(self) -> list[ScaffoldPlanRow]:
        """Required-or-derived skeleton folders that do not exist (``[]`` if n/a)."""
        if self._row is None or self._row.scaffold_state == "n/a":
            return []
        return [row for row in self._plan
                if row.group in ("required", "dev_root") and not row.exists]

    def _render_health(self, row: ProjectRow) -> None:
        missing = self.missing_paths()
        errors = [d for d in self._issues if d.level == "error"]
        warnings = [d for d in self._issues if d.level == "warn"]

        # ``ProjectRow.scaffold_state`` is a summary the backend cached when it
        # listed the projects; the plan is re-read on every refresh. When both
        # exist the plan wins, otherwise a repair would keep showing the stale
        # verdict until the window is reopened.
        state = row.scaffold_state
        if state != "n/a" and any(r.group == "required" for r in self._plan):
            state = "missing" if missing else "complete"

        # The verdict judges the **project**: dead folders and an incomplete
        # skeleton. Global checks are reported on their own line — letting them
        # colour this verdict would make every show look broken and would
        # duplicate the preflight column.
        parts = []
        if missing:
            parts.append(f"{len(missing)} folder(s) missing")
        elif state == "missing":
            parts.append("scaffold incomplete")

        if not parts:
            verdict, color = "Ready", COLOR_OK
        else:
            verdict, color = " · ".join(parts), COLOR_ERROR
        self.verdict_label.setText(verdict)
        self.verdict_label.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {color};")

        marks = []
        for label, plan_row, _derived in self._path_specs(row):
            if plan_row is None:
                marks.append(f"{label.lower()} {MARK_UNKNOWN}")
                continue
            marks.append(f"{label.lower()} "
                         f"{MARK_EXISTS if plan_row.exists else MARK_MISSING}")
        skeleton_total = len([r for r in self._plan
                              if r.group in ("required", "dev_root")])
        if state == "n/a":
            skeleton = "skeleton not checked"
        else:
            skeleton = (f"folders {skeleton_total - len(missing)}/{skeleton_total}"
                        if skeleton_total else "no skeleton plan")
        self.health_detail.setText(" · ".join(marks + [skeleton]))
        self.repair_btn.setEnabled(bool(missing))

        if errors:
            self.checks_label.setText(
                f"preflight: {_plural(len(errors), 'error')}"
                + (f" · {_plural(len(warnings), 'warning')}" if warnings else ""))
            self.checks_label.setStyleSheet(f"color: {COLOR_ERROR}; font-size: 11px;")
        elif warnings:
            self.checks_label.setText(f"preflight: {_plural(len(warnings), 'warning')}")
            self.checks_label.setStyleSheet(f"color: {COLOR_WARN}; font-size: 11px;")
        else:
            self.checks_label.setText("preflight: clean")
            self.checks_label.setStyleSheet(MUTED)

    # -- Paths -------------------------------------------------------------

    def _path_specs(self, row: ProjectRow
                    ) -> list[tuple[str, ScaffoldPlanRow | None, bool]]:
        """``(label, plan row, derived)`` for root, publish and the $DEV folders."""
        specs: list[tuple[str, ScaffoldPlanRow | None, bool]] = []
        required = [r for r in self._plan if r.group == "required"]
        specs.append(("Root", required[0] if required else None, False))
        specs.append(("Publish", required[1] if len(required) > 1 else None, False))
        for plan_row in self._plan:
            if plan_row.group == "dev_root":
                specs.append((_dev_label(plan_row.path), plan_row, True))
        return specs

    def _render_paths(self, row: ProjectRow) -> None:
        _clear_layout(self.paths_grid)
        for index, (label, plan_row, derived) in enumerate(self._path_specs(row)):
            if plan_row is None or not plan_row.path:
                mark, path, tip = MARK_UNKNOWN, "", "Not planned"
            else:
                mark = MARK_EXISTS if plan_row.exists else MARK_MISSING
                path = plan_row.path
                tip = path + ("  (derived — not stored in config)" if derived else "")
            if self._row is not None and self._row.scaffold_state == "n/a":
                mark = MARK_UNKNOWN

            mark_label = QLabel(mark)
            mark_label.setStyleSheet(
                f"color: {COLOR_OK if mark == MARK_EXISTS else COLOR_MUTED if mark == MARK_UNKNOWN else COLOR_ERROR};")
            mark_label.setFixedWidth(12)
            mark_label.setToolTip("exists" if mark == MARK_EXISTS
                                  else "missing" if mark == MARK_MISSING
                                  else "derived / not checked")

            name_label = QLabel(label)
            name_label.setStyleSheet(MUTED)
            name_label.setFixedWidth(52)
            if derived:
                name_label.setToolTip("Derived from $DEV — not stored in config")

            field = QLineEdit(path)
            field.setReadOnly(True)
            field.setFrame(False)
            field.setStyleSheet(VALUE_QSS)
            field.setToolTip(tip)
            field.setMinimumWidth(60)
            field.setCursorPosition(0)

            self.paths_grid.addWidget(mark_label, index, 0)
            self.paths_grid.addWidget(name_label, index, 1)
            self.paths_grid.addWidget(field, index, 2)

        self.source_label.setText(
            f"source: {'database' if row.source == 'db' else 'config/projects.yaml'}"
            + ("" if row.enabled else " · disabled — hidden from the launcher tree")
        )

    # -- Contents ----------------------------------------------------------

    def _render_contents(self, row: ProjectRow) -> None:
        self.counts_label.setText(
            f"{row.seqs} sequence(s) · {row.shots} shot(s) · "
            f"{row.env_show_count} show-scoped var(s)"
        )
        try:
            departments = list(self._data_source.departments())
            roles = list(self._data_source.dcc_roles())
        except Exception:
            departments, roles = [], []
        vocab = []
        if departments:
            vocab.append("departments: " + ", ".join(departments))
        if roles:
            vocab.append("dcc: " + ", ".join(roles))
        self.vocab_label.setText(" · ".join(vocab))
        self.open_root_btn.setEnabled(self._root_is_reachable(row))

    def _root_is_reachable(self, row: ProjectRow) -> bool:
        """Only offer Open when the folder is known to exist (``n/a`` is unknown)."""
        required = [r for r in self._plan if r.group == "required"]
        if not required:
            return False
        if row.scaffold_state == "n/a":
            return True                              # unchecked, not known-dead
        return bool(required[0].exists and required[0].path)

    def _root_path(self, row: ProjectRow) -> str:
        """The folder a TD would open: ``<root>/<name>`` from the plan."""
        required = [r for r in self._plan if r.group == "required"]
        if required and required[0].path:
            return required[0].path
        return f"{row.root.rstrip('/')}/{row.name}" if row.root else ""

    def _on_open_root(self) -> None:
        if self._row is None:
            return
        if not self._root_is_reachable(self._row):
            return                                   # do not open a dead path
        path = self._root_path(self._row)
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # -- Environment layers ------------------------------------------------

    def _project_env(self) -> list:
        """Layers that apply to *this* show.

        Global / derived / dcc / department rows apply everywhere; show-scope
        rows belong to exactly one project, so another show's overrides must not
        be counted or flagged here (the old table showed all of them at once).
        """
        return [
            row for row in self._env
            if not (row.scope == "show" and row.scope_key
                    and row.scope_key != self.project)
        ]

    def _render_layers(self) -> None:
        rows = self._project_env()
        counts = {scope: 0 for scope in SCOPE_ORDER}
        for row in rows:
            if getattr(row, "enabled", True) and row.scope in counts:
                counts[row.scope] += 1
        self.layers_label.setText(
            " · ".join(f"{scope} {count}" for scope, count in counts.items())
            if rows else "no environment layers configured"
        )

        guarded = [
            row for row in rows
            if getattr(row, "enabled", True)
            and row.scope in ("show", "dcc", "department")
            and row.name.upper() in GUARDED_SCOPE_KEYS
        ]
        if not guarded:
            self.guarded_label.setText("")
            self.guarded_label.setStyleSheet(MUTED)
            return
        listed = " · ".join(
            f"{row.name} @ {row.scope}" + (f":{row.scope_key}" if row.scope_key else "")
            for row in guarded
        )
        self.guarded_label.setText(f"⚠ guarded key overridden — {listed}\n{GUARDED_HINT}")
        self.guarded_label.setStyleSheet(f"color: {COLOR_WARN}; font-size: 11px;")

    # -- Actions -----------------------------------------------------------

    def _on_repair(self) -> None:
        """Confirm, then create the missing folders (``repair_now`` does the work)."""
        missing = self.missing_paths()
        if not missing:
            QMessageBox.information(self, "Repair scaffold",
                                    f"{self.project}: nothing to create.")
            return
        preview = "\n".join(row.path for row in missing[:10])
        more = "" if len(missing) <= 10 else f"\n… and {len(missing) - 10} more"
        if QMessageBox.question(
            self, "Repair scaffold",
            f"Create {len(missing)} folder(s) for {self.project}?\n\n{preview}{more}",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.repair_now()

    def repair_now(self) -> ApplySummary:
        """Apply the repair without asking, then re-read (idempotency is visible)."""
        try:
            summary = self._data_source.repair(self.project, dry_run=False)
        except Exception as exc:                     # backend down mid-action
            summary = ApplySummary(errors=((self.project, str(exc)),))
        created, skipped, errors = summary.counts()
        self.repair_status.setText(
            f"{_plural(created, 'created')} · {skipped} already there · "
            f"{_plural(errors, 'error')}"
        )
        self.refresh()
        return summary
