"""Resolved environment preview — what a launch really injects (T13).

The right column: the exact mapping ``build_env_context()`` produces for the
context shown in the window's context bar (project / DCC / department), with the
scope that won each key and whether a lower scope was shadowed.

The three pickers used to live here. They moved up into the window's context bar
(2026-10-25) so the window has exactly one place that says "what are we looking
at" — the preview is now a pure renderer of ``set_context()``.

Reads only ``SettingsDataSource`` (plan G1/G2): no YAML, no ORM, no disk.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from launcher.ui.viewmodels import ResolvedRow, SettingsContext, SettingsDataSource
from launcher.ui.widgets.scope_badge import badge_color, badge_text
from launcher.ui.widgets.style import COLUMN_TITLE_QSS

COLUMNS: tuple[str, ...] = ("Name", "Value", "Scope")
NAME_COLUMN, VALUE_COLUMN, SCOPE_COLUMN = 0, 1, 2
NAME_MIN_WIDTH = 120
NAME_MAX_WIDTH = 200


class ResolvedPreview(QWidget):
    """The resolved environment table for the current ``SettingsContext``."""

    resolved_changed = Signal(int)          # number of rows, for the footer
    #: A value was edited in place — ``(name, new value)``. The window decides
    #: which layer it lands in and writes it; the preview never touches disk.
    env_edited = Signal(str, str)

    def __init__(self, data_source: SettingsDataSource, parent: QWidget | None = None) -> None:
        """Build the preview.

        Args:
            data_source: Backend implementing ``SettingsDataSource``.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._data_source = data_source
        self._rows: list[ResolvedRow] = []
        self._filling = False
        self._applying = False
        self.context = SettingsContext()
        self._build_ui()

    # -- Construction ------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel("Resolved Environment")
        title.setStyleSheet(COLUMN_TITLE_QSS)
        hint = QLabel("What a launch injects for the context above.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b94a3; font-size: 11px;")

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        # Values are mostly paths: keep the tail (the interesting half).
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        # Name is measured per refresh and then clamped (see _fit_name_column):
        # left on ResizeToContents, one long key (PUBLISHER_ENABLE_DATABASE)
        # silently takes the width the values need, and the values are the
        # payload of this table.
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        # Editing is deliberate: nothing is editable until a Value cell is
        # double-clicked, so a stray keystroke cannot rewrite an override.
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table.itemChanged.connect(self._on_item_changed)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color: #8b94a3; font-size: 11px;")

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.summary_label)

    # -- Data --------------------------------------------------------------

    def set_context(self, context: SettingsContext) -> None:
        """Point the preview at a context and re-resolve."""
        self.context = context
        self.resolve()

    def resolve(self) -> None:
        """Resolve the environment for the current context."""
        show, dcc, department = (self.context.project, self.context.dcc,
                                 self.context.department)
        try:
            rows = self._data_source.resolved(show, dcc, department)
            self.summary_label.setStyleSheet("color: #8b94a3; font-size: 11px;")
        except Exception as exc:
            rows = []
            self._rows = []
            self.table.setRowCount(0)
            self.summary_label.setText(f"Could not resolve: {exc}")
            self.resolved_changed.emit(0)
            return
        self._rows = list(rows)
        self._fill_table()
        self.resolved_changed.emit(len(self._rows))

    @property
    def rows(self) -> list[ResolvedRow]:
        """The rows currently rendered (read-only view)."""
        return list(self._rows)

    def _fill_table(self) -> None:
        self._filling = True
        try:
            self._fill_rows()
        finally:
            self._filling = False
        self._applying = False

    def _fill_rows(self) -> None:
        self.table.setRowCount(len(self._rows))
        for index, row in enumerate(self._rows):
            name_item = QTableWidgetItem(row.name)
            name_item.setToolTip(row.name)
            value_item = QTableWidgetItem(row.value)
            value_item.setToolTip(row.value)
            badge = badge_text(row.source, row.scope_key)
            scope_item = QTableWidgetItem(badge)
            # QTableWidgetItem has no stylesheet; colour the text directly.
            scope_item.setForeground(QBrush(QColor(badge_color(row.source))))
            scope_item.setToolTip(
                "\n".join(f"{scope}: {value}" for scope, value in row.shadowed)
                if row.is_shadowed else f"{badge} — nothing shadowed"
            )
            self.table.setItem(index, 0, name_item)
            self.table.setItem(index, 1, value_item)
            self.table.setItem(index, 2, scope_item)

        self._fit_name_column()
        shadowed = sum(1 for row in self._rows if row.is_shadowed)
        parts = [f"{len(self._rows)} variable(s)"]
        if shadowed:
            parts.append(f"{shadowed} shadowed")
        if not self._rows:
            parts = ["no variables — this context resolves to nothing"]
        self.summary_label.setText(" · ".join(parts))

    # -- In-place editing --------------------------------------------------

    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        """Only a double-clicked Value cell becomes editable."""
        if column != VALUE_COLUMN:
            return
        item = self.table.item(row, column)
        if item is None:
            return
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.table.editItem(item)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """A committed value edit: hand it to the window, then go read-only again."""
        if self._filling or self._applying or item.column() != VALUE_COLUMN:
            return
        name_item = self.table.item(item.row(), NAME_COLUMN)
        if name_item is None:
            return
        # Dropping the editable flag is itself a data change, so it re-enters
        # this slot: the flag is what keeps that from being an infinite chain.
        self._applying = True
        try:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        finally:
            self._applying = False
        self.env_edited.emit(name_item.text(), item.text())

    def _fit_name_column(self) -> None:
        """Size the Name column to its content, within bounds.

        Names are short and predictable, values are long paths: measuring once
        and clamping keeps the payload in view instead of letting the widest key
        dictate the column.
        """
        self.table.resizeColumnToContents(NAME_COLUMN)
        width = min(NAME_MAX_WIDTH,
                    max(NAME_MIN_WIDTH, self.table.columnWidth(NAME_COLUMN)))
        self.table.setColumnWidth(NAME_COLUMN, width)

    # -- Output ------------------------------------------------------------

    def env_text(self) -> str:
        """Return the resolved rows as ``NAME=value`` lines (for ``Copy .env``)."""
        return "\n".join(f"{row.name}={row.value}" for row in self._rows)
