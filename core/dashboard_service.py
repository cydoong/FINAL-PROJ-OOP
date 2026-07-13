"""
core.dashboard_service
==========================
Aggregate queries backing the Admin Dashboard and Employee Dashboard,
precisely mirroring admin/dashboard.php and user/dashboard.php.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from database.models import (
    AuditLog, Department, Employee, PayPeriod, Payroll, Position, User,
)


# ─────────────────────────────────────────────────────────────────────────
#  Admin dashboard
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class AdminDashboardData:
    total_employees: int = 0
    total_departments: int = 0
    open_periods: int = 0
    draft_payroll: int = 0
    latest_paid: Optional[dict] = None
    trend: list = field(default_factory=list)
    dept_breakdown: list = field(default_factory=list)
    recent_payroll: list = field(default_factory=list)
    upcoming_periods: list = field(default_factory=list)
    recent_audit: list = field(default_factory=list)
    reset_alerts: list = field(default_factory=list)
    dept_pay: list = field(default_factory=list)


def get_admin_dashboard(session: Session) -> AdminDashboardData:
    d = AdminDashboardData()

    d.total_employees = session.execute(
        select(func.count()).select_from(Employee).where(Employee.employment_status == "active")
    ).scalar_one()
    d.total_departments = session.execute(
        select(func.count()).select_from(Department).where(Department.is_active == True)  # noqa: E712
    ).scalar_one()
    d.open_periods = session.execute(
        select(func.count()).select_from(PayPeriod).where(PayPeriod.status == "open")
    ).scalar_one()
    d.draft_payroll = session.execute(
        select(func.count()).select_from(Payroll).where(Payroll.payroll_status == "draft")
    ).scalar_one()

    # Latest fully-paid period
    latest_row = session.execute(
        select(PayPeriod.period_name,
               func.sum(Payroll.net_pay), func.sum(Payroll.gross_pay), func.count(Payroll.payroll_id))
        .join(Payroll, Payroll.period_id == PayPeriod.period_id)
        .where(Payroll.payroll_status == "paid")
        .group_by(Payroll.period_id)
        .order_by(desc(PayPeriod.end_date))
        .limit(1)
    ).first()
    if latest_row:
        d.latest_paid = {
            "period_name": latest_row[0], "total_net": float(latest_row[1] or 0),
            "total_gross": float(latest_row[2] or 0), "emp_count": latest_row[3],
        }

    # 6-period trend (paid+approved), oldest -> newest
    trend_rows = session.execute(
        select(PayPeriod.period_name, func.sum(Payroll.net_pay), func.sum(Payroll.gross_pay), func.count())
        .join(Payroll, Payroll.period_id == PayPeriod.period_id)
        .where(Payroll.payroll_status.in_(["paid", "approved"]))
        .group_by(Payroll.period_id)
        .order_by(desc(PayPeriod.start_date))
        .limit(6)
    ).all()
    d.trend = list(reversed([
        {"period_name": r[0], "net": float(r[1] or 0), "gross": float(r[2] or 0), "count": r[3]}
        for r in trend_rows
    ]))

    # Department headcount + avg salary
    depts = session.execute(select(Department).where(Department.is_active == True)).scalars().all()  # noqa: E712
    dept_breakdown = []
    for dep in depts:
        emp_count = session.execute(
            select(func.count()).select_from(Employee).where(
                Employee.department_id == dep.department_id, Employee.employment_status == "active"
            )
        ).scalar_one()
        avg_salary = session.execute(
            select(func.avg(Position.base_salary)).select_from(Employee)
            .join(Position, Employee.position_id == Position.position_id)
            .where(Employee.department_id == dep.department_id, Employee.employment_status == "active")
        ).scalar_one()
        dept_breakdown.append({
            "department_name": dep.department_name, "emp_count": emp_count,
            "avg_salary": float(avg_salary) if avg_salary else 0.0,
        })
    d.dept_breakdown = sorted(dept_breakdown, key=lambda x: -x["emp_count"])[:6]

    # Recent payroll
    recent = session.execute(
        select(Payroll, Employee, Department, PayPeriod)
        .join(Employee, Payroll.employee_id == Employee.employee_id)
        .join(Department, Employee.department_id == Department.department_id)
        .join(PayPeriod, Payroll.period_id == PayPeriod.period_id)
        .order_by(desc(Payroll.created_at)).limit(8)
    ).all()
    d.recent_payroll = [
        {"payroll_id": pr.payroll_id, "status": pr.payroll_status, "net_pay": float(pr.net_pay),
         "gross_pay": float(pr.gross_pay), "emp_name": emp.full_name, "employee_code": emp.employee_code,
         "department_name": dept.department_name, "period_name": pp.period_name}
        for pr, emp, dept, pp in recent
    ]

    d.upcoming_periods = list(session.execute(
        select(PayPeriod).where(PayPeriod.status == "open").order_by(PayPeriod.pay_date.asc()).limit(4)
    ).scalars().all())

    audit_rows = session.execute(
        select(AuditLog.action, AuditLog.logged_at, User.username, User.role)
        .outerjoin(User, AuditLog.user_id == User.user_id)
        .order_by(desc(AuditLog.logged_at)).limit(8)
    ).all()
    d.recent_audit = [{"action": a, "logged_at": t, "username": u, "role": r} for a, t, u, r in audit_rows]

    reset_rows = session.execute(
        select(User.username, Employee.first_name, Employee.last_name)
        .join(Employee, Employee.user_id == User.user_id)
        .where(User.reset_requested == True)  # noqa: E712
    ).all()
    d.reset_alerts = [{"username": u, "name": f"{fn} {ln}"} for u, fn, ln in reset_rows]

    dept_pay_rows = session.execute(
        select(Department.department_name, func.sum(Payroll.net_pay))
        .select_from(Payroll)
        .join(Employee, Payroll.employee_id == Employee.employee_id)
        .join(Department, Employee.department_id == Department.department_id)
        .where(Payroll.payroll_status == "paid")
        .group_by(Department.department_id)
        .order_by(desc(func.sum(Payroll.net_pay))).limit(6)
    ).all()
    d.dept_pay = [{"department_name": n, "total": float(t or 0)} for n, t in dept_pay_rows]

    return d


# ─────────────────────────────────────────────────────────────────────────
#  Employee dashboard
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class EmployeeDashboardData:
    employee: Optional[Employee] = None
    department_name: str = ""
    position_title: str = ""
    base_salary: float = 0.0
    employment_type: str = ""
    total_pay_runs: int = 0
    total_paid: float = 0.0
    ytd_net: float = 0.0
    latest_pay: Optional[dict] = None
    recent_pays: list = field(default_factory=list)


def get_employee_dashboard(session: Session, employee_id: int) -> EmployeeDashboardData:
    d = EmployeeDashboardData()
    emp = session.get(Employee, employee_id)
    if not emp:
        return d
    d.employee = emp
    dept = session.get(Department, emp.department_id)
    pos = session.get(Position, emp.position_id)
    d.department_name = dept.department_name if dept else ""
    d.position_title = pos.position_title if pos else ""
    d.base_salary = float(pos.base_salary) if pos else 0.0
    d.employment_type = pos.employment_type if pos else ""

    total_row = session.execute(
        select(func.count(), func.coalesce(func.sum(Payroll.net_pay), 0))
        .where(Payroll.employee_id == employee_id, Payroll.payroll_status.in_(["paid", "approved"]))
    ).first()
    d.total_pay_runs, d.total_paid = total_row[0], float(total_row[1])

    latest = session.execute(
        select(Payroll, PayPeriod)
        .join(PayPeriod, Payroll.period_id == PayPeriod.period_id)
        .where(Payroll.employee_id == employee_id, Payroll.payroll_status.in_(["paid", "approved"]))
        .order_by(desc(PayPeriod.pay_date)).limit(1)
    ).first()
    if latest:
        pr, pp = latest
        d.latest_pay = {"net_pay": float(pr.net_pay), "gross_pay": float(pr.gross_pay),
                         "period_name": pp.period_name, "pay_date": pp.pay_date}

    # Year-to-date: use a plain date-range filter (Jan 1 -> Dec 31 of the
    # current year) instead of strftime()/YEAR(), so this works
    # identically on SQLite and MySQL.
    current_year = datetime.now().year
    year_start = date(current_year, 1, 1)
    year_end = date(current_year, 12, 31)
    ytd = session.execute(
        select(func.coalesce(func.sum(Payroll.net_pay), 0))
        .join(PayPeriod, Payroll.period_id == PayPeriod.period_id)
        .where(Payroll.employee_id == employee_id, Payroll.payroll_status.in_(["paid", "approved"]),
               PayPeriod.pay_date >= year_start, PayPeriod.pay_date <= year_end)
    ).scalar_one()
    d.ytd_net = float(ytd or 0)

    recent = session.execute(
        select(Payroll, PayPeriod)
        .join(PayPeriod, Payroll.period_id == PayPeriod.period_id)
        .where(Payroll.employee_id == employee_id)
        .order_by(desc(PayPeriod.pay_date)).limit(5)
    ).all()
    d.recent_pays = [
        {"payroll_id": pr.payroll_id, "period_name": pp.period_name, "pay_date": pp.pay_date,
         "gross_pay": float(pr.gross_pay), "net_pay": float(pr.net_pay), "status": pr.payroll_status}
        for pr, pp in recent
    ]
    return d
