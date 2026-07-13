"""
ui.employee.attendance_page
===============================
Employee's own daily attendance log — read-only (attendance is recorded
by the admin, front-desk style; see ui/admin/attendance_page.py), with
a monthly summary and full daily breakdown so employees can see exactly
what days/hours are feeding into their next payslip.
"""
from __future__ import annotations

import calendar
from datetime import date

from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget

import core.attendance_service as ats
from core.session import current_session
from core.utils import format_time
from database.db_manager import get_db
from ui import theme
from ui.widgets.common import Badge, SectionHeader, StatCard, make_button
from ui.widgets.table import DataTable

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]


class AttendancePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        lay.addWidget(SectionHeader("My Attendance", "Your daily time-in/time-out record"))

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Month:"))
        self.month_combo = QComboBox()
        self.month_combo.addItems(MONTH_NAMES)
        self.month_combo.setCurrentIndex(date.today().month - 1)
        filter_row.addWidget(self.month_combo)
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2020, 2035)
        self.year_spin.setValue(date.today().year)
        filter_row.addWidget(self.year_spin)
        view_btn = make_button("View", "primary")
        view_btn.clicked.connect(self.refresh)
        filter_row.addWidget(view_btn)
        filter_row.addStretch()
        lay.addLayout(filter_row)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        self.card_present = StatCard("Days Present", "0", "\u2705", theme.SUCCESS)
        self.card_late = StatCard("Days Late", "0", "\u23F0", theme.WARNING)
        self.card_absent = StatCard("Days Absent", "0", "\U0001F6AB", theme.DANGER)
        self.card_hours = StatCard("Total Hours", "0", "\U0001F550", theme.CYAN)
        self.card_ot = StatCard("Overtime Hours", "0", "\u26A1", theme.PURPLE)
        for c in (self.card_present, self.card_late, self.card_absent, self.card_hours, self.card_ot):
            cards_row.addWidget(c)
        lay.addLayout(cards_row)

        self.table = DataTable(["Date", "Day", "Time In", "Time Out", "Hours", "OT Hours", "Status"])
        lay.addWidget(self.table, 1)

        self.refresh()

    def refresh(self):
        emp_id = current_session.employee_id
        if not emp_id:
            return
        year = self.year_spin.value()
        month = self.month_combo.currentIndex() + 1
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])

        db = get_db()
        with db.session() as s:
            rows = ats.list_range(s, emp_id, start, end)
            summary = ats.compute_period_summary(s, emp_id, start, end)

        self.card_present.set_value(f"{summary.days_worked:g}")
        self.card_late.set_value(f"{summary.days_late:g}")
        self.card_absent.set_value(f"{summary.days_absent:g}")
        self.card_hours.set_value(f"{summary.total_hours:.1f}")
        self.card_ot.set_value(f"{summary.overtime_hours:.1f}")

        self.table.clear_rows()
        if not rows:
            self.table.add_row(["No attendance recorded for this month yet.", "", "", "", "", "", None])
            return
        for rec in rows:
            r = self.table.add_row([
                rec.work_date.strftime("%b %d, %Y"), rec.work_date.strftime("%A"),
                format_time(rec.time_in), format_time(rec.time_out),
                f"{rec.hours_worked:.2f}" if rec.hours_worked else "—",
                f"{rec.overtime_hours:.2f}" if rec.overtime_hours else "—",
                None,
            ])
            self.table.set_widget(r, 6, Badge(rec.status))
