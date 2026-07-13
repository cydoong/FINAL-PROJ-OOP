"""
core.archive_service
========================
Exact Python port of admin/archive.php: restoring an archived
employee or position back to the live tables (with every original
conflict check — duplicate name, duplicate email, missing department/
position, employee-code collisions, username collisions), and
permanently purging archive records.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from core.audit import log_action
from core.auth_service import generate_passcode
from core.security import hash_password
from config.settings import get_settings
from database.models import (
    Department, Employee, EmployeeArchive, Position, PositionArchive, User,
)


@dataclass
class ServiceResult:
    success: bool
    error: Optional[str] = None
    data: Optional[dict] = None


_CODE_RE = re.compile(r"^EMP-\d+$")


def restore_employee(session: Session, archive_id: int, admin_id: Optional[int]) -> ServiceResult:
    arc = session.get(EmployeeArchive, archive_id)
    if not arc:
        return ServiceResult(False, "Archive record not found.")

    name_conflict = session.execute(
        select(Employee.employee_id).where(
            func.lower(Employee.first_name) == arc.first_name.lower(),
            func.lower(Employee.last_name) == arc.last_name.lower(),
        )
    ).first()
    if name_conflict:
        return ServiceResult(False, f"Cannot restore {arc.first_name} {arc.last_name}: an active employee with "
                                     f"the same name already exists. Edit or remove that record first.")

    if arc.email:
        email_conflict = session.execute(select(Employee.employee_id).where(Employee.email == arc.email)).first()
        if email_conflict:
            return ServiceResult(False, f"Cannot restore: email {arc.email} is already used by an active employee.")

    if arc.department_id and not session.get(Department, arc.department_id):
        return ServiceResult(False, f"Cannot restore: the original department ({arc.department_name}) no longer "
                                     f"exists. Please re-add the employee manually.")

    if arc.position_id and not session.get(Position, arc.position_id):
        return ServiceResult(False, f"Cannot restore: the original position ({arc.position_title}) no longer "
                                     f"exists. Please re-add the employee manually.")

    # ── Determine a safe employee_code ──
    restore_code = arc.employee_code or ""
    code_is_valid = bool(restore_code and restore_code != "0" and _CODE_RE.match(restore_code))
    if code_is_valid:
        conflict = session.execute(select(Employee.employee_id).where(Employee.employee_code == restore_code)).first()
        if conflict:
            code_is_valid = False

    if not code_is_valid:
        last_live = session.execute(
            select(Employee.employee_code).order_by(Employee.employee_id.desc()).limit(1)
        ).scalar_one_or_none()
        last_archive = session.execute(
            select(EmployeeArchive.employee_code).where(EmployeeArchive.archive_id != archive_id)
            .order_by(EmployeeArchive.archive_id.desc()).limit(1)
        ).scalar_one_or_none()
        n1 = int(re.sub(r"\D", "", last_live)) if last_live else 0
        n2 = int(re.sub(r"\D", "", last_archive)) if last_archive else 0
        next_num = max(n1, n2) + 1
        restore_code = f"EMP-{next_num:03d}"
        while session.execute(select(Employee.employee_id).where(Employee.employee_code == restore_code)).first():
            next_num += 1
            restore_code = f"EMP-{next_num:03d}"

    # ── Create user account ──
    new_uid = None
    new_passcode = None
    final_username = arc.username
    reset_pw = get_settings().reset_default_password
    if arc.username:
        new_passcode = generate_passcode(session)
        taken = session.execute(select(User.user_id).where(User.username == arc.username)).first()
        use_uname = f"{arc.username}_r{datetime.now():%y%m%d}" if taken else arc.username
        final_username = use_uname
        user = User(username=use_uname, password=hash_password(reset_pw), role="employee",
                    passcode=new_passcode, account_activated=False, is_active=True)
        session.add(user)
        session.flush()
        new_uid = user.user_id

    emp = Employee(
        user_id=new_uid, employee_code=restore_code, first_name=arc.first_name, last_name=arc.last_name,
        middle_name=arc.middle_name, email=arc.email or None, phone=arc.phone or None,
        address=arc.address or None, gender=arc.gender or "male",
        birthdate=arc.birthdate, hire_date=arc.hire_date or date.today(),
        department_id=arc.department_id, position_id=arc.position_id,
        employment_status=arc.employment_status or "active",
        sss_number=arc.sss_number or None, philhealth_number=arc.philhealth_number or None,
        pagibig_number=arc.pagibig_number or None, tin_number=arc.tin_number or None,
        bank_name=arc.bank_name or None, bank_account=arc.bank_account or None,
    )
    session.add(emp)
    try:
        session.flush()
    except Exception as e:  # noqa: BLE001
        session.rollback()
        return ServiceResult(False, f"Failed to restore employee: {e}")

    log_action(session, admin_id, "RESTORE_EMPLOYEE", "employees", emp.employee_id, "archive",
               f"{arc.first_name} {arc.last_name}")
    session.delete(arc)
    session.flush()

    return ServiceResult(True, data={
        "name": f"{emp.first_name} {emp.last_name}",
        "employee_code": restore_code,
        "code_changed": restore_code != (arc.employee_code or ""),
        "username_changed": final_username != arc.username,
        "username": final_username,
        "new_passcode": new_passcode,
        "new_uid": new_uid,
    })


def restore_position(session: Session, archive_id: int, admin_id: Optional[int]) -> ServiceResult:
    arc = session.get(PositionArchive, archive_id)
    if not arc:
        return ServiceResult(False, "Archive record not found.")

    conflict = session.execute(
        select(Position.position_id).where(
            func.lower(Position.position_title) == arc.position_title.lower(),
            Position.department_id == arc.department_id,
            Position.is_active == True,  # noqa: E712
        )
    ).first()
    if conflict:
        return ServiceResult(False, f"Cannot restore: a position named {arc.position_title} already exists "
                                     f"in {arc.department_name}.")

    if not arc.department_id or not session.get(Department, arc.department_id):
        return ServiceResult(False, f"Cannot restore: the original department ({arc.department_name}) no longer exists.")

    pos = Position(
        department_id=arc.department_id, position_title=arc.position_title, base_salary=arc.base_salary,
        employment_type=arc.employment_type or "full_time", description=arc.description, is_active=True,
    )
    session.add(pos)
    try:
        session.flush()
    except Exception as e:  # noqa: BLE001
        session.rollback()
        return ServiceResult(False, f"Failed to restore position: {e}")

    log_action(session, admin_id, "RESTORE_POSITION", "positions", pos.position_id, "archive", arc.position_title)
    title = arc.position_title
    session.delete(arc)
    session.flush()
    return ServiceResult(True, data={"title": title})


def purge_employee(session: Session, archive_id: int, admin_id: Optional[int]) -> ServiceResult:
    arc = session.get(EmployeeArchive, archive_id)
    if not arc:
        return ServiceResult(False, "Archive record not found.")
    name = f"{arc.first_name} {arc.last_name}"
    session.delete(arc)
    session.flush()
    log_action(session, admin_id, "PURGE_EMPLOYEE", "employees_archive", archive_id, name, "permanent_delete")
    return ServiceResult(True, data={"name": name})


def purge_position(session: Session, archive_id: int, admin_id: Optional[int]) -> ServiceResult:
    arc = session.get(PositionArchive, archive_id)
    if not arc:
        return ServiceResult(False, "Archive record not found.")
    title = arc.position_title
    session.delete(arc)
    session.flush()
    log_action(session, admin_id, "PURGE_POSITION", "positions_archive", archive_id, title, "permanent_delete")
    return ServiceResult(True, data={"title": title})


def list_archived_employees(session: Session) -> list[EmployeeArchive]:
    return list(session.execute(select(EmployeeArchive).order_by(EmployeeArchive.archived_at.desc())).scalars().all())


def list_archived_positions(session: Session) -> list[PositionArchive]:
    return list(session.execute(select(PositionArchive).order_by(PositionArchive.archived_at.desc())).scalars().all())
