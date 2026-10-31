"""Environment page — the raw override layers behind the resolved preview.

The right column answers "what does a launch inject"; this page answers "where
does each of those lines come from". One row per ``(name, scope, scope_key)``:
the same key can appear once per layer, and the layer with the highest
precedence is the row the preview shows.

Reads only ``SettingsDataSource`` (plan G1/G2): no YAML, no ORM, no disk.
Editing (add / delete / toggle) is deliberately not wired yet — the layer table
is here to make the relationship with the preview legible, not to be a CRUD
surface.
"""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from launcher.ui.viewmodels import SCOPE_ORDER, EnvRow, SettingsDataSource, scope_rank
from launcher.ui.widgets.scope_badge import badge_color, badge_text

COLUMNS: tuple[str, ...] = ("Name", "Value", "Scope")
ALL_SCOPES = "All scopes"


class EnvironmentPage(QWidget):
    """Table of every configured key at every scope, filtered by name/scope."""

    def __init__(self, data_source: SettingsDataSource, parent: QWidget | None = None) -> None:
        """Build the page.

        Args:
            data_source: Backend implementing ``SettingsDataSource``.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._data_source = data_source
        self._rows: list[EnvRow] = []
        self._visible: list[EnvRow] = []
        self._build_ui()
        self.refresh()

    # -- Construction ------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        heading = QLabel("Environment")
        heading.setStyleSheet("font-size: 15px; font-weight: bold;")
        hint = QLabel(
            "Every configured key at every scope — the raw material the right "
            "column merges. The highest-precedence row per key is the one a "
            "launch injects."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b94a3; font-size: 11px;")

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter keys…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)

        self.scope_combo = QComboBox()
        self.scope_combo.setToolTip("Show one layer only")
        self.scope_combo.addItem(ALL_SCOPES, "")
        for scope in SCOPE_ORDER:
            self.scope_combo.addItem(scope, scope)
        self.scope_combo.currentIndexChanged.connect(self._apply_filter)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        toolbar.addWidget(self.search_edit, 1)
        toolbar.addWidget(self.scope_combo)
        toolbar.addWidget(self.refresh_btn)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        # Same three columns as the preview, so the eye can compare directly.
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #8b94a3;")

        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail_label.setStyleSheet("color: #4b5563;")
        self.detail_label.setMinimumHeight(34)

        layout.addWidget(heading)
        layout.addWidget(hint)
        layout.addLayout(toolbar)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.detail_label)
        layout.addWidget(self.status_label)

    # -- Data --------------------------------------------------------------

    def refresh(self) -> None:
        """Reload every layer row from the data source."""
        try:
            rows = list(self._data_source.env_rows())
        except Exception as exc:                # yaml unreadable / backend down
            self._rows = []
            self._visible = []
            self.table.setRowCount(0)
            self.status_label.setText(f"Could not load environment: {exc}")
            self.detail_label.setText("")
            return

        # Group by key first, then by precedence — a key's layers read top-down.
        self._rows = sorted(rows, key=lambda row: (row.name, scope_rank(row.scope)))
        self._apply_filter()

    def _matches(self, row: EnvRow) -> bool:
        needle = self.search_edit.text().strip().lower()
        if needle and needle not in row.name.lower():
            return False
        wanted = self.scope_combo.currentData() or ""
        return not wanted or row.scope == wanted

    def _apply_filter(self) -> None:
        self._visible = [row for row in self._rows if self._matches(row)]
        self.table.setRowCount(len(self._visible))
        for index, row in enumerate(self._visible):
            name_item = QTableWidgetItem(row.name if row.enabled else f"{row.name} (off)")
            if not row.enabled:
                name_item.setToolTip("disabled — skipped when resolving")
            value_item = QTableWidgetItem("••••••" if row.secret else row.value)
            value_item.setToolTip("secret — masked" if row.secret else row.value)
            scope_item = QTableWidgetItem(badge_text(row.scope, row.scope_key))
            # QTableWidgetItem has no stylesheet; colour the text directly.
            scope_item.setForeground(QBrush(QColor(badge_color(row.scope))))
            scope_item.setToolTip(
                "; ".join(filter(None, (row.description,
                                        ", ".join(row.injected_to) or None)))
            )
            self.table.setItem(index, 0, name_item)
            self.table.setItem(index, 1, value_item)
            self.table.setItem(index, 2, scope_item)

        self.status_label.setText(self._status_text())
        if self._visible:
            self.table.selectRow(0)
        else:
            self.detail_label.setText("")

    def _status_text(self) -> str:
        total = len(self._rows)
        if not total:
            return "No environment keys configured."
        keys = Counter(row.name for row in self._rows)
        layered = sum(1 for count in keys.values() if count > 1)
        parts = [f"{total} row(s)", f"{len(keys)} key(s)"]
        if layered:
            parts.append(f"{layered} with more than one layer")
        if len(self._visible) != total:
            parts.append(f"{len(self._visible)} shown")
        return " · ".join(parts)

    def _selected_row(self) -> EnvRow | None:
        items = self.table.selectedItems()
        if not items:
            return None
        row_index = items[0].row()
        return self._visible[row_index] if 0 <= row_index < len(self._visible) else None

    def _on_selection_changed(self) -> None:
        """Explain the selected layer: where it applies and who receives it."""
        row = self._selected_row()
        if row is None:
            self.detail_label.setText("")
            return
        parts = [f"{row.name} @ {badge_text(row.scope, row.scope_key)}"]
        if row.description:
            parts.append(row.description)
        parts.append(
            "injected to: " + ", ".join(row.injected_to) if row.injected_to
            else "not in the dcc.yaml whitelist — no DCC receives it"
        )
        if not row.enabled:
            parts.append("disabled")
        self.detail_label.setText(" · ".join(parts))
