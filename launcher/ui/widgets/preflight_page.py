"""Preflight page — the problems that stop a launch from being trustworthy.

Every check here runs against the same rows the right column resolves, so the
page reads as "here is what is wrong with the environment you are looking at"
rather than a separate log. Reports both counts upward: the footer counter and
the tab badge are driven by this page, not computed twice.

Reads only ``SettingsDataSource`` (plan G1/G2): no YAML, no ORM, no disk.
The actual checks live behind ``diagnostics()`` — this page only renders them.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from launcher.ui.viewmodels import DiagnosticRow, SettingsContext, SettingsDataSource
from launcher.ui.widgets.style import COLUMN_TITLE_QSS

COLUMNS: tuple[str, ...] = ("Level", "Code", "Message", "Target")

LEVEL_COLORS = {
    "error": "#dc2626",
    "warn": "#f59e0b",
    "info": "#6b7280",
}


class PreflightPage(QWidget):
    """Sorted issue table with a re-run and a copy-report action."""

    diagnostics_changed = Signal(int, int)      # (errors, warnings)

    def __init__(self, data_source: SettingsDataSource, parent: QWidget | None = None) -> None:
        """Build the page.

        Args:
            data_source: Backend implementing ``SettingsDataSource``.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._data_source = data_source
        self._rows: list[DiagnosticRow] = []
        self._build_ui()
        self.refresh()

    # -- Construction ------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        heading = QLabel("Preflight")
        heading.setStyleSheet(COLUMN_TITLE_QSS)
        hint = QLabel(
            "Checks run against the same rows the right column resolves: missing "
            "paths, keys the DCCs never receive, duplicate project names."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b94a3; font-size: 11px;")

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        # Which context this run refers to. The checks themselves still read the
        # data source globally (T28 wires ``diagnostics(context)``), so the line
        # is here to keep the promise honest rather than imply per-shot results.
        self.scope_label = QLabel("")
        self.scope_label.setWordWrap(True)
        self.scope_label.setStyleSheet("color: #8b94a3;")

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #8b94a3;")

        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("color: #4b5563;")
        self.detail_label.setMinimumHeight(34)

        self.rerun_btn = QPushButton("Re-run checks")
        self.rerun_btn.clicked.connect(self.refresh)
        self.copy_btn = QPushButton("Copy report")
        self.copy_btn.clicked.connect(self._on_copy_report)
        self.copy_btn.setToolTip("Copy every issue as plain text")

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self.rerun_btn)
        buttons.addWidget(self.copy_btn)
        buttons.addStretch(1)

        layout.addWidget(heading)
        layout.addWidget(hint)
        layout.addWidget(self.scope_label)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.detail_label)
        layout.addWidget(self.status_label)
        layout.addLayout(buttons)

    # -- Context -----------------------------------------------------------

    def set_context(self, context: SettingsContext) -> None:
        """Record which context the report is being shown for."""
        self.scope_label.setText(
            f"scope: {context.summary() or '—'}"
            f" · shot: {context.seq or '?'}/{context.shot or '?'}"
            if (context.seq or context.shot) else
            f"scope: {context.summary() or '—'}"
        )

    # -- Data --------------------------------------------------------------

    def refresh(self) -> None:
        """Re-run the checks and republish both counts."""
        try:
            rows = list(self._data_source.diagnostics())
        except Exception as exc:                # backend down
            self._rows = []
            self.table.setRowCount(0)
            self.status_label.setText(f"Could not run checks: {exc}")
            self.detail_label.setText("")
            self.diagnostics_changed.emit(0, 0)
            return
        self._rows = sorted(rows, key=lambda row: row.sort_key())
        self._fill_table()
        self.diagnostics_changed.emit(*self.counts())

    def counts(self) -> tuple[int, int]:
        """Return ``(errors, warnings)`` for the current rows."""
        errors = sum(1 for row in self._rows if row.level == "error")
        warnings = sum(1 for row in self._rows if row.level == "warn")
        return (errors, warnings)

    def _fill_table(self) -> None:
        self.table.setRowCount(len(self._rows))
        for index, row in enumerate(self._rows):
            level_item = QTableWidgetItem(row.level)
            level_item.setForeground(QBrush(QColor(LEVEL_COLORS.get(row.level, "#6b7280"))))
            code_item = QTableWidgetItem(row.code)
            message_item = QTableWidgetItem(row.message)
            message_item.setToolTip(row.hint or row.message)
            target_item = QTableWidgetItem(row.target)
            for col, item in enumerate((level_item, code_item, message_item, target_item)):
                self.table.setItem(index, col, item)
        self.status_label.setText(self._status_text())
        if self._rows:
            self.table.selectRow(0)
        else:
            self.detail_label.setText("")

    def _status_text(self) -> str:
        if not self._rows:
            return "No problems found — the resolved environment is clean."
        errors, warnings = self.counts()
        parts = []
        if errors:
            parts.append(f"{errors} error" + ("s" if errors != 1 else ""))
        if warnings:
            parts.append(f"{warnings} warning" + ("s" if warnings != 1 else ""))
        if not parts:
            parts.append(f"{len(self._rows)} note(s)")
        return " · ".join(parts) + f" · {len(self._rows)} issue(s) total"

    def _on_selection_changed(self) -> None:
        """Show the fix hint under the table (the table stays one-line)."""
        items = self.table.selectedItems()
        if not items:
            self.detail_label.setText("")
            return
        index = items[0].row()
        if not 0 <= index < len(self._rows):
            self.detail_label.setText("")
            return
        row = self._rows[index]
        self.detail_label.setText(row.hint or "No hint for this check.")

    # -- Output ------------------------------------------------------------

    def report_text(self) -> str:
        """Return every issue as plain text (for ``Copy report``)."""
        lines = []
        for row in self._rows:
            head = f"[{row.level.upper()}] {row.code}"
            if row.target:
                head += f" ({row.target})"
            line = f"{head}: {row.message}"
            if row.hint:
                line += f" — {row.hint}"
            lines.append(line)
        return "\n".join(lines)

    def _on_copy_report(self) -> None:
        text = self.report_text()
        if text:
            QGuiApplication.clipboard().setText(text)
