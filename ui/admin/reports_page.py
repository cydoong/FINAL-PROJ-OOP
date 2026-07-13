"""
ui.admin.reports_page
=========================
Four payroll reports (summary by period, employee history, deduction
summary, department report) + overall totals, exact port of
admin/reports.php.
"""
from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtWidgets import QDateEdit, QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from core.reports_service import get_reports
from core.utils import format_currency, format_date
from database.db_manager import get_db
from ui import theme
from ui.widgets.common import SectionHeader, StatCard, make_button
from ui.widgets.table import DataTable


class ReportsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        header = SectionHeader("Reports", "Payroll analytics and summaries")
        lay.addWidget(header)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("From:"))
        self.start_date = QDateEdit(calendarPopup=True)
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        self.start_date.setDate(date.today() - timedelta(days=180))
        filters.addWidget(self.start_date)
        filters.addWidget(QLabel("To:"))
        self.end_date = QDateEdit(calendarPopup=True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        self.end_date.setDate(date.today() + timedelta(days=30))
        filters.addWidget(self.end_date)
        apply_btn = make_button("Apply", "primary")
        apply_btn.clicked.connect(self.refresh)
        filters.addWidget(apply_btn)
        filters.addStretch()
        lay.addLayout(filters)

        self.kpi_row = QHBoxLayout()
        lay.addLayout(self.kpi_row)

        tabs = QTabWidget()
        self.summary_table = DataTable(["Period", "Pay Date", "Employees", "Gross", "Allowances",
                                         "Deductions", "Net", "Avg Net"])
        self.emp_table = DataTable(["Employee", "Code", "Department", "Position", "Pay Runs", "Gross", "Net", "Avg Net"])
        self.deduct_table = DataTable(["Deduction", "Mandatory", "Times Applied", "Total", "Average"])
        self.dept_table = DataTable(["Department", "Employees", "Gross", "Deductions", "Net", "Avg Net", "Max Net"])
        tabs.addTab(self.summary_table, "By Period")
        tabs.addTab(self.emp_table, "By Employee")
        tabs.addTab(self.deduct_table, "Deductions")
        tabs.addTab(self.dept_table, "By Department")
        lay.addWidget(tabs, 1)

        self.refresh()

    def refresh(self):
        while self.kpi_row.count():
            item = self.kpi_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        db = get_db()
        with db.session() as s:
            r = get_reports(s, self.start_date.date().toPyDate(), self.end_date.date().toPyDate())

        t = r.totals
        self.kpi_row.addWidget(StatCard("Total Records", str(t.get("total_records", 0)), "\U0001F4C4", theme.PINK))
        self.kpi_row.addWidget(StatCard("Total Gross", format_currency(t.get("grand_gross", 0)), "\U0001F4B5", theme.PURPLE))
        self.kpi_row.addWidget(StatCard("Total Net", format_currency(t.get("grand_net", 0)), "\U0001F4B0", theme.SUCCESS))
        self.kpi_row.addWidget(StatCard("Total Deductions", format_currency(t.get("grand_deduct", 0)), "\u2796", theme.DANGER))
        self.kpi_row.addWidget(StatCard("Average Net", format_currency(t.get("avg_net", 0)), "\U0001F4C8", theme.CYAN))

        self.summary_table.clear_rows()
        for row in r.payroll_summary:
            self.summary_table.add_row([
                row["period_name"], format_date(row["pay_date"]), str(row["emp_count"]),
                format_currency(row["total_gross"]), format_currency(row["total_allow"]),
                format_currency(row["total_deduct"]), format_currency(row["total_net"]), format_currency(row["avg_net"]),
            ])

        self.emp_table.clear_rows()
        for row in r.emp_history:
            self.emp_table.add_row([
                row["full_name"], row["employee_code"], row["department_name"], row["position_title"],
                str(row["pay_count"]), format_currency(row["total_gross"]), format_currency(row["total_net"]),
                format_currency(row["avg_net"]),
            ])

        self.deduct_table.clear_rows()
        for row in r.deduct_summary:
            self.deduct_table.add_row([
                row["type_name"], "Yes" if row["is_mandatory"] else "No", str(row["times_applied"]),
                format_currency(row["total_amount"]), format_currency(row["avg_amount"]),
            ])

        self.dept_table.clear_rows()
        for row in r.dept_report:
            self.dept_table.add_row([
                row["department_name"], str(row["emp_count"]), format_currency(row["total_gross"]),
                format_currency(row["total_deduct"]), format_currency(row["total_net"]),
                format_currency(row["avg_net"]), format_currency(row["max_net"]),
            ])
