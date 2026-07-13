"""
core.reports_service
========================
The four payroll reports + overall totals, exact port of
admin/reports.php: summary by period, employee history, deduction
summary, and department report — all filtered by pay-date range.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from database.models import (
    DeductionType, Department, Employee, PayPeriod, Payroll, PayrollDeduction, Position,
)


@dataclass
class ReportsData:
    payroll_summary: list = field(default_factory=list)
    emp_history: list = field(default_factory=list)
    deduct_summary: list = field(default_factory=list)
    dept_report: list = field(default_factory=list)
    totals: dict = field(default_factory=dict)


def get_reports(session: Session, start: date, end: date) -> ReportsData:
    r = ReportsData()

    # Report 1: Payroll summary by period
    rows = session.execute(
        select(PayPeriod.period_name, PayPeriod.pay_date, func.count(Payroll.payroll_id),
               func.sum(Payroll.gross_pay), func.sum(Payroll.total_allowances),
               func.sum(Payroll.total_deductions), func.sum(Payroll.net_pay),
               func.avg(Payroll.net_pay), func.max(Payroll.net_pay), func.min(Payroll.net_pay))
        .join(Payroll, Payroll.period_id == PayPeriod.period_id)
        .where(Payroll.payroll_status != "cancelled", PayPeriod.pay_date >= start, PayPeriod.pay_date <= end)
        .group_by(Payroll.period_id)
        .order_by(desc(PayPeriod.start_date))
    ).all()
    r.payroll_summary = [
        {"period_name": a, "pay_date": b, "emp_count": c, "total_gross": float(dd or 0),
         "total_allow": float(e or 0), "total_deduct": float(f or 0), "total_net": float(g or 0),
         "avg_net": float(h or 0), "max_net": float(i or 0), "min_net": float(j or 0)}
        for a, b, c, dd, e, f, g, h, i, j in rows
    ]

    # Report 2: Employee payroll history
    rows = session.execute(
        select(Employee.first_name, Employee.last_name, Employee.employee_code,
               Department.department_name, Position.position_title,
               func.count(Payroll.payroll_id), func.sum(Payroll.gross_pay),
               func.sum(Payroll.net_pay), func.avg(Payroll.net_pay))
        .select_from(Payroll)
        .join(Employee, Payroll.employee_id == Employee.employee_id)
        .join(Department, Employee.department_id == Department.department_id)
        .join(Position, Employee.position_id == Position.position_id)
        .join(PayPeriod, Payroll.period_id == PayPeriod.period_id)
        .where(Payroll.payroll_status != "cancelled", PayPeriod.pay_date >= start, PayPeriod.pay_date <= end)
        .group_by(Employee.employee_id)
        .order_by(desc(func.sum(Payroll.net_pay)))
    ).all()
    r.emp_history = [
        {"full_name": f"{fn} {ln}", "employee_code": code, "department_name": dept, "position_title": pos,
         "pay_count": cnt, "total_gross": float(tg or 0), "total_net": float(tn or 0), "avg_net": float(av or 0)}
        for fn, ln, code, dept, pos, cnt, tg, tn, av in rows
    ]

    # Report 3: Deduction summary
    rows = session.execute(
        select(DeductionType.type_name, DeductionType.is_mandatory, func.count(PayrollDeduction.pd_id),
               func.sum(PayrollDeduction.amount), func.avg(PayrollDeduction.amount))
        .select_from(PayrollDeduction)
        .join(DeductionType, PayrollDeduction.deduction_type_id == DeductionType.deduction_type_id)
        .join(Payroll, PayrollDeduction.payroll_id == Payroll.payroll_id)
        .join(PayPeriod, Payroll.period_id == PayPeriod.period_id)
        .where(Payroll.payroll_status != "cancelled", PayPeriod.pay_date >= start, PayPeriod.pay_date <= end)
        .group_by(DeductionType.deduction_type_id)
        .order_by(desc(func.sum(PayrollDeduction.amount)))
    ).all()
    r.deduct_summary = [
        {"type_name": n, "is_mandatory": m, "times_applied": c, "total_amount": float(t or 0), "avg_amount": float(av or 0)}
        for n, m, c, t, av in rows
    ]

    # Report 4: Department payroll
    rows = session.execute(
        select(Department.department_name, func.count(func.distinct(Employee.employee_id)),
               func.sum(Payroll.gross_pay), func.sum(Payroll.total_deductions),
               func.sum(Payroll.net_pay), func.avg(Payroll.net_pay), func.max(Payroll.net_pay))
        .select_from(Payroll)
        .join(Employee, Payroll.employee_id == Employee.employee_id)
        .join(Department, Employee.department_id == Department.department_id)
        .join(PayPeriod, Payroll.period_id == PayPeriod.period_id)
        .where(Payroll.payroll_status != "cancelled", PayPeriod.pay_date >= start, PayPeriod.pay_date <= end)
        .group_by(Department.department_id)
        .order_by(desc(func.sum(Payroll.net_pay)))
    ).all()
    r.dept_report = [
        {"department_name": n, "emp_count": c, "total_gross": float(tg or 0), "total_deduct": float(td or 0),
         "total_net": float(tn or 0), "avg_net": float(av or 0), "max_net": float(mx or 0)}
        for n, c, tg, td, tn, av, mx in rows
    ]

    # Overall totals
    totals_row = session.execute(
        select(func.count(Payroll.payroll_id), func.sum(Payroll.gross_pay), func.sum(Payroll.net_pay),
               func.sum(Payroll.total_deductions), func.avg(Payroll.net_pay),
               func.max(Payroll.net_pay), func.min(Payroll.net_pay))
        .select_from(Payroll)
        .join(PayPeriod, Payroll.period_id == PayPeriod.period_id)
        .where(Payroll.payroll_status != "cancelled", PayPeriod.pay_date >= start, PayPeriod.pay_date <= end)
    ).first()
    if totals_row:
        tr, gg, gn, gd, av, mx, mn = totals_row
        r.totals = {
            "total_records": tr or 0, "grand_gross": float(gg or 0), "grand_net": float(gn or 0),
            "grand_deduct": float(gd or 0), "avg_net": float(av or 0),
            "max_net": float(mx or 0), "min_net": float(mn or 0),
        }
    return r
