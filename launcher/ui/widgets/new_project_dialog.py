"""New Project — one screen, and it says what will happen before it happens.

The dialog exists to answer three questions at once, because "create a project"
in this pipeline means four coupled writes (a database row, a work skeleton, a
publish root, and the show's baseline environment):

1. *what do I call it, and where does it live* — name plus the two roots;
2. *what will be created* — the folder count and the override count, quoted live
   from the same ``create_project(dry_run=True)`` call the real run uses, so the
   preview cannot drift from the outcome;
3. *what is wrong right now* — blocking errors (bad name, relative path, an
   existing project at a different root) are listed and ``Create`` stays
   disabled instead of failing after the fact.

The plan is a **dry run of the real call**, not a parallel implementation: the
approach is the same one that made the scaffold repair trustworthy, and it is
why the numbers here survive a change in the backend without editing this file.

Data comes exclusively through ``SettingsDataSource`` — the dialog never touches
the database, YAML or the disk itself.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from launcher.ui.viewmodels import (
    ApplySummary,
    DiagnosticRow,
    SettingsDataSource,
)

MUTED = "color: #8b94a3;"
ERROR = "color: #e5484d;"
WARNING = "color: #f59e0b;"
OK = "color: #30a46c;"

#: The dialog never gets narrower than this, whatever the text says.
MIN_WIDTH = 520

#: Room left to the screen edge when the dialog has to grow to fit its text.
SCREEN_MARGIN = 80


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


class NewProjectDialog(QDialog):
    """Create a project, with a live preview of the four writes it implies.

    Signals:
        None — the caller reads :attr:`summary` after ``exec()`` returns
        ``Accepted``; a creation is a single deliberate click, not a stream.
    """

    def __init__(self, data_source: SettingsDataSource,
                 root: str = "", publish_root: str = "",
                 parent: QWidget | None = None) -> None:
        """Build the dialog.

        Args:
            data_source: Backend implementing ``SettingsDataSource``.
            root: Default projects root (normally the one the existing shows
                use — retyping a volume path is where typos come from).
            publish_root: Default publish root.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._data_source = data_source
        self.summary: ApplySummary | None = None
        self.project_name = ""

        self.setWindowTitle("New Project")
        self.setModal(True)
        self.setMinimumWidth(MIN_WIDTH)
        self._build_ui(root, publish_root)
        # Open at the intended width; from here on the window may only grow in
        # height, so a wider window never creeps back when the text shortens.
        self.resize(MIN_WIDTH, self.sizeHint().height())
        self._refresh_plan()

    # -- Construction ------------------------------------------------------

    def _build_ui(self, root: str, publish_root: str) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 12)
        outer.setSpacing(10)

        intro = QLabel(
            "A project owns one work tree, one publish tree and one baseline "
            "environment. Nothing outside those is touched."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(MUTED)
        outer.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. NewShow — letters, digits, underscores")
        self.name_edit.textChanged.connect(self._refresh_plan)

        self.root_edit = QLineEdit(root)
        self.root_edit.setPlaceholderText("/path/to/y_pipeline_projects")
        self.root_edit.textChanged.connect(self._refresh_plan)
        self.publish_edit = QLineEdit(publish_root)
        self.publish_edit.setPlaceholderText("/path/to/y_pipeline_publish")
        self.publish_edit.textChanged.connect(self._refresh_plan)

        form.addRow("Name", self.name_edit)
        form.addRow("Work root", self._with_browse(self.root_edit, "Pick the work root"))
        form.addRow("Publish root",
                    self._with_browse(self.publish_edit, "Pick the publish root"))
        outer.addLayout(form)

        self.plan_label = QLabel("")
        self.plan_label.setWordWrap(True)
        outer.addWidget(self.plan_label)

        self.issues_label = QLabel("")
        self.issues_label.setWordWrap(True)
        self.issues_label.setTextFormat(Qt.TextFormat.PlainText)
        outer.addWidget(self.issues_label)

        self.buttons = QDialogButtonBox()
        self.create_btn = self.buttons.addButton("Create",
                                                 QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_btn = self.buttons.addButton("Cancel",
                                                 QDialogButtonBox.ButtonRole.RejectRole)
        self.create_btn.clicked.connect(self._on_create)
        self.cancel_btn.clicked.connect(self.reject)
        outer.addWidget(self.buttons)

    def _with_browse(self, edit: QLineEdit, title: str) -> QWidget:
        """Put a Browse button next to a path field."""
        row = QWidget()
        # A path field keeps its height: whatever the text below grows into, it
        # is not paid for out of these two rows.
        row.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        box = QHBoxLayout(row)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        box.addWidget(edit, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: self._browse(edit, title))
        box.addWidget(browse)
        return row

    def _browse(self, edit: QLineEdit, title: str) -> None:
        """Pick a directory into *edit* (no-op when the user cancels)."""
        chosen = QFileDialog.getExistingDirectory(self, title, edit.text() or "/")
        if chosen:
            edit.setText(chosen)

    # -- Planning ----------------------------------------------------------

    def name(self) -> str:
        """The trimmed project name."""
        return self.name_edit.text().strip()

    def planned(self) -> ApplySummary:
        """Dry-run the real creation call.

        A backend that raises is a blocking condition, not a crash: the dialog
        reports it and keeps Create disabled.
        """
        try:
            return self._data_source.create_project(
                self.name(), self.root_edit.text().strip(),
                self.publish_edit.text().strip(), {}, True)
        except Exception as exc:                       # noqa: BLE001 — surface, don't crash
            return ApplySummary(
                errors=((self.name(), str(exc)),),
                diagnostics=(DiagnosticRow("error", "E_PLAN",
                                           f"Cannot plan the project: {exc}",
                                           target=self.name()),),
            )

    def blocking(self, summary: ApplySummary) -> list[DiagnosticRow]:
        """Errors the dry run itself reported, in a stable order."""
        errors = [d for d in summary.diagnostics if d.level == "error"]
        for path, reason in summary.errors:
            if not any(d.target == path for d in errors):
                errors.append(DiagnosticRow("error", "E_PLAN", reason, target=path))
        return errors

    def review(self) -> tuple[ApplySummary, list[DiagnosticRow], list[DiagnosticRow]]:
        """Validate, then dry-run — ``(plan, errors, warnings)``.

        Both calls are needed and they answer different questions: the
        validator is the contract for a *name and roots*, the dry run is the
        contract for *what will be written*. A backend that validates inside
        ``create_project`` and one that exposes ``validate_project`` therefore
        behave the same here.
        """
        name = self.name()
        root = self.root_edit.text().strip()
        publish_root = self.publish_edit.text().strip()
        errors: list[DiagnosticRow] = []
        warnings: list[DiagnosticRow] = []
        try:
            for diagnostic in self._data_source.validate_project(name, root, publish_root):
                if diagnostic.level == "error":
                    errors.append(diagnostic)
                elif diagnostic.level == "warn":
                    warnings.append(diagnostic)
        except Exception as exc:                       # noqa: BLE001 — surface, don't crash
            errors.append(DiagnosticRow("error", "E_PLAN",
                                        f"Cannot validate the project: {exc}", target=name))
        plan = self.planned()
        for diagnostic in self.blocking(plan):
            if not any(d.code == diagnostic.code and d.target == diagnostic.target
                       for d in errors):
                errors.append(diagnostic)
        warnings += [d for d in plan.diagnostics
                     if d.level == "warn" and d not in warnings]
        return plan, errors, warnings

    def _render_issues(self, errors: list[DiagnosticRow],
                       warnings: list[DiagnosticRow]) -> None:
        """List blocking errors first, then warnings, in one label."""
        lines = [(d.message, ERROR) for d in errors] + [(d.message, WARNING) for d in warnings]
        if not lines:
            self.issues_label.setText("")
            self.issues_label.setStyleSheet(MUTED)
            return
        self.issues_label.setText("\n".join(f"• {message}" for message, _ in lines))
        self.issues_label.setStyleSheet(lines[0][1])

    def _refresh_plan(self) -> None:
        """Re-plan on every keystroke and restate the outcome in two numbers."""
        plan, errors, warnings = self.review()

        if not self.name():
            self.plan_label.setText("Type a name to see what will be created.")
            self.plan_label.setStyleSheet(MUTED)
        else:
            text = (f"Will create {_plural(len(plan.created), 'folder')} · "
                    f"will write {_plural(plan.env_written, 'override')}")
            if plan.skipped:
                text += f" · {len(plan.skipped)} already exist"
            self.plan_label.setText(text)
            self.plan_label.setStyleSheet(ERROR if errors else OK)

        self._render_issues(errors, warnings)
        self.create_btn.setEnabled(bool(self.name()) and not errors)
        self._fit_to_content()

    def _fit_to_content(self) -> None:
        """Follow the text with the window instead of squeezing the fields.

        Two labels appear and disappear while typing — the plan line, and the
        warnings under it. A dialog keeps the height it was opened with, so that
        extra text used to be paid for by the rows above it: type a name, an
        orange warning appears, and the two path fields lose a few pixels each
        time. Re-fit instead. The width stays where the user put it, the height
        follows ``heightForWidth`` (so word-wrapped text is measured, not
        guessed), and the screen edge is the only ceiling.
        """
        layout = self.layout()
        if layout is None:
            return
        layout.activate()
        width = max(self.width(), MIN_WIDTH)
        wanted = (layout.heightForWidth(width) if layout.hasHeightForWidth()
                  else self.sizeHint().height())
        height = max(wanted, self.minimumSizeHint().height())
        screen = self.screen()
        if screen is not None:
            height = min(height, screen.availableGeometry().height() - SCREEN_MARGIN)
        self.resize(width, height)

    # -- Creating ----------------------------------------------------------

    def _on_create(self) -> None:
        """Run the real call; only a clean result closes the dialog."""
        summary = self._data_source.create_project(
            self.name(), self.root_edit.text().strip(),
            self.publish_edit.text().strip(), {}, False)
        self.summary = summary
        if not summary.ok:
            failures = self.blocking(summary)
            if not failures:                    # ok is False via diagnostics alone
                failures = [d for d in summary.diagnostics if d.level == "error"]
            self._render_issues(failures, [])
            return
        self.project_name = self.name()
        self.accept()
