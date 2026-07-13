"""
ui.admin.pay_periods_page
=============================
Pay period CRUD, exact port of admin/pay_periods.php.
"""
from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtWidgets import QComboBox, QDateEdit, QLineEdit, QVBoxLayout, QWidget

import core.pay_period_service as pps
from core.session import current_session
from core.utils import format_currency, format_date
from database.db_manager import get_db
from ui.widgets.common import Badge, SectionHeader, confirm, error as show_err
from ui.widgets.dialogs import BaseFormDialog
from ui.widgets.table import DataTable, action_bar

PERIOD_TYPES = ["weekly", "bi_weekly", "semi_monthly", "monthly"]
STATUSES = ["open", "processing", "closed"]


class PayPeriodFormDialog(BaseFormDialog):
    def __init__(self, parent, editing=None):
        title = "Edit Pay Period" if editing else "Add Pay Period"
        super().__init__(title, parent=parent, width=460)
        self.editing = editing
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. July 2026")
        self.period_type = QComboBox()
        self.period_type.addItems([t.replace("_", " ").title() for t in PERIOD_TYPES])
        self.start_date = QDateEdit(calendarPopup=True)
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        self.start_date.setDate(date.today().replace(day=1))
        self.end_date = QDateEdit(calendarPopup=True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        self.end_date.setDate(date.today())
        self.pay_date = QDateEdit(calendarPopup=True)
        self.pay_date.setDisplayFormat("yyyy-MM-dd")
        self.pay_date.setDate(date.today() + timedelta(days=5))
        self.status = QComboBox()
        self.status.addItems([s.title() for s in STATUSES])

        self.add_row("Period Name*", self.name)
        self.add_row("Period Type", self.period_type)
        self.add_row("Start Date*", self.start_date)
        self.add_row("End Date*", self.end_date)
        self.add_row("Pay Date*", self.pay_date)
        self.add_row("Status", self.status)

        if editing:
            self.name.setText(editing.period_name)
            self.period_type.setCurrentText(editing.period_type.replace("_", " ").title())
            self.start_date.setDate(editing.start_date)
            self.end_date.setDate(editing.end_date)
            self.pay_date.setDate(editing.pay_date)
            self.status.setCurrentText(editing.status.title())


class PayPeriodsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        header = SectionHeader("Pay Periods", "Define payroll cycles", "+ Add Pay Period")
        header.action_btn.clicked.connect(self.open_add)
        lay.addWidget(header)

        self.table = DataTable(["Period", "Type", "Start", "End", "Pay Date", "Records", "Total Net", "Status", "Actions"])
        lay.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        db = get_db()
        with db.session() as s:
            rows = pps.list_pay_periods(s)
        self.table.clear_rows()
        for p in rows:
            r = self.table.add_row([
                p.period_name, p.period_type.replace("_", " ").title(), format_date(p.start_date),
                format_date(p.end_date), format_date(p.pay_date), str(p.payroll_count),
                format_currency(p.total_net), "", None,
            ])
            self.table.set_widget(r, 7, Badge(p.status))
            actions = action_bar([
                ("\u270F\uFE0F", "ghost", lambda _, pp=p: self.open_edit(pp), "Edit pay period"),
                ("\U0001F5D1\uFE0F", "danger", lambda _, pp=p: self.delete(pp), "Delete pay period"),
            ])
            self.table.set_widget(r, 8, actions)

    def open_add(self):
        dlg = PayPeriodFormDialog(self)
        dlg.save_btn.clicked.connect(lambda: self._submit_add(dlg))
        dlg.exec()

    def _submit_add(self, dlg):
        dlg.clear_error()
        if not dlg.name.text().strip():
            dlg.show_error("Period name is required.")
            return
        db = get_db()
        with db.session() as s:
            result = pps.add_pay_period(
                s, dlg.name.text().strip(), dlg.period_type.currentText().lower().replace(" ", "_"),
                dlg.start_date.date().toPyDate(), dlg.end_date.date().toPyDate(), dlg.pay_date.date().toPyDate(),
                dlg.status.currentText().lower(), current_session.user_id,
            )
        if not result.success:
            dlg.show_error(result.error)
            return
        dlg.accept()
        self.refresh()

    def open_edit(self, period_row):
        dlg = PayPeriodFormDialog(self, editing=period_row)
        dlg.save_btn.clicked.connect(lambda: self._submit_edit(dlg, period_row.period_id))
        dlg.exec()

    def _submit_edit(self, dlg, period_id):
        dlg.clear_error()
        db = get_db()
        with db.session() as s:
            result = pps.edit_pay_period(
                s, period_id, dlg.name.text().strip(), dlg.period_type.currentText().lower().replace(" ", "_"),
                dlg.start_date.date().toPyDate(), dlg.end_date.date().toPyDate(), dlg.pay_date.date().toPyDate(),
                dlg.status.currentText().lower(),
            )
        if not result.success:
            dlg.show_error(result.error)
            return
        dlg.accept()
        self.refresh()

    def delete(self, period_row):
        if not confirm(self, "Delete Pay Period?", f'Delete "{period_row.period_name}"?', danger=True):
            return
        db = get_db()
        with db.session() as s:
            result = pps.delete_pay_period(s, period_row.period_id)
        if result.success:
            self.refresh()
        else:
            show_err(self, "Cannot Delete", result.error)
