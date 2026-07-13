"""
core.audit_service
======================
Audit log listing with search/filter/stats, exact port of
admin/audit_log.php.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, func, or_, desc
from sqlalchemy.orm import Session

from database.models import AuditLog, User


@dataclass
class AuditLogRow:
    log_id: int
    action: str
    table_affected: Optional[str]
    record_id: Optional[int]
    old_value: Optional[str]
    new_value: Optional[str]
    details: Optional[str]
    logged_at: datetime
    username: Optional[str]
    role: Optional[str]


def list_audit_logs(session: Session, search: str = "", filter_action: str = "",
                     page: int = 1, per_page: int = 25) -> tuple[list[AuditLogRow], int]:
    q = select(AuditLog, User.username, User.role).outerjoin(User, AuditLog.user_id == User.user_id)
    if search:
        like = f"%{search}%"
        q = q.where(or_(AuditLog.action.like(like), User.username.like(like), AuditLog.new_value.like(like)))
    if filter_action:
        q = q.where(AuditLog.action == filter_action)

    count_q = select(func.count()).select_from(q.order_by(None).subquery())
    total = session.execute(count_q).scalar_one()

    q = q.order_by(desc(AuditLog.logged_at)).offset((page - 1) * per_page).limit(per_page)
    rows = [
        AuditLogRow(log.log_id, log.action, log.table_affected, log.record_id, log.old_value,
                    log.new_value, log.details, log.logged_at, uname, role)
        for log, uname, role in session.execute(q).all()
    ]
    return rows, total


def list_distinct_actions(session: Session) -> list[str]:
    return [a for (a,) in session.execute(select(AuditLog.action).distinct().order_by(AuditLog.action)).all()]


def audit_stats(session: Session) -> dict:
    today = date.today()
    total = session.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    today_count = session.execute(
        select(func.count()).select_from(AuditLog).where(func.date(AuditLog.logged_at) == today)
    ).scalar_one()
    fail_count = session.execute(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "FAILED_LOGIN", func.date(AuditLog.logged_at) == today
        )
    ).scalar_one()
    reset_count = session.execute(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.action.in_(["RESET_PASSWORD", "PASSWORD_RESET_REQ"])
        )
    ).scalar_one()
    return {"total": total, "today": today_count, "failed_today": fail_count, "resets": reset_count}
