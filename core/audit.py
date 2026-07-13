"""
core.audit
============
Equivalent of `log_action()` in the original includes/db.php, plus
explicit Python re-implementations of the two MySQL triggers that
used to fire automatically:

    trg_employee_status_change  -> log_employee_status_change()
    trg_payroll_status_change   -> log_payroll_status_change()

Both are called explicitly by the relevant service functions right
after a status field changes, so behaviour is identical whether the
app is running against SQLite or MySQL.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from core.utils import local_ip
from database.models import AuditLog, User


def log_action(
    session: Session,
    user_id: Optional[int],
    action: str,
    table: Optional[str] = None,
    record_id: Optional[int] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    ip: Optional[str] = None,
) -> None:
    """Insert an audit_logs row. Never raises — a broken audit log
    should never take down the feature that triggered it."""
    try:
        safe_uid = None
        if user_id:
            exists = session.get(User, user_id)
            safe_uid = user_id if exists else None
        session.add(AuditLog(
            user_id=safe_uid,
            action=action,
            table_affected=table,
            record_id=record_id,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip or local_ip(),
        ))
        session.flush()
    except Exception:  # noqa: BLE001
        # Mirror the PHP behaviour: a logging failure must never break
        # the calling feature.
        pass


def log_employee_status_change(session: Session, employee_id: int, old_status: str, new_status: str) -> None:
    if old_status == new_status:
        return
    log_action(session, None, "EMPLOYEE_STATUS_CHANGE", "employees", employee_id, old_status, new_status)


def log_payroll_status_change(session: Session, payroll_id: int, old_status: str, old_net,
                               new_status: str, new_net) -> None:
    if old_status == new_status:
        return
    log_action(
        session, None, "PAYROLL_STATUS_CHANGE", "payroll", payroll_id,
        f"status:{old_status} net:{old_net:.2f}",
        f"status:{new_status} net:{new_net:.2f}",
    )
