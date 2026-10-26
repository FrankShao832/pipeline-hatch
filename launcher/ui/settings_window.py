"""Settings window — three columns: resolved preview / pages / nav.

Plan v1.1 §5 U1 (T05). This file is the **shell only**: the three pages are
placeholders until T07 (Projects), T14 (Environment) and T15 (Preflight).

Design contract (D-B/D-C/D-D):
  * modeless QDialog, 1200x780 default, 1080x720 minimum
  * resolved preview 420px fixed | pages flexible | nav 200px fixed
  * the **nav sits on the right edge** (the mouse lives on the right of the
    screen) and the page column — the one that changes with the selection —
    sits **next to it in the middle**, so a click and its result stay in the
    same neighbourhood; the resolved preview is the far column, left
  * instant-apply semantics: a ``Close`` button, no OK/Cancel transaction

Data comes exclusively through :class:`launcher.ui.viewmodels.SettingsDataSource`.
While the fixture source is wired in, the footer says so — nobody should mistake
demo numbers for their real pipeline.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from launcher.ui.fakes import FakeSettingsDataSource
from launcher.ui.widgets.projects_page import ProjectsPage
from launcher.ui.viewmodels import SettingsDataSource

NAV_WIDTH = 200
PREVIEW_WIDTH = 420
PANEL_MARGIN = 8
DEFAULT_SIZE = (1200, 780)
MINIMUM_SIZE = (1080, 720)
NAV_ITEMS: tuple[str, ...] = ("Projects", "Environment", "Preflight")


class SettingsWindow(QDialog):
    """Three-column settings shell.

    Signals:
        projects_changed: Emitted after any project CRUD operation so the main
            window can refresh its project tree.
        open_env_for_show: Emitted when another page asks to jump to the
            Environment page filtered by a show name.
    """

    projects_changed = Signal()
    open_env_for_show = Signal(str)

    def __init__(self, data_source: SettingsDataSource | None = None,
                 db_session=None, current_user=None, parent=None) -> None:
        """Build the shell.

        Args:
            data_source: Backend implementing ``SettingsDataSource``. Defaults
                to the rich fixture (UI-first phase).
            db_session: Kept for main-window compatibility until T06 rewires it.
            current_user: Kept for main-window compatibility.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._data_source: SettingsDataSource = (
            data_source if data_source is not None else FakeSettingsDataSource("rich")
        )
        self.is_fixture = isinstance(self._data_source, FakeSettingsDataSource)
        self._db_session = db_session
        self._current_user = current_user

        self.setWindowTitle("Settings")
        self.setModal(False)
        self.resize(*DEFAULT_SIZE)
        self.setMinimumSize(*MINIMUM_SIZE)
        self._build_ui()

    # -- Construction ------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        self.nav = QListWidget()
        self.nav.setFixedWidth(NAV_WIDTH)
        self.nav.addItems(list(NAV_ITEMS))
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        # Diagnostics badge for the Environment row; hidden until T28 has a count.
        self.env_badge = QLabel("", self.nav)
        self.env_badge.hide()

        self.stack = QStackedWidget()
        self.projects_page = ProjectsPage(self._data_source)
        self.stack.addWidget(self.projects_page)
        self.stack.addWidget(_placeholder("Environment", "Scope tree lands in T14."))
        self.stack.addWidget(_placeholder("Preflight", "Diagnostics land in T15."))

        self.preview_host = QWidget()
        preview_layout = QVBoxLayout(self.preview_host)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_title = QLabel("Resolved Environment")
        preview_title.setStyleSheet("font-weight: bold;")
        preview_hint = QLabel("Live resolver preview lands in T13.")
        preview_hint.setWordWrap(True)
        preview_hint.setStyleSheet("color: #8b94a3;")
        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(preview_hint)
        preview_layout.addStretch(1)

        # Column order (left -> right): resolved preview | pages | nav.
        # Nav on the right edge keeps switching near the pointer; the page
        # column (the one that changes with the selection) sits right next to
        # it, so the click and its result are in the same place.
        #
        # The nav is a QListWidget, so Qt already gives it a hairline frame and
        # a base-coloured viewport. The other two columns are bare widgets,
        # which read as empty space — wrapping them in the same kind of frame
        # makes the window read as three surfaces instead of one grey field.
        self.preview_panel = _panel(self.preview_host)
        self.preview_panel.setFixedWidth(PREVIEW_WIDTH)
        self.pages_panel = _panel(self.stack)

        self.splitter.addWidget(self.preview_panel)
        self.splitter.addWidget(self.pages_panel)
        self.splitter.addWidget(self.nav)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes(
            [PREVIEW_WIDTH, DEFAULT_SIZE[0] - NAV_WIDTH - PREVIEW_WIDTH, NAV_WIDTH]
        )
        layout.addWidget(self.splitter, 1)

        layout.addLayout(self._build_footer())

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.saved_label = QLabel("Saved —")
        self.warnings_label = QLabel("0 warnings")
        self.fixture_label = QLabel("fixture data" if self.is_fixture else "")
        self.fixture_label.setStyleSheet("color: #f59e0b;")
        self.fixture_label.setVisible(self.is_fixture)

        self.copy_env_btn = QPushButton("Copy .env")
        self.copy_env_btn.setEnabled(False)          # enabled in T13
        self.open_config_btn = QPushButton("Open config")
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)

        footer.addWidget(self.saved_label)
        footer.addWidget(self.warnings_label)
        footer.addWidget(self.fixture_label)
        footer.addStretch(1)
        footer.addWidget(self.copy_env_btn)
        footer.addWidget(self.open_config_btn)
        footer.addWidget(self.close_btn)
        return footer

    # -- Behaviour ---------------------------------------------------------

    def _on_nav_changed(self, row: int) -> None:
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    def set_warning_count(self, count: int) -> None:
        """Update the footer warning counter (T28 wires this to diagnostics)."""
        self.warnings_label.setText(
            "0 warnings" if count == 0 else f"{count} warning" + ("s" if count != 1 else "")
        )

    def set_saved_now(self, text: str = "just now") -> None:
        """Update the footer saved stamp after a successful write."""
        self.saved_label.setText(f"Saved {text}")


def _panel(content: QWidget) -> QFrame:
    """Wrap a column in a boxed surface that matches the nav list's frame.

    The nav is a ``QListWidget``: Qt draws a hairline around it and fills its
    viewport with the palette's ``Base`` colour. The other columns are plain
    widgets with a transparent background, so side by side they read as one
    grey field. Reusing the viewport convention (``StyledPanel`` + ``Plain``
    shadow + ``Base`` fill) gives all three columns the same surface without
    hard-coding any colour, so it still tracks a dark system theme.
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


def _placeholder(title: str, hint: str) -> QWidget:
    """Build a placeholder page used until the real page lands."""
    page = QWidget()
    page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    layout = QVBoxLayout(page)
    # The enclosing panel already provides the inset.
    layout.setContentsMargins(0, 0, 0, 0)
    heading = QLabel(title)
    heading.setStyleSheet("font-size: 15px; font-weight: bold;")
    body = QLabel(hint)
    body.setStyleSheet("color: #8b94a3;")
    layout.addWidget(heading)
    layout.addWidget(body)
    layout.addStretch(1)
    return page


# Backwards-compatible alias: main_window imports SettingsPanel until T06.
SettingsPanel = SettingsWindow
