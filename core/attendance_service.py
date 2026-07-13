"""
core.attendance_service
===========================
Daily time-in/time-out attendance log, kept by the admin (front-desk
style — this isn't employee self-service clock-in).

Design rules straight from the spec:
  * time_in / time_out are always `datetime.now()` at the moment the
    admin taps the button — never hand-typed — for the normal flow.
  * Once time_in is set via the tap flow, tapping again is blocked
    (same for time_out) — this keeps the everyday flow honest and
    prevents accidental double-taps.
  * For flexibility (testing, or correcting a tap that caught the
    wrong moment), override_time_in()/override_time_out() let the
    admin deliberately set an exact time regardless of lock state —
    same "auto-filled but overridable" pattern as the payroll
    attendance override. This is an explicit action (an edit button in
    the UI), not the default path.
  * Picking a work_date that isn't today is allowed (back-filling a
    missed day), but the caller is expected to confirm with the admin
    first (see ui/admin/attendance_page.py) — record_time_in/out just
    remembers that a backdated entry happened, for the audit trail.
  * Attendance rows are the single source of truth for payroll: days
    worked / absent / late / overtime hours are aggregated straight
    from here, not typed in twice.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.settings import get_settings
from core.audit import log_action
from database.models import DailyAttendance, Employee


@dataclass
class ServiceResult:
    success: bool
    error: Optional[str] = None
    data: Optional[dict] = None


def _parse_hhmm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def list_active_employees_for_roster(session: Session) -> list[dict]:
    """Lightweight employee list for the daily attendance roster —
    active employees only, ordered by name."""
    from database.models import Department
    rows = session.execute(
        select(Employee, Department.department_name)
        .join(Department, Employee.department_id == Department.department_id)
        .where(Employee.employment_status == "active")
        .order_by(Employee.first_name, Employee.last_name)
    ).all()
    return [{"employee_id": e.employee_id, "full_name": e.full_name, "employee_code": e.employee_code,
             "department_name": dept_name} for e, dept_name in rows]


def get_day(session: Session, employee_id: int, work_date: date) -> Optional[DailyAttendance]:
    return session.execute(
        select(DailyAttendance).where(
            DailyAttendance.employee_id == employee_id, DailyAttendance.work_date == work_date
        )
    ).scalar_one_or_none()


def _get_or_create(session: Session, employee_id: int, work_date: date) -> DailyAttendance:
    row = get_day(session, employee_id, work_date)
    if row is None:
        row = DailyAttendance(employee_id=employee_id, work_date=work_date, status="present")
        session.add(row)
        session.flush()
    return row


def _status_for_time_in(work_date: date, time_in: datetime, cfg) -> str:
    shift_start = _parse_hhmm(cfg.shift_start)
    grace = timedelta(minutes=cfg.grace_minutes)
    cutoff = datetime.combine(work_date, shift_start) + grace
    return "late" if time_in > cutoff else "present"


def _late_minutes(work_date: date, time_in: datetime, cfg) -> Decimal:
    """Minutes late, measured from the *exact* shift start — not from
    the end of the grace period. Grace only forgives the "late" status
    label (see _status_for_time_in); once someone is beyond it, the
    deduction covers their full lateness from the actual start time,
    which is standard practice ("grace" is a free pass, not a discount)."""
    shift_start = _parse_hhmm(cfg.shift_start)
    grace = timedelta(minutes=cfg.grace_minutes)
    start_dt = datetime.combine(work_date, shift_start)
    cutoff = start_dt + grace
    if time_in <= cutoff:
        return Decimal("0.00")
    return (Decimal((time_in - start_dt).total_seconds()) / Decimal(60)).quantize(Decimal("0.01"))


def _undertime_minutes(work_date: date, time_out: datetime, cfg) -> Decimal:
    """Minutes left before the shift's official end time, with the same
    grace-period tolerance as lateness (a couple of minutes early
    isn't worth nagging over, but beyond that it's counted in full,
    measured from the exact shift end)."""
    shift_end = _parse_hhmm(cfg.shift_end)
    grace = timedelta(minutes=cfg.grace_minutes)
    end_dt = datetime.combine(work_date, shift_end)
    cutoff = end_dt - grace
    if time_out >= cutoff:
        return Decimal("0.00")
    return (Decimal((end_dt - time_out).total_seconds()) / Decimal(60)).quantize(Decimal("0.01"))


def _recompute_hours(row: DailyAttendance, cfg) -> None:
    """Recompute hours_worked/overtime_hours (and half_day status) from
    whatever time_in/time_out are currently set — used after both the
    normal tap flow and manual overrides so the numbers never drift
    out of sync with the raw timestamps."""
    standard = Decimal(str(cfg.standard_hours_per_day))
    if row.time_in and row.time_out:
        delta = row.time_out - row.time_in
        hours = (Decimal(delta.total_seconds()) / Decimal(3600)).quantize(Decimal("0.01"))
        row.hours_worked = max(hours, Decimal("0.00"))
        row.overtime_hours = max(Decimal("0.00"), row.hours_worked - standard)
        if row.status not in ("on_leave", "holiday", "rest_day") and row.hours_worked > 0 and row.hours_worked < (standard / 2):
            row.status = "half_day"
    else:
        row.hours_worked = Decimal("0.00")
        row.overtime_hours = Decimal("0.00")


def record_time_in(session: Session, employee_id: int, work_date: date,
                    admin_id: Optional[int], backdated: bool = False) -> ServiceResult:
    row = _get_or_create(session, employee_id, work_date)
    if row.is_time_in_locked:
        return ServiceResult(False, "Time In has already been recorded for this day. Use the edit (\u270e) button to change it.")

    now = datetime.now()
    cfg = get_settings().attendance
    row.time_in = now
    row.is_time_in_locked = True
    row.status = _status_for_time_in(work_date, now, cfg)
    row.late_minutes = _late_minutes(work_date, now, cfg)
    row.backdated_flag = row.backdated_flag or backdated
    row.recorded_by = admin_id
    _recompute_hours(row, cfg)
    session.flush()

    log_action(session, admin_id, "ATTENDANCE_TIME_IN", "daily_attendance", row.daily_attendance_id,
               None, f"emp:{employee_id} date:{work_date} in:{now.strftime('%H:%M:%S')}")
    return ServiceResult(True, data={"time_in": now, "status": row.status})


def record_time_out(session: Session, employee_id: int, work_date: date,
                     admin_id: Optional[int]) -> ServiceResult:
    row = get_day(session, employee_id, work_date)
    if row is None or not row.is_time_in_locked:
        return ServiceResult(False, "Time In hasn't been recorded yet for this day.")
    if row.is_time_out_locked:
        return ServiceResult(False, "Time Out has already been recorded for this day. Use the edit (\u270e) button to change it.")

    now = datetime.now()
    if row.time_in and now < row.time_in:
        return ServiceResult(False, "Time Out can't be earlier than Time In.")

    cfg = get_settings().attendance
    row.time_out = now
    row.is_time_out_locked = True
    row.undertime_minutes = _undertime_minutes(work_date, now, cfg)
    _recompute_hours(row, cfg)
    session.flush()

    log_action(session, admin_id, "ATTENDANCE_TIME_OUT", "daily_attendance", row.daily_attendance_id,
               None, f"emp:{employee_id} date:{work_date} out:{now.strftime('%H:%M:%S')} hours:{row.hours_worked}")
    return ServiceResult(True, data={"time_out": now, "hours_worked": row.hours_worked, "overtime_hours": row.overtime_hours})


def override_time_in(session: Session, employee_id: int, work_date: date, new_time: datetime,
                      admin_id: Optional[int]) -> ServiceResult:
    """Manually set an exact Time In, bypassing the tap-flow lock. This
    is the deliberate escape hatch for testing and for correcting a
    tap that captured the wrong moment — the auto-tap flow above stays
    the normal path, but nothing here is permanently locked against a
    knowing admin action."""
    row = _get_or_create(session, employee_id, work_date)
    if row.time_out and new_time > row.time_out:
        return ServiceResult(False, "Time In can't be after the recorded Time Out.")
    cfg = get_settings().attendance
    row.time_in = new_time
    row.is_time_in_locked = True
    if row.status not in ("on_leave", "holiday", "rest_day"):
        row.status = _status_for_time_in(work_date, new_time, cfg)
        row.late_minutes = _late_minutes(work_date, new_time, cfg)
    _recompute_hours(row, cfg)
    row.recorded_by = admin_id
    session.flush()

    log_action(session, admin_id, "ATTENDANCE_TIME_IN_OVERRIDE", "daily_attendance", row.daily_attendance_id,
               None, f"emp:{employee_id} date:{work_date} in:{new_time.strftime('%H:%M:%S')}")
    return ServiceResult(True, data={"time_in": new_time, "status": row.status})


def override_time_out(session: Session, employee_id: int, work_date: date, new_time: datetime,
                       admin_id: Optional[int]) -> ServiceResult:
    """Manually set an exact Time Out, bypassing the tap-flow lock."""
    row = get_day(session, employee_id, work_date)
    if row is None:
        return ServiceResult(False, "No attendance record exists yet for this day — set Time In first.")
    if row.time_in and new_time < row.time_in:
        return ServiceResult(False, "Time Out can't be earlier than Time In.")
    cfg = get_settings().attendance
    row.time_out = new_time
    row.is_time_out_locked = True
    row.undertime_minutes = _undertime_minutes(work_date, new_time, cfg)
    _recompute_hours(row, cfg)
    row.recorded_by = admin_id
    session.flush()

    log_action(session, admin_id, "ATTENDANCE_TIME_OUT_OVERRIDE", "daily_attendance", row.daily_attendance_id,
               None, f"emp:{employee_id} date:{work_date} out:{new_time.strftime('%H:%M:%S')} hours:{row.hours_worked}")
    return ServiceResult(True, data={"time_out": new_time, "hours_worked": row.hours_worked, "overtime_hours": row.overtime_hours})


def mark_special_status(session: Session, employee_id: int, work_date: date, status: str,
                         admin_id: Optional[int], notes: str = "", backdated: bool = False) -> ServiceResult:
    """Mark a day as absent/on_leave/holiday/rest_day without a time-in —
    for days the admin is filling in after the fact rather than
    clocking live. Also locks immediately once set."""
    if status not in ("absent", "on_leave", "holiday", "rest_day"):
        return ServiceResult(False, "Invalid status.")
    row = get_day(session, employee_id, work_date)
    if row is not None and (row.is_time_in_locked or row.is_time_out_locked):
        return ServiceResult(False, "This day already has a locked time-in/out record.")
    if row is None:
        row = DailyAttendance(employee_id=employee_id, work_date=work_date)
        session.add(row)
    row.status = status
    row.is_time_in_locked = True
    row.is_time_out_locked = True
    row.hours_worked = Decimal("0")
    row.overtime_hours = Decimal("0")
    row.notes = notes or None
    row.backdated_flag = row.backdated_flag or backdated
    row.recorded_by = admin_id
    session.flush()

    log_action(session, admin_id, "ATTENDANCE_MARK", "daily_attendance", row.daily_attendance_id,
               None, f"emp:{employee_id} date:{work_date} status:{status}")
    return ServiceResult(True, data={"status": status})


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def list_range(session: Session, employee_id: int, start: date, end: date) -> list[DailyAttendance]:
    start, end = _as_date(start), _as_date(end)
    return list(session.execute(
        select(DailyAttendance)
        .where(DailyAttendance.employee_id == employee_id,
               DailyAttendance.work_date >= start, DailyAttendance.work_date <= end)
        .order_by(DailyAttendance.work_date)
    ).scalars().all())


def list_day_all_employees(session: Session, work_date: date) -> dict[int, DailyAttendance]:
    rows = session.execute(
        select(DailyAttendance).where(DailyAttendance.work_date == work_date)
    ).scalars().all()
    return {r.employee_id: r for r in rows}


@dataclass
class PeriodSummary:
    days_worked: Decimal
    days_absent: Decimal
    days_late: Decimal
    days_on_leave: Decimal
    total_hours: Decimal
    overtime_hours: Decimal
    late_minutes_total: Decimal
    undertime_minutes_total: Decimal
    records_found: int


def compute_period_summary(session: Session, employee_id: int, start: date, end: date) -> PeriodSummary:
    """Aggregates daily attendance into the totals payroll needs. This
    is what replaces hand-typed 'Days Worked' / 'Overtime Hours' in the
    payroll dialog."""
    rows = list_range(session, employee_id, start, end)
    days_worked = Decimal("0")
    days_absent = Decimal("0")
    days_late = Decimal("0")
    days_on_leave = Decimal("0")
    total_hours = Decimal("0")
    overtime_hours = Decimal("0")
    late_minutes_total = Decimal("0")
    undertime_minutes_total = Decimal("0")

    for r in rows:
        if r.status == "absent":
            days_absent += 1
        elif r.status == "on_leave":
            days_on_leave += 1
        elif r.status == "holiday":
            days_worked += 1  # paid holiday counts toward days worked
        elif r.status == "rest_day":
            pass
        elif r.status == "half_day":
            days_worked += Decimal("0.5")
            total_hours += r.hours_worked or Decimal("0")
        else:  # present / late
            days_worked += 1
            if r.status == "late":
                days_late += 1
            total_hours += r.hours_worked or Decimal("0")
        overtime_hours += r.overtime_hours or Decimal("0")
        late_minutes_total += r.late_minutes or Decimal("0")
        undertime_minutes_total += r.undertime_minutes or Decimal("0")

    return PeriodSummary(
        days_worked=days_worked, days_absent=days_absent, days_late=days_late,
        days_on_leave=days_on_leave, total_hours=total_hours, overtime_hours=overtime_hours,
        late_minutes_total=late_minutes_total, undertime_minutes_total=undertime_minutes_total,
        records_found=len(rows),
    )


def count_business_days(start: date, end: date) -> int:
    """Mon–Fri count in [start, end], used to flag periods where
    attendance records look incomplete."""
    n = 0
    d = start
    while d <= end:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


# ─────────────────────────────────────────────────────────────────────────
#  Holiday calendar — source of truth for holiday pay (see database.
#  models.Holiday for the DOLE-style rules this feeds into).
# ─────────────────────────────────────────────────────────────────────────

def list_holidays(session: Session, start: Optional[date] = None, end: Optional[date] = None):
    from database.models import Holiday
    stmt = select(Holiday).where(Holiday.is_active == True)  # noqa: E712
    if start is not None:
        stmt = stmt.where(Holiday.holiday_date >= start)
    if end is not None:
        stmt = stmt.where(Holiday.holiday_date <= end)
    return list(session.execute(stmt.order_by(Holiday.holiday_date)).scalars().all())


def get_holiday_for_date(session: Session, work_date: date):
    from database.models import Holiday
    return session.execute(
        select(Holiday).where(Holiday.holiday_date == work_date, Holiday.is_active == True)  # noqa: E712
    ).scalar_one_or_none()


def add_holiday(session: Session, holiday_date: date, name: str, holiday_type: str,
                 admin_id: Optional[int] = None) -> ServiceResult:
    from database.models import Holiday
    if holiday_type not in ("regular", "special"):
        return ServiceResult(False, "Holiday type must be 'regular' or 'special'.")
    existing = session.execute(
        select(Holiday).where(Holiday.holiday_date == holiday_date)
    ).scalar_one_or_none()
    if existing:
        existing.name = name
        existing.holiday_type = holiday_type
        existing.is_active = True
    else:
        session.add(Holiday(holiday_date=holiday_date, name=name, holiday_type=holiday_type, is_active=True))
    session.flush()
    log_action(session, admin_id, "HOLIDAY_ADD", "holidays", None, None, f"{holiday_date}:{name}:{holiday_type}")
    return ServiceResult(True)


def delete_holiday(session: Session, holiday_id: int, admin_id: Optional[int] = None) -> ServiceResult:
    from database.models import Holiday
    row = session.get(Holiday, holiday_id)
    if not row:
        return ServiceResult(False, "Holiday not found.")
    session.delete(row)
    session.flush()
    log_action(session, admin_id, "HOLIDAY_DELETE", "holidays", holiday_id, None, None)
    return ServiceResult(True)


@dataclass
class HolidayAdjustment:
    regular_worked_days: Decimal      # regular holidays the employee actually worked
    special_worked_days: Decimal      # special holidays the employee actually worked
    special_unworked_weekdays: Decimal  # special holidays (falling on a weekday) NOT worked —
                                         # excluded from standard paid days ("no work, no pay")
    holiday_notes: list  # human-readable lines for the payslip/preview


def compute_holiday_adjustment(session: Session, employee_id: int, start: date, end: date) -> HolidayAdjustment:
    """Walks every holiday in [start, end] and checks whether this
    employee actually worked that specific date (has a time_in), to
    apply the DOLE-style treatment. See database.models.Holiday."""
    holidays = list_holidays(session, start, end)
    if not holidays:
        return HolidayAdjustment(Decimal("0"), Decimal("0"), Decimal("0"), [])

    day_map = {r.work_date: r for r in list_range(session, employee_id, start, end)}
    regular_worked = Decimal("0")
    special_worked = Decimal("0")
    special_unworked_weekday = Decimal("0")
    notes = []

    for h in holidays:
        rec = day_map.get(h.holiday_date)
        worked = bool(rec and rec.time_in)
        if h.holiday_type == "regular":
            if worked:
                regular_worked += 1
                notes.append(f"{h.holiday_date.strftime('%b %d')} \u2014 {h.name} (Regular, worked: +100% premium)")
            else:
                notes.append(f"{h.holiday_date.strftime('%b %d')} \u2014 {h.name} (Regular, not worked: paid as usual)")
        else:  # special
            if worked:
                special_worked += 1
                notes.append(f"{h.holiday_date.strftime('%b %d')} \u2014 {h.name} (Special, worked: +30% premium)")
            elif h.holiday_date.weekday() < 5:
                special_unworked_weekday += 1
                notes.append(f"{h.holiday_date.strftime('%b %d')} \u2014 {h.name} (Special, not worked: no work no pay)")

    return HolidayAdjustment(regular_worked, special_worked, special_unworked_weekday, notes)
