"""
ui.admin.payroll_page
=========================
Payroll processing (with dynamic allowance/deduction rows), status
management, and a payslip viewer/printer — exact port of
admin/payroll.php.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout, QLabel,
    QLineEdit, QTextEdit, QVBoxLayout, QWidget, QFrame, QFileDialog,
)

import core.attendance_service as ats
import core.gov_rates as gov_rates
import core.pay_period_service as pps
import core.payroll_engine as pe
import core.reference_service as rs
from core.payslip_pdf import PayslipData, PayslipLine, generate_payslip_pdf
from core.session import current_session
from core.utils import format_currency, format_date
from database.db_manager import get_db
from database.models import Employee, PayPeriod, Payroll, PayrollAllowance, PayrollDeduction, Position
from config.settings import get_settings
from ui import theme
from ui.widgets.common import Badge, SectionHeader, confirm, error as show_err, info as show_info, make_button
from ui.widgets.dialogs import BaseFormDialog
from ui.widgets.table import DataTable, action_bar

STATUS_OPTIONS = ["draft", "approved", "paid", "cancelled"]
PAYMENT_METHODS = ["bank_transfer", "gcash", "maya", "cash", "check"]
PAYMENT_METHOD_LABELS = ["Bank Transfer", "GCash", "Maya", "Cash", "Check"]


class ProcessPayrollDialog(BaseFormDialog):
    def __init__(self, parent, employees, periods, allowance_types, deduction_types):
        super().__init__(
            "Process Payroll",
            "Days worked & overtime are pulled straight from Attendance — check Override only if you need to adjust them by hand.",
            parent, width=600,
        )
        self._employees = {e.employee_id: e for e in employees}
        self.employee_combo = QComboBox()
        for e in employees:
            self.employee_combo.addItem(f"{e.full_name} ({e.employee_code})", e.employee_id)
        self.period_combo = QComboBox()
        for p in periods:
            self.period_combo.addItem(p.period_name, p.period_id)
        self.employee_combo.currentIndexChanged.connect(self._pull_attendance)
        self.period_combo.currentIndexChanged.connect(self._pull_attendance)

        self.add_row("Employee*", self.employee_combo)
        self.add_row("Pay Period*", self.period_combo)

        self.override_check = QCheckBox("Override attendance-computed values")
        self.override_check.toggled.connect(self._toggle_override)
        self.add_full_row(self.override_check)

        self.days_worked = QDoubleSpinBox()
        self.days_worked.setRange(0, 31)
        self.days_worked.setEnabled(False)
        self.overtime_hours = QDoubleSpinBox()
        self.overtime_hours.setRange(0, 200)
        self.overtime_hours.setEnabled(False)
        self.days_absent = QDoubleSpinBox()
        self.days_absent.setRange(0, 31)
        self.days_absent.setEnabled(False)
        self.days_late = QDoubleSpinBox()
        self.days_late.setRange(0, 31)
        self.days_late.setEnabled(False)
        self.late_minutes = QDoubleSpinBox()
        self.late_minutes.setRange(0, 100000)
        self.late_minutes.setEnabled(False)
        self.undertime_minutes = QDoubleSpinBox()
        self.undertime_minutes.setRange(0, 100000)
        self.undertime_minutes.setEnabled(False)
        self.add_row("Days Worked*", self.days_worked)
        self.add_row("Overtime Hours", self.overtime_hours)
        self.add_row("Days Absent", self.days_absent)
        self.add_row("Days Late", self.days_late)
        self.add_row("Late (minutes)", self.late_minutes)
        self.add_row("Undertime (minutes)", self.undertime_minutes)

        self.attendance_note = QLabel("")
        self.attendance_note.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px;")
        self.attendance_note.setWordWrap(True)
        self.add_full_row(self.attendance_note)

        sep = QFrame()
        sep.setProperty("divider", "true")
        sep.setFixedHeight(1)
        self.add_full_row(sep)

        self.payment_method = QComboBox()
        self.payment_method.addItems(PAYMENT_METHOD_LABELS)
        self.add_row("Payment Method", self.payment_method)
        self.employee_combo.currentIndexChanged.connect(self._sync_payment_method)

        sep2 = QFrame()
        sep2.setProperty("divider", "true")
        sep2.setFixedHeight(1)
        self.add_full_row(sep2)

        self.add_full_row(QLabel("<b>Government Contributions</b> — auto-computed, not editable"))
        self.gov_preview_label = QLabel("Select an employee to see SSS / PhilHealth / Pag-IBIG amounts.")
        self.gov_preview_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        self.gov_preview_label.setWordWrap(True)
        self.add_full_row(self.gov_preview_label)

        self.add_full_row(QLabel("<b>Late / Absence / Undertime</b> — auto-computed from Attendance, not editable"))
        self.attendance_deduction_label = QLabel("")
        self.attendance_deduction_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        self.attendance_deduction_label.setWordWrap(True)
        self.add_full_row(self.attendance_deduction_label)

        self.holiday_label = QLabel("")
        self.holiday_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        self.holiday_label.setWordWrap(True)
        self.holiday_label.setVisible(False)
        self.add_full_row(self.holiday_label)

        self.allowance_checks = []
        manual_allowance_types = [at for at in allowance_types if not getattr(at, "auto_type", None)]
        if manual_allowance_types:
            self.add_full_row(QLabel("<b>Allowances</b>"))
            for at in manual_allowance_types:
                row = QWidget()
                rl = QHBoxLayout(row)
                rl.setContentsMargins(0, 0, 0, 0)
                cb = QCheckBox(at.type_name)
                amt = QDoubleSpinBox()
                amt.setRange(0, 1_000_000)
                amt.setPrefix("\u20b1 ")
                amt.setEnabled(False)
                cb.toggled.connect(amt.setEnabled)
                rl.addWidget(cb, 1)
                rl.addWidget(amt)
                self.add_full_row(row)
                self.allowance_checks.append((at.allowance_type_id, cb, amt))

        self.deduction_checks = []
        manual_deduction_types = [dt for dt in deduction_types if not dt.auto_type]
        if manual_deduction_types:
            self.add_full_row(QLabel("<b>Other Deductions</b> (cash advance, loan, etc.)"))
            for dt in manual_deduction_types:
                row = QWidget()
                rl = QHBoxLayout(row)
                rl.setContentsMargins(0, 0, 0, 0)
                cb = QCheckBox(dt.type_name)
                amt = QDoubleSpinBox()
                amt.setRange(0, 1_000_000)
                amt.setPrefix("\u20b1 ")
                amt.setEnabled(False)
                cb.toggled.connect(amt.setEnabled)
                rl.addWidget(cb, 1)
                rl.addWidget(amt)
                self.add_full_row(row)
                self.deduction_checks.append((dt.deduction_type_id, cb, amt))

        self.save_btn.setText("Process & Finalize")
        self._pull_attendance()

    # ------------------------------------------------------------------
    def _toggle_override(self, checked: bool):
        for w in (self.days_worked, self.overtime_hours, self.days_absent, self.days_late,
                  self.late_minutes, self.undertime_minutes):
            w.setEnabled(checked)
        if not checked:
            self._pull_attendance()

    def _pull_attendance(self):
        emp_id = self.employee_combo.currentData()
        period_id = self.period_combo.currentData()
        if not emp_id or not period_id:
            return
        db = get_db()
        with db.session() as s:
            period = s.get(PayPeriod, period_id)
            if not period:
                return
            summary = ats.compute_period_summary(s, emp_id, period.start_date, period.end_date)
        if not self.override_check.isChecked():
            self.days_worked.setValue(float(summary.days_worked))
            self.overtime_hours.setValue(float(summary.overtime_hours))
            self.days_absent.setValue(float(summary.days_absent))
            self.days_late.setValue(float(summary.days_late))
            self.late_minutes.setValue(float(summary.late_minutes_total))
            self.undertime_minutes.setValue(float(summary.undertime_minutes_total))
        if summary.records_found == 0:
            self.attendance_note.setText(
                "\u26A0 No attendance records found for this employee in this period — record "
                "attendance first, or check Override to enter figures manually."
            )
        else:
            self.attendance_note.setText(
                f"Pulled from {summary.records_found} attendance record(s) for this period."
            )
        self._sync_payment_method()
        self._update_gov_preview()
        self._update_attendance_deduction_preview()
        self._update_holiday_preview()

    def _sync_payment_method(self):
        emp = self._employees.get(self.employee_combo.currentData())
        if emp is not None:
            method = getattr(emp, "payment_method", "bank_transfer") or "bank_transfer"
            if method in PAYMENT_METHODS:
                self.payment_method.setCurrentIndex(PAYMENT_METHODS.index(method))

    def _update_gov_preview(self):
        emp_id = self.employee_combo.currentData()
        period_id = self.period_combo.currentData()
        if not emp_id or not period_id:
            return
        db = get_db()
        with db.session() as s:
            emp = s.get(Employee, emp_id)
            position = s.get(Position, emp.position_id) if emp else None
            period = s.get(PayPeriod, period_id)
            monthly_basic = Decimal(position.base_salary) if position else Decimal(0)
            period_days = gov_rates.period_days_between(period.start_date, period.end_date) if period else 30
            factor = gov_rates.period_proration_factor(period_days)
            contribs = gov_rates.compute_all_contributions(s, monthly_basic)
            has_number = {
                scheme: (emp is not None and gov_rates.employee_has_scheme_number(emp, scheme))
                for scheme in ("sss", "philhealth", "pagibig")
            }

        parts = []
        total = Decimal("0")
        any_computed = False
        for scheme in ("sss", "philhealth", "pagibig"):
            label = gov_rates.SCHEME_LABELS[scheme]
            if has_number[scheme]:
                amt = (contribs[scheme].employee_share * factor).quantize(Decimal("0.01"))
                total += amt
                any_computed = True
                parts.append(f"<span style='color:{theme.TEXT};'>{label}: <b>{format_currency(amt)}</b></span>")
            else:
                parts.append(f"<span style='color:{theme.WARNING};'>{label}: not computed \u2014 no {label} number on file</span>")

        joined = "   \u00b7   ".join(parts)
        if any_computed:
            self.gov_preview_label.setText(
                f"{joined}<br><span style='color:{theme.TEXT_MUTED};font-size:11px;'>"
                f"Total this period: {format_currency(total)} &middot; only contributions for numbers actually on file are deducted "
                f"&middot; period spans {period_days} day(s), prorated accordingly.</span>"
            )
        else:
            self.gov_preview_label.setText(
                f"<span style='color:{theme.WARNING};'>\u26A0 No government contributions will be deducted \u2014 this "
                f"employee has no SSS, PhilHealth, or Pag-IBIG number on file.</span><br>"
                f"<span style='color:{theme.TEXT_MUTED};font-size:11px;'>Add the relevant number(s) on the employee's "
                f"profile if contributions should be withheld.</span>"
            )

    def _update_attendance_deduction_preview(self):
        emp_id = self.employee_combo.currentData()
        period_id = self.period_combo.currentData()
        if not emp_id or not period_id:
            return
        db = get_db()
        with db.session() as s:
            emp = s.get(Employee, emp_id)
            position = s.get(Position, emp.position_id) if emp else None
        base_salary = Decimal(position.base_salary) if position else Decimal(0)
        daily_rate = (base_salary / Decimal(22)).quantize(Decimal("0.01"))
        minute_rate = daily_rate / Decimal(8) / Decimal(60)

        late_amt = (minute_rate * Decimal(str(self.late_minutes.value()))).quantize(Decimal("0.01"))
        undertime_amt = (minute_rate * Decimal(str(self.undertime_minutes.value()))).quantize(Decimal("0.01"))
        absence_amt = (daily_rate * Decimal(str(self.days_absent.value()))).quantize(Decimal("0.01"))
        total = late_amt + undertime_amt + absence_amt

        if total <= 0:
            self.attendance_deduction_label.setText(
                f"<span style='color:{theme.SUCCESS};'>No late, absence, or undertime deductions this period.</span>"
            )
            return
        parts = []
        if late_amt > 0:
            parts.append(f"Late: <b>{format_currency(late_amt)}</b> ({self.late_minutes.value():g} min \u00d7 {format_currency(minute_rate)}/min)")
        if absence_amt > 0:
            parts.append(f"Absence: <b>{format_currency(absence_amt)}</b> ({self.days_absent.value():g} day(s) \u00d7 {format_currency(daily_rate)}/day)")
        if undertime_amt > 0:
            parts.append(f"Undertime: <b>{format_currency(undertime_amt)}</b> ({self.undertime_minutes.value():g} min \u00d7 {format_currency(minute_rate)}/min)")
        self.attendance_deduction_label.setText(
            "   \u00b7   ".join(parts) + f"<br><span style='color:{theme.TEXT_MUTED};font-size:11px;'>"
            f"Total: {format_currency(total)}</span>"
        )

    def _update_holiday_preview(self):
        emp_id = self.employee_combo.currentData()
        period_id = self.period_combo.currentData()
        if not emp_id or not period_id:
            self.holiday_label.setVisible(False)
            return
        db = get_db()
        with db.session() as s:
            period = s.get(PayPeriod, period_id)
            if not period:
                self.holiday_label.setVisible(False)
                return
            adj = ats.compute_holiday_adjustment(s, emp_id, period.start_date, period.end_date)
        if not adj.holiday_notes:
            self.holiday_label.setVisible(False)
            return
        lines = "<br>".join(adj.holiday_notes)
        self.holiday_label.setText(f"<b>Holidays this period</b><br>{lines}")
        self.holiday_label.setVisible(True)

    # ------------------------------------------------------------------
    def get_allowances(self):
        return [(tid, Decimal(str(amt.value()))) for tid, cb, amt in self.allowance_checks if cb.isChecked() and amt.value() > 0]

    def get_deductions(self):
        return [(tid, Decimal(str(amt.value()))) for tid, cb, amt in self.deduction_checks if cb.isChecked() and amt.value() > 0]

    def get_payment_method(self) -> str:
        idx = self.payment_method.currentIndex()
        return PAYMENT_METHODS[idx] if idx >= 0 else "bank_transfer"

    def get_payment_detail(self) -> str:
        emp = self._employees.get(self.employee_combo.currentData())
        method = self.get_payment_method()
        default_method = getattr(emp, "payment_method", None) if emp else None
        if emp is not None and method == default_method:
            return getattr(emp, "payment_detail", method)
        return PAYMENT_METHOD_LABELS[PAYMENT_METHODS.index(method)]


class StatusUpdateDialog(BaseFormDialog):
    def __init__(self, parent, current_status: str):
        super().__init__("Update Payroll Status", parent=parent, width=420)
        self.status = QComboBox()
        self.status.addItems([s.title() for s in STATUS_OPTIONS])
        self.status.setCurrentText(current_status.title())
        self.add_row("New Status", self.status)
        self.save_btn.setText("Update Status")


class PayslipDialog(QDialog):
    def __init__(self, parent, html: str, payslip_data: Optional[PayslipData] = None):
        super().__init__(parent)
        self.payslip_data = payslip_data
        self.setWindowTitle("Payslip")
        self.resize(560, 700)
        lay = QVBoxLayout(self)
        self.view = QTextEdit()
        self.view.setReadOnly(True)
        # The payslip HTML is styled as a plain light document (dark text
        # on white, like a real printed payslip) — the app's global dark
        # theme would otherwise paint this QTextEdit's background dark
        # too, making the dark-on-white text unreadable. Force it light
        # regardless of theme.
        self.view.setStyleSheet(
            "QTextEdit { background-color: #ffffff; border: 1px solid #3a3350; border-radius: 8px; }"
        )
        self.view.setHtml(html)
        lay.addWidget(self.view, 1)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        pdf_btn = make_button("\U0001F4C4 Save Payslip as PDF", "primary")
        pdf_btn.setMinimumHeight(42)
        pdf_btn.clicked.connect(self._save_pdf)
        btn_row.addWidget(pdf_btn)
        lay.addLayout(btn_row)

    def _save_pdf(self):
        if not self.payslip_data:
            show_err(self, "Can't Export", "No payslip data available.")
            return
        default_name = f"Payslip_{self.payslip_data.employee_code}_{self.payslip_data.period_name}.pdf".replace(" ", "_").replace("/", "-")
        path, _ = QFileDialog.getSaveFileName(self, "Save Payslip as PDF", default_name, "PDF Files (*.pdf)")
        if not path:
            return
        try:
            generate_payslip_pdf(self.payslip_data, path)
        except Exception as e:
            show_err(self, "Export Failed", f"Could not generate the PDF:\n{e}")
            return
        show_info(self, "Saved", f"Payslip saved to:\n{path}")


def build_payslip_html(payroll, employee, department, position, period, allowances, deductions) -> str:
    allow_rows = "".join(
        f"<tr><td>{a.allowance_type.type_name}</td><td align='right'>{format_currency(a.amount)}</td></tr>"
        for a in allowances
    ) or "<tr><td colspan='2' style='color:#888'>No allowances</td></tr>"
    deduct_rows = "".join(
        f"<tr><td>{d.deduction_type.type_name}</td><td align='right'>{format_currency(d.amount)}</td></tr>"
        for d in deductions
    )
    if payroll.tax_withheld and Decimal(payroll.tax_withheld) > 0:
        deduct_rows += f"<tr><td>Withholding Tax</td><td align='right'>{format_currency(payroll.tax_withheld)}</td></tr>"
    deduct_rows = deduct_rows or "<tr><td colspan='2' style='color:#888'>No deductions</td></tr>"

    payment_label = {"bank_transfer": "Bank Transfer", "gcash": "GCash", "maya": "Maya",
                      "cash": "Cash", "check": "Check"}.get(payroll.payment_method_used or "", "\u2014")
    gross_total = Decimal(payroll.gross_pay) + Decimal(payroll.total_allowances)
    total_ded_with_tax = Decimal(payroll.total_deductions) + Decimal(payroll.tax_withheld)

    return f"""
    <div style="font-family: Segoe UI, Arial; color: #222; background: #ffffff; padding: 4px 2px;">
    <h2 style="color:#a020c0; margin-bottom:0;">PayrollPro Payslip</h2>
    <p style="color:#888; margin-top:2px;">{period.period_name} &middot; Pay Date: {format_date(period.pay_date)}</p>
    <hr>
    <table width="100%" cellspacing="4">
      <tr><td><b>Employee</b></td><td align="right">{employee.full_name} ({employee.employee_code})</td></tr>
      <tr><td><b>Department</b></td><td align="right">{department.department_name if department else ''}</td></tr>
      <tr><td><b>Position</b></td><td align="right">{position.position_title if position else ''}</td></tr>
      <tr><td><b>Payment Method</b></td><td align="right">{payment_label} &ndash; {payroll.payment_detail_used or ''}</td></tr>
      <tr><td><b>Status</b></td><td align="right">{payroll.payroll_status.title()}</td></tr>
    </table>
    <hr>
    <table width="100%" cellspacing="4">
      <tr><td><b>Days Worked</b></td><td align="right">{payroll.days_worked}</td></tr>
      <tr><td><b>Days Absent</b></td><td align="right">{payroll.days_absent}</td></tr>
      <tr><td><b>Days Late</b></td><td align="right">{payroll.days_late}</td></tr>
      <tr><td><b>Overtime Hours</b></td><td align="right">{payroll.overtime_hours}</td></tr>
      <tr><td><b>Daily Rate</b></td><td align="right">{format_currency(payroll.daily_rate)}</td></tr>
      <tr><td><b>Basic Pay</b></td><td align="right">{format_currency(payroll.basic_pay)}</td></tr>
      <tr><td><b>Overtime Pay</b></td><td align="right">{format_currency(payroll.overtime_pay)}</td></tr>
      <tr><td><b>Gross Pay</b></td><td align="right"><b>{format_currency(gross_total)}</b></td></tr>
    </table>
    <hr>
    <p><b>Allowances</b></p>
    <table width="100%" cellspacing="4">{allow_rows}
      <tr><td><b>Total Allowances</b></td><td align="right"><b>{format_currency(payroll.total_allowances)}</b></td></tr>
    </table>
    <p><b>Deductions</b></p>
    <table width="100%" cellspacing="4">{deduct_rows}
      <tr><td><b>Total Deductions</b></td><td align="right"><b>{format_currency(total_ded_with_tax)}</b></td></tr>
    </table>
    <hr>
    <table width="100%" cellspacing="4">
      <tr><td style="font-size:16px;"><b>NET PAY</b></td>
          <td align="right" style="font-size:18px; color:#0a0;"><b>{format_currency(payroll.net_pay)}</b></td></tr>
    </table>
    </div>
    """


def build_payslip_data(payroll, employee, department, position, period, allowances, deductions) -> PayslipData:
    payment_label = {"bank_transfer": "Bank Transfer", "gcash": "GCash", "maya": "Maya",
                      "cash": "Cash", "check": "Check"}.get(payroll.payment_method_used or "", "\u2014")
    return PayslipData(
        company_name=get_settings().mail.company_name,
        employee_name=employee.full_name, employee_code=employee.employee_code,
        department_name=department.department_name if department else "",
        position_title=position.position_title if position else "",
        period_name=period.period_name, pay_date=format_date(period.pay_date),
        payroll_status=payroll.payroll_status,
        days_worked=Decimal(payroll.days_worked), days_absent=Decimal(payroll.days_absent),
        days_late=Decimal(payroll.days_late), overtime_hours=Decimal(payroll.overtime_hours),
        daily_rate=Decimal(payroll.daily_rate), basic_pay=Decimal(payroll.basic_pay),
        overtime_pay=Decimal(payroll.overtime_pay), gross_pay=Decimal(payroll.gross_pay),
        earnings=[PayslipLine(a.allowance_type.type_name, Decimal(a.amount)) for a in allowances],
        deductions=[PayslipLine(d.deduction_type.type_name, Decimal(d.amount)) for d in deductions],
        tax_withheld=Decimal(payroll.tax_withheld), total_allowances=Decimal(payroll.total_allowances),
        total_deductions=Decimal(payroll.total_deductions), net_pay=Decimal(payroll.net_pay),
        payment_method_label=payment_label, payment_detail=payroll.payment_detail_used or "",
    )


class PayrollPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.period_filter = 0
        self.status_filter = ""

        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        header = SectionHeader("Payroll", "Process and manage employee payroll", "+ Process Payroll")
        header.action_btn.clicked.connect(self.open_process_dialog)
        lay.addWidget(header)

        filters = QHBoxLayout()
        self.period_combo = QComboBox()
        self.period_combo.addItem("All Periods", 0)
        self.period_combo.currentIndexChanged.connect(self._on_filter_change)
        filters.addWidget(self.period_combo)
        self.status_combo = QComboBox()
        self.status_combo.addItem("All Statuses", "")
        for st in STATUS_OPTIONS:
            self.status_combo.addItem(st.title(), st)
        self.status_combo.currentIndexChanged.connect(self._on_filter_change)
        filters.addWidget(self.status_combo)
        filters.addStretch()
        lay.addLayout(filters)

        self.table = DataTable(["Employee", "Period", "Gross Pay", "Net Pay", "Status", "Actions"])
        lay.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        db = get_db()
        with db.session() as s:
            from sqlalchemy import select
            q = (
                select(Payroll, Employee, PayPeriod)
                .join(Employee, Payroll.employee_id == Employee.employee_id)
                .join(PayPeriod, Payroll.period_id == PayPeriod.period_id)
                .order_by(Payroll.created_at.desc())
            )
            if self.period_filter:
                q = q.where(Payroll.period_id == self.period_filter)
            if self.status_filter:
                q = q.where(Payroll.payroll_status == self.status_filter)
            rows = s.execute(q).all()
            periods = pps.list_pay_periods(s)

        current_period = self.period_combo.currentData()
        self.period_combo.blockSignals(True)
        self.period_combo.clear()
        self.period_combo.addItem("All Periods", 0)
        for p in periods:
            self.period_combo.addItem(p.period_name, p.period_id)
        if current_period:
            idx = self.period_combo.findData(current_period)
            if idx >= 0:
                self.period_combo.setCurrentIndex(idx)
        self.period_combo.blockSignals(False)

        self.table.clear_rows()
        for payroll, emp, period in rows:
            r = self.table.add_row([
                f"{emp.full_name} ({emp.employee_code})", period.period_name,
                format_currency(payroll.gross_pay), format_currency(payroll.net_pay), "", None,
            ])
            self.table.set_widget(r, 4, Badge(payroll.payroll_status))
            actions = action_bar([
                ("\U0001F4C4", "ghost", lambda _, pid=payroll.payroll_id: self.view_payslip(pid), "View payslip"),
                ("\U0001F504", "ghost", lambda _, pid=payroll.payroll_id, st=payroll.payroll_status: self.update_status(pid, st), "Update status"),
                ("\U0001F5D1\uFE0F", "danger", lambda _, pid=payroll.payroll_id, st=payroll.payroll_status: self.delete(pid, st), "Delete payroll record"),
            ])
            self.table.set_widget(r, 5, actions)

    def _on_filter_change(self):
        self.period_filter = self.period_combo.currentData() or 0
        self.status_filter = self.status_combo.currentData() or ""
        self.refresh()

    # ------------------------------------------------------------------
    def open_process_dialog(self):
        db = get_db()
        with db.session() as s:
            from sqlalchemy import select
            emp_rows = s.execute(select(Employee).where(Employee.employment_status == "active")
                                  .order_by(Employee.first_name)).scalars().all()
            employees = [type("E", (), {
                "employee_id": e.employee_id, "full_name": e.full_name, "employee_code": e.employee_code,
                "payment_method": e.payment_method, "payment_detail": e.payment_detail,
            }) for e in emp_rows]
            periods = pps.list_pay_periods(s)
            allowance_types = rs.list_allowance_types(s, active_only=True)
            deduction_types = rs.list_deduction_types(s, active_only=True)

        if not employees:
            show_err(self, "No Employees", "Please add active employees first.")
            return
        if not periods:
            show_err(self, "No Pay Periods", "Please add a pay period first.")
            return

        dlg = ProcessPayrollDialog(self, employees, periods, allowance_types, deduction_types)
        dlg.save_btn.clicked.connect(lambda: self._submit_process(dlg))
        dlg.exec()

    def _submit_process(self, dlg: ProcessPayrollDialog):
        dlg.clear_error()
        db = get_db()
        with db.session() as s:
            result = pe.process_and_finalize_payroll(
                s, dlg.employee_combo.currentData(), dlg.period_combo.currentData(),
                Decimal(str(dlg.days_worked.value())), Decimal(str(dlg.overtime_hours.value())),
                current_session.user_id, dlg.get_allowances(), dlg.get_deductions(),
                days_absent=Decimal(str(dlg.days_absent.value())), days_late=Decimal(str(dlg.days_late.value())),
                late_minutes=Decimal(str(dlg.late_minutes.value())), undertime_minutes=Decimal(str(dlg.undertime_minutes.value())),
                payment_method_override=dlg.get_payment_method(), payment_detail_override=dlg.get_payment_detail(),
            )
        if not result.success:
            dlg.show_error(result.error)
            return
        dlg.accept()
        msg = f"Payroll processed successfully. Net Pay: {format_currency(result.extra.get('net_pay'))}"
        if not result.extra.get("notif_success"):
            msg += f"\n\nNote: employee notification email was not sent ({result.extra.get('notif_error')})."
        show_info(self, "Payroll Processed", msg)
        self.refresh()

    def view_payslip(self, payroll_id: int):
        db = get_db()
        with db.session() as s:
            payroll = s.get(Payroll, payroll_id)
            employee = s.get(Employee, payroll.employee_id)
            from database.models import Department, Position
            department = s.get(Department, employee.department_id)
            position = s.get(Position, employee.position_id)
            period = s.get(PayPeriod, payroll.period_id)
            from sqlalchemy import select
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

    def update_status(self, payroll_id: int, current_status: str):
        dlg = StatusUpdateDialog(self, current_status)

        def do_update():
            new_status = dlg.status.currentText().lower()
            db = get_db()
            with db.session() as s:
                result = pe.update_payroll_status(s, payroll_id, new_status, current_session.user_id)
            if not result.success:
                dlg.show_error(result.error)
                return
            dlg.accept()
            self.refresh()
        dlg.save_btn.clicked.connect(do_update)
        dlg.exec()

    def delete(self, payroll_id: int, status: str):
        if status == "paid":
            show_err(self, "Cannot Delete", "Paid payroll records cannot be deleted.")
            return
        if not confirm(self, "Delete Payroll Record?", "This cannot be undone.", danger=True):
            return
        db = get_db()
        with db.session() as s:
            result = pe.delete_payroll(s, payroll_id)
        if result.success:
            self.refresh()
        else:
            show_err(self, "Error", result.error)
