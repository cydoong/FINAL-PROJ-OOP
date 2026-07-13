"""
core.payroll_notify
=======================
Port of the "PAYROLL NOTIFICATIONS" section of includes/notify.php:
get_employee_contact(), notify_payroll_generated(), notify_payroll_status().

Kept in its own module (separate from core.payroll_engine) purely to
avoid a circular import between the engine and the notifications
module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from core.notifications import (
    notify_send_email, payroll_generated_email_html, payroll_status_email_html, SendResult,
)
from database.models import Employee, PayPeriod, Payroll, User


@dataclass
class EmployeeContact:
    employee_id: int
    user_id: Optional[int]
    full_name: str
    email: Optional[str]
    phone: Optional[str]


def get_employee_contact(session: Session, employee_id: int) -> Optional[EmployeeContact]:
    emp = session.get(Employee, employee_id)
    if not emp:
        return None
    user = session.get(User, emp.user_id) if emp.user_id else None
    email = (user.auth_email if user and user.auth_email else None) or emp.email or None
    phone = (user.auth_phone if user and user.auth_phone else None) or emp.phone or None
    return EmployeeContact(
        employee_id=emp.employee_id,
        user_id=user.user_id if user else None,
        full_name=emp.full_name,
        email=email,
        phone=phone,
    )


def notify_payroll_generated(session: Session, payroll_id: int) -> SendResult:
    payroll = session.get(Payroll, payroll_id)
    if not payroll:
        return SendResult(False, "Payroll record not found.")
    period = session.get(PayPeriod, payroll.period_id)

    contact = get_employee_contact(session, payroll.employee_id)
    if not contact:
        return SendResult(False, "Employee record not found.")
    if not contact.email:
        return SendResult(False, "No email on file for this employee.")

    html = payroll_generated_email_html(
        contact.full_name, period.period_name if period else "", period.pay_date if period else None,
        payroll.net_pay, payroll.payroll_status,
    )
    return notify_send_email(
        session, contact.email, contact.full_name,
        f"Payslip Generated \u2014 {period.period_name if period else ''}", html, "",
        payroll.employee_id, "payroll_generated", contact.user_id,
    )


def notify_payroll_status(session: Session, payroll_id: int, new_status: str) -> SendResult:
    if new_status == "draft":
        return SendResult(True, skipped=True)

    payroll = session.get(Payroll, payroll_id)
    if not payroll:
        return SendResult(False, "Payroll record not found.")
    period = session.get(PayPeriod, payroll.period_id)

    contact = get_employee_contact(session, payroll.employee_id)
    if not contact:
        return SendResult(False, "Employee record not found.")
    if not contact.email:
        return SendResult(False, "No email on file for this employee.")

    html = payroll_status_email_html(
        contact.full_name, period.period_name if period else "", period.pay_date if period else None,
        payroll.net_pay, new_status, payroll.remarks or "",
    )
    if html is None:
        return SendResult(True, skipped=True)

    return notify_send_email(
        session, contact.email, contact.full_name,
        f"{new_status.title()} \u2014 {period.period_name if period else ''}", html, "",
        payroll.employee_id, f"payroll_{new_status}", contact.user_id,
    )
