"""
ui.admin.audit_log_page
===========================
Audit log listing with search/filter/stats, exact port of
admin/audit_log.php.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QVBoxLayout, QWidget

import core.audit_service as aus
from core.utils import format_datetime
from database.db_manager import get_db
from ui import theme
from ui.widgets.common import SearchBox, SectionHeader, StatCard
from ui.widgets.table import DataTable


class AuditLogPage(QWidget):
    PER_PAGE = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self.search_text = ""
        self.action_filter = ""

        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        header = SectionHeader("Audit Log", "Track every action taken in the system")
        lay.addWidget(header)

        self.kpi_row = QHBoxLayout()
        lay.addLayout(self.kpi_row)

        filters = QHBoxLayout()
        self.search_box = SearchBox("Search by user or action...")
        self.search_box.textChanged.connect(self._on_search)
        filters.addWidget(self.search_box)
        self.action_combo = QComboBox()
        self.action_combo.addItem("All Actions", "")
        self.action_combo.currentIndexChanged.connect(self._on_filter)
        filters.addWidget(self.action_combo)
        filters.addStretch()
        lay.addLayout(filters)

        self.table = DataTable(["Timestamp", "User", "Role", "Action", "Table", "Details"])
        lay.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        while self.kpi_row.count():
            item = self.kpi_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        db = get_db()
        with db.session() as s:
            stats = aus.audit_stats(s)
            actions = aus.list_distinct_actions(s)
            rows, total = aus.list_audit_logs(s, self.search_text, self.action_filter, 1, self.PER_PAGE)

        self.kpi_row.addWidget(StatCard("Total Logs", str(stats["total"]), "\U0001F4DC", theme.PINK))
        self.kpi_row.addWidget(StatCard("Today", str(stats["today"]), "\U0001F4C5", theme.CYAN))
        self.kpi_row.addWidget(StatCard("Failed Logins Today", str(stats["failed_today"]), "\u26A0\uFE0F", theme.DANGER))
        self.kpi_row.addWidget(StatCard("Password Resets", str(stats["resets"]), "\U0001F511", theme.WARNING))

        current = self.action_combo.currentData()
        self.action_combo.blockSignals(True)
        self.action_combo.clear()
        self.action_combo.addItem("All Actions", "")
        for a in actions:
            self.action_combo.addItem(a.replace("_", " ").title(), a)
        if current:
            idx = self.action_combo.findData(current)
            if idx >= 0:
                self.action_combo.setCurrentIndex(idx)
        self.action_combo.blockSignals(False)

        self.table.clear_rows()
        for log in rows:
            details = ""
            if log.old_value or log.new_value:
                details = f"{log.old_value or ''} \u2192 {log.new_value or ''}".strip()
            self.table.add_row([
                format_datetime(log.logged_at), log.username or "System", (log.role or "\u2014").title(),
                log.action.replace("_", " ").title(), log.table_affected or "\u2014", details or "\u2014",
            ])

    def _on_search(self, text):
        self.search_text = text
        self.refresh()

    def _on_filter(self):
        self.action_filter = self.action_combo.currentData() or ""
        self.refresh()
