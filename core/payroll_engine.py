"""
core.payroll_engine
=======================
Exact re-implementation of the original MySQL stored procedures and
the admin/payroll.php action handlers, so payroll math is identical
byte-for-byte regardless of which database backend is active:

    sp_process_payroll   -> process_payroll()
    sp_finalize_payroll  -> finalize_payroll()
    trg_payroll_status_change -> update_payroll_status() calls
                                  core.audit.log_payroll_status_change()

The "Process Payroll" button in the original admin UI actually calls
sp_process_payroll, inserts allowance/deduction rows, THEN
immediately calls sp_finalize_payroll and fires an employee
notification — all in one request. That combined flow is
process_and_finalize_payroll() below.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

import core.attendance_service as attendance_service
import core.gov_rates as gov_rates
from core.audit import log_action, log_payroll_status_change
from database.models import (
    AllowanceType, DeductionType, Employee, PayPeriod, Payroll, PayrollAllowance,
    PayrollDeduction, Position, User,
)

TWO_PLACES = Decimal("0.01")


def _round2(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass
class PayrollResult:
    success: bool
    error: Optional[str] = None
    payroll_id: Optional[int] = None
    extra: Optional[dict] = None


def _get_employee_or_none(session: Session, employee_id: int) -> Optional[Employee]:
    return session.get(Employee, employee_id)


# ─────────────────────────────────────────────────────────────────────────
#  sp_process_payroll
# ─────────────────────────────────────────────────────────────────────────

def process_payroll(session: Session, employee_id: int, period_id: int,
                     days_worked: Optional[Decimal] = None, overtime_hours: Optional[Decimal] = None,
                     days_absent: Optional[Decimal] = None, days_late: Optional[Decimal] = None,
                     processed_by: Optional[int] = None,
                     late_minutes: Optional[Decimal] = None, undertime_minutes: Optional[Decimal] = None) -> PayrollResult:
    """Days worked / OT / absences / lateness default to whatever the
    Attendance log actually recorded for this employee across the pay
    period's date range — the whole point of the daily time-in/out
    system. Pass explicit numbers only when the admin has deliberately
    overridden them in the UI.

    Basic pay is based on the period's *standard business days*
    (Mon-Fri count from the actual calendar dates, adjusted for any
    unworked special holidays — see attendance_service.compute_holiday_
    adjustment) rather than only days actually attended. That full
    amount is what makes Late/Absence/Undertime deductions meaningful
    as their own visible line items instead of being silently baked
    into a smaller basic pay number."""
    emp = session.execute(
        select(Employee).where(Employee.employee_id == employee_id)
    ).scalar_one_or_none()
    if not emp:
        return PayrollResult(False, "Employee not found.")

    period = session.get(PayPeriod, period_id)
    if not period:
        return PayrollResult(False, "Pay period not found.")

    if days_worked is None or overtime_hours is None:
        summary = attendance_service.compute_period_summary(session, employee_id, period.start_date, period.end_date)
        days_worked = summary.days_worked
        overtime_hours = summary.overtime_hours
        days_absent = summary.days_absent if days_absent is None else days_absent
        days_late = summary.days_late if days_late is None else days_late
        late_minutes = summary.late_minutes_total if late_minutes is None else late_minutes
        undertime_minutes = summary.undertime_minutes_total if undertime_minutes is None else undertime_minutes

    position = session.get(Position, emp.position_id)
    base_salary = Decimal(position.base_salary) if position else Decimal(0)

    days_worked = Decimal(str(days_worked))
    overtime_hours = Decimal(str(overtime_hours))
    days_absent = Decimal(str(days_absent or 0))
    days_late = Decimal(str(days_late or 0))
    late_minutes = Decimal(str(late_minutes or 0))
    undertime_minutes = Decimal(str(undertime_minutes or 0))

    standard_days = Decimal(attendance_service.count_business_days(period.start_date, period.end_date))
    holiday_adj = attendance_service.compute_holiday_adjustment(session, employee_id, period.start_date, period.end_date)
    standard_days -= holiday_adj.special_unworked_weekdays  # "no work, no pay" special holidays

    daily_rate = _round2(base_salary / Decimal(22))
    basic_pay = _round2(daily_rate * standard_days)
    overtime_pay = _round2((daily_rate / Decimal(8)) * Decimal("1.25") * overtime_hours)
    gross_pay = _round2(basic_pay + overtime_pay)

    existing = session.execute(
        select(Payroll).where(Payroll.employee_id == employee_id, Payroll.period_id == period_id)
    ).scalar_one_or_none()

    now = datetime.now()
    if existing:
        existing.basic_pay = basic_pay
        existing.daily_rate = daily_rate
        existing.standard_days = standard_days
        existing.days_worked = days_worked
        existing.days_absent = days_absent
        existing.days_late = days_late
        existing.late_minutes = late_minutes
        existing.undertime_minutes = undertime_minutes
        existing.overtime_hours = overtime_hours
        existing.overtime_pay = overtime_pay
        existing.gross_pay = gross_pay
        existing.processed_by = processed_by
        existing.processed_at = now
        existing.payroll_status = "draft"
        session.flush()
        payroll_id = existing.payroll_id
    else:
        row = Payroll(
            employee_id=employee_id, period_id=period_id, basic_pay=basic_pay,
            daily_rate=daily_rate, standard_days=standard_days, days_worked=days_worked, days_absent=days_absent,
            days_late=days_late, late_minutes=late_minutes, undertime_minutes=undertime_minutes,
            overtime_hours=overtime_hours, overtime_pay=overtime_pay,
            gross_pay=gross_pay, processed_by=processed_by, processed_at=now,
            payroll_status="draft",
        )
        session.add(row)
        session.flush()
        payroll_id = row.payroll_id

    log_action(session, processed_by, "PROCESS_PAYROLL", "payroll", payroll_id, None,
               f"employee:{employee_id} period:{period_id}")
    return PayrollResult(True, payroll_id=payroll_id)


# ─────────────────────────────────────────────────────────────────────────
#  sp_finalize_payroll
# ─────────────────────────────────────────────────────────────────────────

def finalize_payroll(session: Session, payroll_id: int, admin_id: Optional[int],
                      payment_method_override: Optional[str] = None,
                      payment_detail_override: Optional[str] = None) -> PayrollResult:
    payroll = session.get(Payroll, payroll_id)
    if not payroll:
        return PayrollResult(False, "Payroll record not found.")

    emp = session.get(Employee, payroll.employee_id)
    position = session.get(Position, emp.position_id) if emp else None
    period = session.get(PayPeriod, payroll.period_id)
    monthly_basic = Decimal(position.base_salary) if position else Decimal(0)
    period_days = gov_rates.period_days_between(period.start_date, period.end_date) if period else 30
    daily_rate = Decimal(payroll.daily_rate)
    minute_rate = daily_rate / Decimal(8) / Decimal(60)

    # Wipe any previously auto-computed rows (gov't contributions, late/
    # absence/undertime deductions, holiday premiums) so a re-finalize
    # (e.g. after editing manual allowances) never doubles them up.
    auto_dt_ids = [row.deduction_type_id for row in session.execute(
        select(DeductionType).where(DeductionType.auto_type.isnot(None))
    ).scalars().all()]
    if auto_dt_ids:
        session.query(PayrollDeduction).filter(
            PayrollDeduction.payroll_id == payroll_id,
            PayrollDeduction.deduction_type_id.in_(auto_dt_ids),
        ).delete(synchronize_session=False)
    auto_at_ids = [row.allowance_type_id for row in session.execute(
        select(AllowanceType).where(AllowanceType.auto_type.isnot(None))
    ).scalars().all()]
    if auto_at_ids:
        session.query(PayrollAllowance).filter(
            PayrollAllowance.payroll_id == payroll_id,
            PayrollAllowance.allowance_type_id.in_(auto_at_ids),
        ).delete(synchronize_session=False)
    session.flush()

    # ---- Government contributions: only for schemes the employee is
    # actually registered under (has the number on file), prorated to
    # the period's *actual* calendar length rather than a period-type
    # label that might not match the real dates. ----
    factor = gov_rates.period_proration_factor(period_days)
    gov_deduction_total = Decimal("0")
    gov_breakdown: dict[str, dict] = {}
    for dt_row in session.execute(
        select(DeductionType).where(DeductionType.auto_type.in_(["sss", "philhealth", "pagibig"]),
                                     DeductionType.is_active == True)  # noqa: E712
    ).scalars().all():
        scheme = dt_row.auto_type
        has_number = emp is not None and gov_rates.employee_has_scheme_number(emp, scheme)
        if not has_number:
            gov_breakdown[scheme] = {"computed": False, "amount": Decimal("0"), "reason": "no number on file"}
            continue
        contrib = gov_rates.compute_contribution(session, scheme, monthly_basic)
        amount = _round2(contrib.employee_share * factor)
        if amount > 0:
            session.add(PayrollDeduction(payroll_id=payroll_id, deduction_type_id=dt_row.deduction_type_id, amount=amount))
            gov_deduction_total += amount
        gov_breakdown[scheme] = {"computed": True, "amount": amount, "reason": ""}

    # ---- Late / Absence / Undertime: computed from the employee's own
    # daily/minute rate and actual Attendance figures — never a flat
    # percentage guess (see the reference formulas in payroll_engine's
    # module docstring). ----
    attendance_deduction_total = Decimal("0")
    late_amt = _round2(minute_rate * Decimal(payroll.late_minutes))
    absence_amt = _round2(daily_rate * Decimal(payroll.days_absent))
    undertime_amt = _round2(minute_rate * Decimal(payroll.undertime_minutes))
    for auto_type, amount in (("late", late_amt), ("absence", absence_amt), ("undertime", undertime_amt)):
        if amount <= 0:
            continue
        dt_row = session.execute(
            select(DeductionType).where(DeductionType.auto_type == auto_type, DeductionType.is_active == True)  # noqa: E712
        ).scalar_one_or_none()
        if dt_row:
            session.add(PayrollDeduction(payroll_id=payroll_id, deduction_type_id=dt_row.deduction_type_id, amount=amount))
            attendance_deduction_total += amount

    # ---- Holiday premiums: +100% for a regular holiday actually
    # worked, +30% for a special (non-working) holiday actually worked.
    # Unworked special holidays are already excluded from basic pay's
    # standard_days in process_payroll(), so there's nothing to deduct
    # for those here — just nothing extra to add. ----
    holiday_premium_total = Decimal("0")
    if period is not None:
        holiday_adj = attendance_service.compute_holiday_adjustment(
            session, payroll.employee_id, period.start_date, period.end_date)
        for auto_type, days in (("regular_holiday_premium", holiday_adj.regular_worked_days),
                                 ("special_holiday_premium", holiday_adj.special_worked_days)):
            if days <= 0:
                continue
            rate = Decimal("1.0") if auto_type == "regular_holiday_premium" else Decimal("0.3")
            amount = _round2(daily_rate * rate * days)
            at_row = session.execute(
                select(AllowanceType).where(AllowanceType.auto_type == auto_type, AllowanceType.is_active == True)  # noqa: E712
            ).scalar_one_or_none()
            if at_row and amount > 0:
                session.add(PayrollAllowance(payroll_id=payroll_id, allowance_type_id=at_row.allowance_type_id, amount=amount))
                holiday_premium_total += amount
    session.flush()

    allow_rows = session.execute(
        select(PayrollAllowance).where(PayrollAllowance.payroll_id == payroll_id)
    ).scalars().all()
    deduct_rows = session.execute(
        select(PayrollDeduction).where(PayrollDeduction.payroll_id == payroll_id)
    ).scalars().all()

    v_gross = Decimal(payroll.gross_pay)  # basic + overtime, no allowances
    v_total_allow = sum((Decimal(a.amount) for a in allow_rows), Decimal(0))
    v_total_deduct = sum((Decimal(d.amount) for d in deduct_rows), Decimal(0))

    taxable_allow = Decimal("0")
    for a in allow_rows:
        at = session.get(AllowanceType, a.allowance_type_id)
        if at is not None and at.is_taxable:
            taxable_allow += Decimal(a.amount)

    taxable_income = v_gross + taxable_allow - gov_deduction_total
    v_tax = gov_rates.compute_withholding_tax(session, taxable_income, period_days)

    v_net = _round2(v_gross + v_total_allow - v_total_deduct - v_tax)

    payroll.total_allowances = _round2(v_total_allow)
    payroll.total_deductions = _round2(v_total_deduct)
    payroll.tax_withheld = v_tax
    payroll.net_pay = v_net
    payroll.payroll_status = "approved"
    if payment_method_override:
        payroll.payment_method_used = payment_method_override
        payroll.payment_detail_used = payment_detail_override or payment_method_override
    elif emp is not None:
        payroll.payment_method_used = emp.payment_method
        payroll.payment_detail_used = emp.payment_detail
    payroll.updated_at = datetime.now()
    session.flush()

    log_action(session, admin_id, "FINALIZE_PAYROLL", "payroll", payroll_id, None, f"net_pay:{v_net}")
    return PayrollResult(True, payroll_id=payroll_id, extra={
        "net_pay": v_net, "tax_withheld": v_tax, "gov_deductions": gov_deduction_total,
        "gov_breakdown": gov_breakdown,
    })


# ─────────────────────────────────────────────────────────────────────────
#  Combined "Process Payroll" admin action (process + allowances/
#  deductions + finalize + notify), matching admin/payroll.php exactly.
# ─────────────────────────────────────────────────────────────────────────

def process_and_finalize_payroll(
    session: Session,
    employee_id: int,
    period_id: int,
    days_worked: Optional[Decimal] = None,
    overtime_hours: Optional[Decimal] = None,
    processed_by: Optional[int] = None,
    allowances: Sequence[Tuple[int, Decimal]] = (),
    deductions: Sequence[Tuple[int, Decimal]] = (),
    days_absent: Optional[Decimal] = None,
    days_late: Optional[Decimal] = None,
    late_minutes: Optional[Decimal] = None,
    undertime_minutes: Optional[Decimal] = None,
    payment_method_override: Optional[str] = None,
    payment_detail_override: Optional[str] = None,
) -> PayrollResult:
    result = process_payroll(session, employee_id, period_id, days_worked, overtime_hours,
                              days_absent, days_late, processed_by, late_minutes, undertime_minutes)
    if not result.success:
        return result
    payroll_id = result.payroll_id

    # SSS/PhilHealth/Pag-IBIG/Late/Absence/Undertime deductions and
    # Holiday premium allowances are all computed inside finalize_payroll
    # — never let a stray manual entry for one of those slip in here too.
    auto_dt_ids = {row.deduction_type_id for row in session.execute(
        select(DeductionType).where(DeductionType.auto_type.isnot(None))
    ).scalars().all()}
    auto_at_ids = {row.allowance_type_id for row in session.execute(
        select(AllowanceType).where(AllowanceType.auto_type.isnot(None))
    ).scalars().all()}

    # Replace allowance/deduction rows (mirrors DELETE-then-INSERT in payroll.php)
    session.query(PayrollAllowance).filter(PayrollAllowance.payroll_id == payroll_id).delete()
    session.query(PayrollDeduction).filter(PayrollDeduction.payroll_id == payroll_id).delete()
    for at_id, amt in allowances:
        amt = Decimal(str(amt))
        if at_id and amt > 0 and at_id not in auto_at_ids:
            session.add(PayrollAllowance(payroll_id=payroll_id, allowance_type_id=at_id, amount=amt))
    for dt_id, amt in deductions:
        amt = Decimal(str(amt))
        if dt_id and amt > 0 and dt_id not in auto_dt_ids:
            session.add(PayrollDeduction(payroll_id=payroll_id, deduction_type_id=dt_id, amount=amt))
    session.flush()

    fin = finalize_payroll(session, payroll_id, processed_by,
                            payment_method_override=payment_method_override,
                            payment_detail_override=payment_detail_override)
    if not fin.success:
        return fin

    # Notify employee (best-effort — failures never block the payroll operation)
    from core.payroll_notify import notify_payroll_generated
    notif = notify_payroll_generated(session, payroll_id)
    return PayrollResult(True, payroll_id=payroll_id, extra={
        "net_pay": fin.extra.get("net_pay") if fin.extra else None,
        "notif_success": notif.success,
        "notif_error": notif.error,
    })


# ─────────────────────────────────────────────────────────────────────────
#  Status update (admin/payroll.php action=update_status)
# ─────────────────────────────────────────────────────────────────────────

ALLOWED_STATUSES = ("draft", "approved", "paid", "cancelled")


def update_payroll_status(session: Session, payroll_id: int, new_status: str,
                           admin_id: Optional[int]) -> PayrollResult:
    if new_status not in ALLOWED_STATUSES:
        return PayrollResult(False, "Invalid status.")
    payroll = session.get(Payroll, payroll_id)
    if not payroll:
        return PayrollResult(False, "Payroll record not found.")

    old_status = payroll.payroll_status
    old_net = Decimal(payroll.net_pay)

    payroll.payroll_status = new_status
    payroll.updated_at = datetime.now()
    session.flush()

    log_action(session, admin_id, "UPDATE_PAYROLL_STATUS", "payroll", payroll_id, None, new_status)
    log_payroll_status_change(session, payroll_id, old_status, old_net, new_status, Decimal(payroll.net_pay))

    from core.payroll_notify import notify_payroll_status
    notif = notify_payroll_status(session, payroll_id, new_status)
    return PayrollResult(True, payroll_id=payroll_id, extra={
        "notif_success": notif.success, "notif_error": notif.error, "notif_skipped": notif.skipped,
    })


def delete_payroll(session: Session, payroll_id: int) -> PayrollResult:
    payroll = session.get(Payroll, payroll_id)
    if not payroll:
        return PayrollResult(False, "Payroll record not found.")
    if payroll.payroll_status == "paid":
        return PayrollResult(False, "Cannot delete a paid payroll record.")
    session.delete(payroll)
    session.flush()
    return PayrollResult(True)
