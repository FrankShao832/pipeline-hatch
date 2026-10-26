"""Resolved environment preview — what a launch really injects (T13).

The left column of the settings window: pick a show, a DCC and a department, and
see the exact mapping ``build_env_context()`` produces for that combination, with
the scope that won each key and whether a lower scope was shadowed.

Reads only ``SettingsDataSource`` (plan G1/G2): no YAML, no ORM, no disk.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from launcher.ui.viewmodels import SettingsDataSource
from launcher.ui.widgets.scope_badge import badge_color, badge_text

COLUMNS: tuple[str, ...] = ("Name", "Value", "Scope")


class ResolvedPreview(QWidget):
    """Show/DCC/department pickers plus the resolved environment table."""

    resolved_changed = Signal(int)          # number of rows, for the footer

    def __init__(self, data_source: SettingsDataSource, parent: QWidget | None = None) -> None:
        """Build the preview.

        Args:
            data_source: Backend implementing ``SettingsDataSource``.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._data_source = data_source
        self._rows: list = []
        self._build_ui()
        self.refresh_sources()

    # -- Construction ------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel("Resolved Environment")
        title.setStyleSheet("font-weight: bold;")
        hint = QLabel("What a launch injects for this show / DCC / department.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b94a3; font-size: 11px;")

        self.show_combo = QComboBox()
        self.show_combo.setToolTip("Show — the project whose rows are resolved")
        self.show_combo.currentIndexChanged.connect(self._reload)

        self.dcc_combo = QComboBox()
        self.dcc_combo.setToolTip("DCC — the application axis (runtime)")
        self.dcc_combo.currentIndexChanged.connect(self._reload)

        self.department_combo = QComboBox()
        self.department_combo.setToolTip("Department — the data axis")
        self.department_combo.currentIndexChanged.connect(self._reload)

        pickers = QHBoxLayout()
        pickers.setSpacing(6)
        pickers.addWidget(self.dcc_combo, 1)
        pickers.addWidget(self.department_combo, 1)

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
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color: #8b94a3; font-size: 11px;")

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.show_combo)
        layout.addLayout(pickers)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.summary_label)

    # -- Data --------------------------------------------------------------

    def _fill(self, combo: QComboBox, values: list[str], tooltip_prefix: str = "") -> None:
        """Replace a combo's items without emitting a reload per item."""
        combo.blockSignals(True)
        combo.clear()
        for value in values:
            combo.addItem(value, userData=value)
        combo.blockSignals(False)
        if combo.count():
            combo.setCurrentIndex(0)

    def refresh_sources(self) -> None:
        """Reload the pickers (projects, DCC roles, departments) then resolve."""
        try:
            shows = [row.name for row in self._data_source.projects()]
            roles = list(self._data_source.dcc_roles())
            departments = list(self._data_source.departments())
        except Exception as exc:
            self._rows = []
            self.table.setRowCount(0)
            self.summary_label.setText(f"Could not load sources: {exc}")
            self.resolved_changed.emit(0)
            return

        self._fill(self.show_combo, shows)
        self._fill(self.dcc_combo, roles)
        self._fill(self.department_combo, departments)
        if self.department_combo.count():
            # Departments are shown in vocabulary order; fx is the common default.
            index = self.department_combo.findData("fx")
            self.department_combo.setCurrentIndex(index if index >= 0 else 0)
        self._reload()

    def current_selection(self) -> tuple[str, str, str]:
        """Return ``(show, dcc, department)`` as currently selected."""
        return (
            self.show_combo.currentData() or "",
            self.dcc_combo.currentData() or "",
            self.department_combo.currentData() or "",
        )

    def _reload(self) -> None:
        """Resolve the environment for the current selection."""
        show, dcc, department = self.current_selection()
        try:
            rows = self._data_source.resolved(show, dcc, department)
        except Exception as exc:
            rows = []
            self.summary_label.setText(f"Could not resolve: {exc}")
        self._rows = list(rows)
        self._fill_table()
        self.resolved_changed.emit(len(self._rows))

    def _fill_table(self) -> None:
        self.table.setRowCount(len(self._rows))
        for index, row in enumerate(self._rows):
            name_item = QTableWidgetItem(row.name)
            value_item = QTableWidgetItem(row.value)
            value_item.setToolTip(row.value)
            scope_item = QTableWidgetItem(
                badge_text(row.source, row.shadowed[-1][0] if row.is_shadowed else "")
            )
            # QTableWidgetItem has no stylesheet; colour the text directly.
            scope_item.setForeground(QBrush(QColor(badge_color(row.source))))
            scope_item.setToolTip(
                "\n".join(f"{scope}: {value}" for scope, value in row.shadowed)
                if row.is_shadowed else f"{row.source} — nothing shadowed"
            )
            self.table.setItem(index, 0, name_item)
            self.table.setItem(index, 1, value_item)
            self.table.setItem(index, 2, scope_item)

        shadowed = sum(1 for row in self._rows if row.is_shadowed)
        parts = [f"{len(self._rows)} variable(s)"]
        if shadowed:
            parts.append(f"{shadowed} shadowed")
        if not self._rows:
            parts = ["no variables — pick a show with discs on disk"]
        self.summary_label.setText(" · ".join(parts))

    # -- Output ------------------------------------------------------------

    def env_text(self) -> str:
        """Return the resolved rows as ``NAME=value`` lines (for ``Copy .env``)."""
        return "\n".join(f"{row.name}={row.value}" for row in self._rows)
