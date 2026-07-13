"""
core.notification_service
=============================
Listing/stats for the notification_log table, backing the admin
Notifications & Diagnostics page (admin/notifications.php).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from database.models import NotificationLog


@dataclass
class NotificationRow:
    log_id: int
    channel: str
    notif_type: str
    recipient: str
    subject: Optional[str]
    status: str
    error_message: Optional[str]
    created_at: datetime


def list_notifications(session: Session, channel: str = "", status: str = "",
                        page: int = 1, per_page: int = 25) -> tuple[list[NotificationRow], int]:
    q = select(NotificationLog)
    if channel:
        q = q.where(NotificationLog.channel == channel)
    if status:
        q = q.where(NotificationLog.status == status)

    count_q = select(func.count()).select_from(q.order_by(None).subquery())
    total = session.execute(count_q).scalar_one()

    q = q.order_by(desc(NotificationLog.created_at)).offset((page - 1) * per_page).limit(per_page)
    rows = [
        NotificationRow(n.log_id, n.channel, n.notif_type, n.recipient, n.subject, n.status,
                         n.error_message, n.created_at)
        for n in session.execute(q).scalars().all()
    ]
    return rows, total


def notification_stats(session: Session) -> dict:
    total = session.execute(select(func.count()).select_from(NotificationLog)).scalar_one()
    sent = session.execute(
        select(func.count()).select_from(NotificationLog).where(NotificationLog.status == "sent")
    ).scalar_one()
    failed = session.execute(
        select(func.count()).select_from(NotificationLog).where(NotificationLog.status == "failed")
    ).scalar_one()
    today = session.execute(
        select(func.count()).select_from(NotificationLog).where(func.date(NotificationLog.created_at) == date.today())
    ).scalar_one()
    return {"total": total, "sent": sent, "failed": failed, "today": today}
