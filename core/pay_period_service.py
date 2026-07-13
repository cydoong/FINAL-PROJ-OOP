"""
core.pay_period_service
===========================
CRUD for pay periods, mirroring admin/pay_periods.php: duplicate-name
guard on add, and a delete guard so a period with existing payroll
records can't be removed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from database.models import PayPeriod, Payroll


@dataclass
class ServiceResult:
    success: bool
    error: Optional[str] = None
    data: Optional[dict] = None


def add_pay_period(session: Session, name: str, period_type: str, start_date: date, end_date: date,
                    pay_date: date, status: str, admin_id: Optional[int]) -> ServiceResult:
    name = (name or "").strip()
    if session.execute(select(PayPeriod.period_id).where(PayPeriod.period_name == name)).first():
        return ServiceResult(False, f'A pay period named "{name}" already exists.')
    row = PayPeriod(period_name=name, period_type=period_type, start_date=start_date, end_date=end_date,
                     pay_date=pay_date, status=status, created_by=admin_id)
    session.add(row)
    session.flush()
    return ServiceResult(True, data={"period_id": row.period_id})


def edit_pay_period(session: Session, period_id: int, name: str, period_type: str, start_date: date,
                     end_date: date, pay_date: date, status: str) -> ServiceResult:
    row = session.get(PayPeriod, period_id)
    if not row:
        return ServiceResult(False, "Pay period not found.")
    row.period_name = name
    row.period_type = period_type
    row.start_date = start_date
    row.end_date = end_date
    row.pay_date = pay_date
    row.status = status
    session.flush()
    return ServiceResult(True)


def delete_pay_period(session: Session, period_id: int) -> ServiceResult:
    count = session.execute(
        select(func.count()).select_from(Payroll).where(Payroll.period_id == period_id)
    ).scalar_one()
    if count > 0:
        return ServiceResult(False, "Cannot delete period with existing payroll records.")
    row = session.get(PayPeriod, period_id)
    if row:
        session.delete(row)
        session.flush()
    return ServiceResult(True)


@dataclass
class PayPeriodRow:
    period_id: int
    period_name: str
    period_type: str
    start_date: date
    end_date: date
    pay_date: date
    status: str
    payroll_count: int
    total_net: float


def list_pay_periods(session: Session) -> list[PayPeriodRow]:
    periods = session.execute(select(PayPeriod).order_by(PayPeriod.start_date.desc())).scalars().all()
    rows = []
    for p in periods:
        payrolls = session.execute(
            select(Payroll).where(Payroll.period_id == p.period_id, Payroll.payroll_status != "cancelled")
        ).scalars().all()
        total_net = sum((float(pr.net_pay) for pr in payrolls), 0.0)
        rows.append(PayPeriodRow(p.period_id, p.period_name, p.period_type, p.start_date, p.end_date,
                                  p.pay_date, p.status, len(payrolls), total_net))
    return rows
