"""
ui.employee.dashboard_page
==============================
Employee landing page: welcome banner, quick stats, recent payslips —
exact port of user/dashboard.php.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.dashboard_service import get_employee_dashboard
from core.session import current_session
from core.utils import format_currency, format_date
from database.db_manager import get_db
from ui import theme
from ui.widgets.common import Badge, StatCard
from ui.widgets.table import DataTable


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("card", "true")


class EmployeeDashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lay = QVBoxLayout(self)
        self.lay.setSpacing(20)
        self.refresh()

    def refresh(self):
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        db = get_db()
        with db.session() as s:
            d = get_employee_dashboard(s, current_session.employee_id)

        if not d.employee:
            self.lay.addWidget(QLabel("Employee record not found."))
            return

        banner = Card()
        bl = QVBoxLayout(banner)
        bl.setContentsMargins(24, 20, 24, 20)
        greeting = QLabel(f"Welcome back, {d.employee.first_name}! \U0001F44B")
        greeting.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {theme.TEXT_STRONG};")
        bl.addWidget(greeting)
        sub = QLabel(f"{d.position_title} \u00b7 {d.department_name}")
        sub.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        bl.addWidget(sub)
        self.lay.addWidget(banner)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(16)
        kpi_row.addWidget(StatCard("Monthly Base Salary", format_currency(d.base_salary), "\U0001F4B5", theme.PINK))
        kpi_row.addWidget(StatCard("Total Pay Runs", str(d.total_pay_runs), "\U0001F4C4", theme.PURPLE))
        kpi_row.addWidget(StatCard("Year-to-Date Net", format_currency(d.ytd_net), "\U0001F4C8", theme.CYAN))
        if d.latest_pay:
            kpi_row.addWidget(StatCard("Latest Net Pay", format_currency(d.latest_pay["net_pay"]),
                                        "\u2705", theme.SUCCESS, subtext=d.latest_pay["period_name"]))
        self.lay.addLayout(kpi_row)

        recent_card = Card()
        rl = QVBoxLayout(recent_card)
        rl.setContentsMargins(20, 16, 20, 16)
        title = QLabel("Recent Payslips")
        title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {theme.TEXT_STRONG}; margin-bottom: 8px;")
        rl.addWidget(title)
        table = DataTable(["Period", "Pay Date", "Gross", "Net", "Status"])
        for p in d.recent_pays:
            r = table.add_row([p["period_name"], format_date(p["pay_date"]), format_currency(p["gross_pay"]),
                                format_currency(p["net_pay"]), ""])
            table.set_widget(r, 4, Badge(p["status"]))
        rl.addWidget(table)
        self.lay.addWidget(recent_card)
        self.lay.addStretch()
