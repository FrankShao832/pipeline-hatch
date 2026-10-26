"""Projects page — the real project table (U2, connected 2026-10-25).

Reads ``SettingsDataSource.projects()`` and shows one row per configured
project: name, counts from disk, scaffold state and where the row came from
(database or YAML fallback). The two root paths live in a detail strip under the
table: they are long, nearly identical across rows, and unreadable at column
width — the strip keeps them complete and copyable instead of elided.

No YAML, no ORM, no disk access here — the page only knows the view-model
contract (plan G2).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from launcher.ui.viewmodels import ProjectRow, SettingsDataSource

COLUMNS: tuple[str, ...] = ("Name", "Seqs", "Shots", "Scaffold", "Source")

SCAFFOLD_TEXT = {
    "complete": "complete",
    "missing": "missing",
    "n/a": "n/a",
}


class ProjectsPage(QWidget):
    """Table of every configured project plus a scaffold repair action."""

    def __init__(self, data_source: SettingsDataSource, parent: QWidget | None = None) -> None:
        """Build the page.

        Args:
            data_source: Backend implementing ``SettingsDataSource``.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._data_source = data_source
        self._rows: dict[str, ProjectRow] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        heading = QLabel("Projects")
        heading.setStyleSheet("font-size: 15px; font-weight: bold;")

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #8b94a3;")

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail_label.setStyleSheet("color: #4b5563;")
        self.detail_label.setMinimumHeight(52)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        self.repair_btn = QPushButton("Repair scaffold")
        self.repair_btn.clicked.connect(self._on_repair)
        self.repair_btn.setEnabled(False)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self.refresh_btn)
        buttons.addWidget(self.repair_btn)
        buttons.addStretch(1)

        layout.addWidget(heading)
        layout.addWidget(self.status_label)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.detail_label)
        layout.addLayout(buttons)

        self.refresh()

    # -- Data --------------------------------------------------------------

    def refresh(self) -> None:
        """Reload every row from the data source."""
        try:
            rows = self._data_source.projects()
        except Exception as exc:                 # database down, YAML unreadable
            self.table.setRowCount(0)
            self._rows = {}
            self.status_label.setText(f"Could not load projects: {exc}")
            self.detail_label.setText("")
            self.repair_btn.setEnabled(False)
            return

        self._rows = {row.name: row for row in rows}
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            cells = (
                f"{row.name} (disabled)" if not row.enabled else row.name,
                str(row.seqs),
                str(row.shots),
                SCAFFOLD_TEXT.get(row.scaffold_state, row.scaffold_state),
                row.source,
            )
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col in (1, 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                          | Qt.AlignmentFlag.AlignVCenter)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row.name)
                    if not row.enabled:
                        item.setToolTip("disabled: hidden from the launcher tree")
                if col == 3:
                    item.setToolTip(
                        f"{row.scaffold_missing} required folder(s) missing"
                        if row.scaffold_state == "missing"
                        else "all required folders exist"
                    )
                if col == 4:
                    item.setToolTip("from the launcher database"
                                    if row.source == "db" else
                                    "from config/projects.yaml (not in the database)")
                self.table.setItem(index, col, item)

        missing = sum(1 for r in rows if r.scaffold_state == "missing")
        self.status_label.setText(
            f"{len(rows)} project(s) · {missing} with a missing scaffold"
            if rows else "No projects configured."
        )
        if rows:
            self.table.selectRow(0)
        else:
            self._update_detail("")

    def _current_name(self) -> str:
        items = self.table.selectedItems()
        if not items:
            return ""
        return self.table.item(items[0].row(), 0).data(Qt.ItemDataRole.UserRole) or ""

    def _update_detail(self, name: str) -> None:
        """Show the full paths of the selected project under the table."""
        row = self._rows.get(name)
        if row is None:
            self.detail_label.setText("")
            return
        state = ("all required folders exist" if row.scaffold_state == "complete"
                 else f"{row.scaffold_missing} required folder(s) missing")
        self.detail_label.setText(
            f"work:    {row.root}/{row.name}\n"
            f"publish: {row.publish_root}/{row.name}\n"
            f"scaffold: {state} · source: {row.source}"
        )

    def _on_selection_changed(self) -> None:
        name = self._current_name()
        self.repair_btn.setEnabled(bool(name))
        self._update_detail(name)

    # -- Actions -----------------------------------------------------------

    def _on_repair(self) -> None:
        """Create the missing skeleton folders for the selected project."""
        name = self._current_name()
        if not name:
            return
        plan = self._data_source.scaffold_plan(name)
        missing = [row.path for row in plan if row.path and not row.exists]
        if not missing:
            QMessageBox.information(self, "Repair scaffold",
                                    f"{name}: nothing to create.")
            return
        preview = "\n".join(missing[:10])
        more = "" if len(missing) <= 10 else f"\n… and {len(missing) - 10} more"
        if QMessageBox.question(
            self, "Repair scaffold",
            f"Create {len(missing)} folder(s) for {name}?\n\n{preview}{more}",
        ) != QMessageBox.StandardButton.Yes:
            return
        summary = self._data_source.repair(name, dry_run=False)
        created, skipped, errors = summary.counts()
        self.status_label.setText(
            f"{name}: {created} created · {skipped} already there · {errors} error(s)"
        )
        self.refresh()
