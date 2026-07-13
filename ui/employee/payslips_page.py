"""
ui.employee.payslips_page
=============================
Employee's own payslip list + viewer, exact port of user/my_payslips.php.
Reuses the same payslip HTML builder / print dialog as the admin page.
"""
from __future__ import annotations

from sqlalchemy import select

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from core.session import current_session
from core.utils import format_currency, format_date
from database.db_manager import get_db
from database.models import Department, Employee, PayPeriod, Payroll, PayrollAllowance, PayrollDeduction, Position
from ui.admin.payroll_page import PayslipDialog, build_payslip_data, build_payslip_html
from ui.widgets.common import Badge, SectionHeader
from ui.widgets.table import DataTable, action_bar


class PayslipsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        lay.addWidget(SectionHeader("My Payslips", "View and print your payslip history"))
        self.table = DataTable(["Period", "Pay Date", "Gross Pay", "Deductions", "Net Pay", "Status", "Actions"])
        lay.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        db = get_db()
        with db.session() as s:
            rows = s.execute(
                select(Payroll, PayPeriod)
                .join(PayPeriod, Payroll.period_id == PayPeriod.period_id)
                .where(Payroll.employee_id == current_session.employee_id)
                .order_by(PayPeriod.pay_date.desc())
            ).all()

        self.table.clear_rows()
        for payroll, period in rows:
            r = self.table.add_row([
                period.period_name, format_date(period.pay_date), format_currency(payroll.gross_pay),
                format_currency(payroll.total_deductions), format_currency(payroll.net_pay), "", None,
            ])
            self.table.set_widget(r, 5, Badge(payroll.payroll_status))
            actions = action_bar([
                ("View / Print", "primary", lambda _, pid=payroll.payroll_id: self.view_payslip(pid)),
            ])
            self.table.set_widget(r, 6, actions)

    def view_payslip(self, payroll_id: int):
        db = get_db()
        with db.session() as s:
            payroll = s.get(Payroll, payroll_id)
            if payroll.employee_id != current_session.employee_id:
                return
            employee = s.get(Employee, payroll.employee_id)
            department = s.get(Department, employee.department_id)
            position = s.get(Position, employee.position_id)
            period = s.get(PayPeriod, payroll.period_id)
            allowances = s.execute(select(PayrollAllowance).where(PayrollAllowance.payroll_id == payroll_id)).scalars().all()
            for a in allowances:
                _ = a.allowance_type.type_name
            deductions = s.execute(select(PayrollDeduction).where(PayrollDeduction.payroll_id == payroll_id)).scalars().all()
            for dd in deductions:
                _ = dd.deduction_type.type_name
            html = build_payslip_html(payroll, employee, department, position, period, allowances, deductions)
            payslip_data = build_payslip_data(payroll, employee, department, position, period, allowances, deductions)
        dlg = PayslipDialog(self, html, payslip_data)
        dlg.exec()
