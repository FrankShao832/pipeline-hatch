"""Settings window — a context bar and three always-visible columns, no tabs.

Plan v1.1 §5 U1 (T05) shell; first cut of the pages landed 2026-10-25; the tab
strip was removed on 2026-10-26 (r7) in favour of three always-visible columns.

Design contract (D-B/D-C/D-D, revised 2026-10-26 r7):
  * modeless QDialog, 1400x840 default, 1200x720 minimum
  * a **context bar** on top: Project / Department / DCC pickers plus a
    read-only ``project ▸ seq/shot`` chip. It is a **snapshot** taken when the
    window opens (from the main window when it has a selection, otherwise the
    first usable default). The main window owns the real launch context; this
    copy exists so the window can be opened stand-alone and so editing never
    mutates the launch selection.
  * **three columns, left to right**: resolved environment (read-only answer,
    ~520px, flexible) | preflight (flexible) | project (380px, pinned). No tabs:
    switching hid two thirds of the evidence, and all three are read together.
  * instant-apply semantics: a ``Close`` button, no OK/Cancel transaction

Why this order: the resolved environment is the *answer* and reads first. Both
tables share the surplus because their long columns (values, messages) are the
ones that elide first; the project column is form-shaped, comfortable at 380px,
and sits next to the pointer. The two views that must be compared line by line
are no longer separated by a page switch.

Data comes exclusively through :class:`launcher.ui.viewmodels.SettingsDataSource`.
While the fixture source is wired in, the footer says so — nobody should mistake
demo numbers for their real pipeline.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from launcher.ui.fakes import FakeSettingsDataSource
from launcher.ui.viewmodels import EnvRow, SettingsContext, SettingsDataSource
from launcher.ui.widgets.preflight_page import PreflightPage
from launcher.ui.widgets.project_panel import ProjectPanel
from launcher.ui.widgets.resolved_preview import ResolvedPreview

PREVIEW_WIDTH = 520          # initial width of the resolved-environment column
PREVIEW_MIN_WIDTH = 440
PROJECT_WIDTH = 380
PREFLIGHT_MIN_WIDTH = 420
PANEL_MARGIN = 8
DEFAULT_SIZE = (1400, 840)
MINIMUM_SIZE = (1200, 720)
NO_DEPARTMENT = "— no department —"


class SettingsWindow(QDialog):
    """Three-column settings shell: context bar, resolved env, preflight, project.

    Signals:
        projects_changed: Emitted after any project CRUD operation so the main
            window can refresh its project tree.
    """

    projects_changed = Signal()

    def __init__(self, data_source: SettingsDataSource | None = None,
                 db_session=None, current_user=None,
                 context: SettingsContext | None = None,
                 parent=None) -> None:
        """Build the shell.

        Args:
            data_source: Backend implementing ``SettingsDataSource``. Defaults
                to the rich fixture (UI-first phase).
            db_session: Kept for main-window compatibility until T06 rewires it.
            current_user: Kept for main-window compatibility.
            context: Seed context (normally the main window's current
                selection). ``None`` or an empty context falls back to the
                first usable default.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._data_source: SettingsDataSource = (
            data_source if data_source is not None else FakeSettingsDataSource("rich")
        )
        self.is_fixture = isinstance(self._data_source, FakeSettingsDataSource)
        self._db_session = db_session
        self._current_user = current_user
        self.context: SettingsContext = context or SettingsContext()
        self._seq = self.context.seq
        self._shot = self.context.shot

        self.setWindowTitle("Settings")
        self.setModal(False)
        self.resize(*DEFAULT_SIZE)
        self.setMinimumSize(*MINIMUM_SIZE)
        self._build_ui()
        self._apply_context(self.context)

    # -- Construction ------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        layout.addLayout(self._build_context_bar())

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        # Column 1 (left): the resolved environment — the answer this whole
        # window exists to give, so it is read first.
        self.resolved_preview = ResolvedPreview(self._data_source)
        self.resolved_preview.env_edited.connect(self._on_env_edited)
        self.preview_host = self.resolved_preview

        # Column 2 (middle): preflight owns the flexible slot — four columns of
        # diagnostics need more width than either fixed column.
        self.preflight_page = PreflightPage(self._data_source)

        # Column 3 (right): the project as a card stack (verdict, paths,
        # contents, layers, danger zone) — the TD's working surface.
        self.project_panel = ProjectPanel(self._data_source)
        # A brand-new project becomes the context of the whole window: the
        # point of creating one here is to configure it immediately.
        self.project_panel.project_created.connect(self._on_project_created)
        self.project_panel.shots_added.connect(self._on_shots_added)

        self.preview_panel = _panel(self.preview_host)
        self.preflight_panel = _panel(self.preflight_page)
        self.project_panel_box = _panel(self.project_panel)
        # Both tables want width (their Value / Message columns are the ones
        # that get elided first), so they share the surplus; the project column
        # is a form and gains nothing from growing, so it is pinned.
        self.preview_panel.setMinimumWidth(PREVIEW_MIN_WIDTH)
        self.preflight_panel.setMinimumWidth(PREFLIGHT_MIN_WIDTH)
        self.project_panel_box.setFixedWidth(PROJECT_WIDTH)

        self.splitter.addWidget(self.preview_panel)
        self.splitter.addWidget(self.preflight_panel)
        self.splitter.addWidget(self.project_panel_box)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        middle = DEFAULT_SIZE[0] - PREVIEW_WIDTH - PROJECT_WIDTH
        self.splitter.setSizes([PREVIEW_WIDTH, middle, PROJECT_WIDTH])
        layout.addWidget(self.splitter, 1)

        layout.addLayout(self._build_footer())

    def _build_context_bar(self) -> QHBoxLayout:
        """Project / Department / DCC pickers plus the read-only shot chip."""
        bar = QHBoxLayout()
        bar.setSpacing(6)

        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(170)
        self.project_combo.setToolTip("Project — the show whose environment is shown")
        self.project_combo.currentIndexChanged.connect(self._on_context_edited)

        self.department_combo = QComboBox()
        self.department_combo.setMinimumWidth(130)
        self.department_combo.setToolTip(
            "Department — the data axis. Left unset rather than guessed."
        )
        self.department_combo.currentIndexChanged.connect(self._on_context_edited)

        self.dcc_combo = QComboBox()
        self.dcc_combo.setMinimumWidth(100)
        self.dcc_combo.setToolTip("DCC — the runtime axis")
        self.dcc_combo.currentIndexChanged.connect(self._on_context_edited)

        # seq/shot are read-only: the override chain has no seq/shot layers yet,
        # but a user must be able to see which shot the numbers refer to.
        self.scope_chip = QLabel("—")
        self.scope_chip.setStyleSheet("color: #8b94a3;")
        self.scope_chip.setToolTip(
            "Shot this context came from (inherited, read-only). The resolver "
            "does not honour seq/shot layers yet — it still picks the first "
            "shot on disk for SEQ/SHOT."
        )

        bar.addWidget(QLabel("Project"))
        bar.addWidget(self.project_combo)
        bar.addWidget(QLabel("Department"))
        bar.addWidget(self.department_combo)
        bar.addWidget(QLabel("DCC"))
        bar.addWidget(self.dcc_combo)
        bar.addWidget(self.scope_chip)
        bar.addStretch(1)
        return bar

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.saved_label = QLabel("Saved —")
        self.warnings_label = QLabel("0 issues")
        self.fixture_label = QLabel("fixture data" if self.is_fixture else "")
        self.fixture_label.setStyleSheet("color: #f59e0b;")
        self.fixture_label.setVisible(self.is_fixture)

        self.copy_env_btn = QPushButton("Copy .env")
        self.copy_env_btn.setToolTip("Copy the resolved rows as NAME=value lines")
        self.copy_env_btn.clicked.connect(self._on_copy_env)
        # One click takes back the last edit — the override file keeps its
        # previous bytes as a backup, so no confirmation dialog is needed.
        self.revert_btn = QPushButton("Revert")
        self.revert_btn.clicked.connect(self._on_revert)
        self.open_config_btn = QPushButton("Open config")
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)

        footer.addWidget(self.saved_label)
        footer.addWidget(self.warnings_label)
        footer.addWidget(self.fixture_label)
        footer.addStretch(1)
        footer.addWidget(self.copy_env_btn)
        footer.addWidget(self.revert_btn)
        footer.addWidget(self.open_config_btn)
        footer.addWidget(self.close_btn)

        # The Preflight page owns the numbers: the footer counter and the tab
        # badge both read from it instead of recomputing anything.
        self.preflight_page.diagnostics_changed.connect(self._on_diagnostics)
        self._on_diagnostics(*self.preflight_page.counts())
        self._refresh_revert_state()
        return footer

    # -- Context -----------------------------------------------------------

    def _load_candidates(self) -> tuple[list, list[str], list[str]]:
        """Load project rows / departments / DCC roles, degrading to empty."""
        try:
            projects = list(self._data_source.projects())
        except Exception:
            projects = []
        try:
            departments = list(self._data_source.departments())
        except Exception:
            departments = []
        try:
            roles = list(self._data_source.dcc_roles())
        except Exception:
            roles = []
        return (projects, departments, roles)

    @staticmethod
    def _default_project(projects: list) -> str:
        """First *usable* project: enabled and scaffolded, else the first enabled.

        Blindly taking row 0 lands on disabled or half-created projects on a
        real install, and the window then opens on a wall of W_PATH warnings.
        """
        for row in projects:
            if row.enabled and row.scaffold_state == "complete":
                return row.name
        for row in projects:
            if row.enabled:
                return row.name
        return projects[0].name if projects else ""

    @staticmethod
    def _fill(combo: QComboBox, items: list[tuple[str, str]]) -> None:
        """Replace a combo's items without emitting a change per item."""
        combo.blockSignals(True)
        combo.clear()
        for label, data in items:
            combo.addItem(label, userData=data)
        combo.blockSignals(False)

    def _select(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.blockSignals(True)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _apply_context(self, context: SettingsContext | None) -> None:
        """Fill the bar from a context, falling back to the default rules."""
        projects, departments, roles = self._load_candidates()
        context = context or SettingsContext()

        self._fill(self.project_combo, [(row.name, row.name) for row in projects])
        project = context.project if self.project_combo.findData(context.project) >= 0 \
            else self._default_project(projects)
        self._select(self.project_combo, project)

        self._fill(self.department_combo,
                   [(NO_DEPARTMENT, "")] + [(name, name) for name in departments])
        department = context.department if context.department in departments else ""
        self._select(self.department_combo, department)

        self._fill(self.dcc_combo, [(role, role) for role in roles])
        dcc = context.dcc if context.dcc in roles else (roles[0] if roles else "")
        self._select(self.dcc_combo, dcc)

        self._seq = context.seq
        self._shot = context.shot
        self._push_context()

    def current_context(self) -> SettingsContext:
        """The context the bar currently shows."""
        return SettingsContext(
            project=self.project_combo.currentData() or "",
            seq=self._seq,
            shot=self._shot,
            dcc=self.dcc_combo.currentData() or "",
            department=self.department_combo.currentData() or "",
        )

    def _push_context(self) -> None:
        """Re-render everything that depends on the context."""
        self.context = self.current_context()
        shot = (f"{self.context.seq or '?'}/{self.context.shot or '?'}"
                if (self.context.seq or self.context.shot) else "no shot")
        self.scope_chip.setText(f"▸ {shot}")
        self.resolved_preview.set_context(self.context)
        self.preflight_page.set_context(self.context)
        self.project_panel.set_context(self.context)

    def _on_context_edited(self) -> None:
        """A picker changed: re-render everything that depends on the context."""
        self._push_context()

    # -- Behaviour ---------------------------------------------------------

    def _on_env_edited(self, name: str, value: str) -> None:
        """Write one edited value as a show-scope override, then re-render.

        The window owns the decision about *which* layer an edit lands in: the
        context bar already names exactly one project, so a value typed here
        means "for this show" and nothing else has to be asked.
        """
        diagnostics = self._data_source.save_env_row(EnvRow(
            name=name, value=value, scope="show", scope_key=self.context.project,
        ))
        self._push_context()

        errors = [d for d in diagnostics if d.level == "error"]
        if errors:
            self.saved_label.setText(f"Not saved — {errors[0].message}")
            return
        self.preflight_page.refresh()
        self.set_saved_now(
            f"just now · {len(diagnostics)} warning(s)" if diagnostics else "just now")
        self._refresh_revert_state()

    def _on_project_created(self, name: str) -> None:
        """Move the context (and therefore all three columns) onto *name*."""
        if self.project_combo.findData(name) < 0:
            self.project_combo.blockSignals(True)
            self.project_combo.addItem(name, userData=name)
            self.project_combo.blockSignals(False)
        self._select(self.project_combo, name)
        self._push_context()
        self.set_saved_now(f"just now · created {name}")
        self.projects_changed.emit()

    def _on_shots_added(self, project: str, sequence: str, shot: str) -> None:
        """Report the batch that just landed, and reload what depends on it.

        The context is left where it is: adding shots is a data-axis act, and
        the shot the user wants to launch into is a deliberate choice, not a
        side effect of a bulk import.
        """
        self.set_saved_now(f"just now · added {sequence}/{shot}")
        self.projects_changed.emit()

    # -- Undo --------------------------------------------------------------

    def _refresh_revert_state(self) -> None:
        """Enable Revert exactly when a backup exists.

        A disabled button plus a tooltip that says *why* beats a button that
        looks live and then reports "nothing to revert" after the click.
        """
        try:
            available = bool(self._data_source.has_env_backup())
        except Exception:
            available = False
        self.revert_btn.setEnabled(available)
        self.revert_btn.setToolTip(
            "Restore the environment overrides as they were before the last save"
            if available else "No backup yet — the first edit creates one")

    def _on_revert(self) -> None:
        """Take back the last write to ``env.yaml``, then re-render."""
        diagnostics = self._data_source.revert_env()
        errors = [d for d in diagnostics if d.level == "error"]
        if errors:
            self.saved_label.setText(f"Not reverted — {errors[0].message}")
            return
        self._push_context()
        self.preflight_page.refresh()
        self.set_saved_now("reverted · previous overrides restored")
        self._refresh_revert_state()

    def _on_diagnostics(self, errors: int, warnings: int) -> None:
        """Footer counter — fed by the Preflight column, never recomputed here."""
        self.set_issue_counts(errors, warnings)

    def set_issue_counts(self, errors: int, warnings: int) -> None:
        """Update the footer issue counter."""
        parts = []
        if errors:
            parts.append(f"{errors} error" + ("s" if errors != 1 else ""))
        if warnings:
            parts.append(f"{warnings} warning" + ("s" if warnings != 1 else ""))
        self.warnings_label.setText(" · ".join(parts) if parts else "0 issues")

    def _on_copy_env(self) -> None:
        """Copy the resolved environment to the clipboard as NAME=value lines."""
        text = self.resolved_preview.env_text()
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self.set_saved_now("env copied")

    def set_saved_now(self, text: str = "just now") -> None:
        """Update the footer saved stamp after a successful write."""
        self.saved_label.setText(f"Saved {text}")


def _panel(content: QWidget) -> QFrame:
    """Wrap a column in a boxed surface.

    Page tables and the preview are plain widgets with a transparent
    background, so side by side they read as one grey field. Reusing the
    view-viewport convention (``StyledPanel`` + ``Plain`` shadow + ``Base``
    fill) gives both columns the same surface without hard-coding any colour,
    so it still tracks a dark system theme.
    """
    frame = QFrame()
    frame.setObjectName("settingsPanel")
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    frame.setFrameShadow(QFrame.Shadow.Plain)      # 1px hairline, no bevel
    frame.setBackgroundRole(QPalette.ColorRole.Base)
    frame.setAutoFillBackground(True)
    box = QVBoxLayout(frame)
    box.setContentsMargins(PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN)
    box.addWidget(content)
    return frame


# Backwards-compatible alias: main_window imports SettingsPanel until T06.
SettingsPanel = SettingsWindow
