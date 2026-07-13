"""
core.reference_service
==========================
CRUD for the "reference data" tables — departments, positions,
allowance types, deduction types — precisely mirroring
admin/departments.php, admin/positions.php and admin/allowances.php,
including their guard rails:

  * A department can't be deleted while it still has active positions
    or ANY employees (active or not).
  * A position isn't hard-deleted — it's archived (moved to
    positions_archive) — and only if it has no employees assigned.
  * Allowance/deduction types are simple CRUD, but duplicate names
    (case-insensitive) are rejected on add.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from core.audit import log_action
from database.models import (
    AllowanceType, DeductionType, Department, Employee, Position, PositionArchive,
)


@dataclass
class ServiceResult:
    success: bool
    error: Optional[str] = None
    data: Optional[dict] = None


# ─────────────────────────────────────────────────────────────────────────
#  Departments
# ─────────────────────────────────────────────────────────────────────────

def add_department(session: Session, name: str, description: str, admin_id: Optional[int]) -> ServiceResult:
    name = (name or "").strip()
    if not name:
        return ServiceResult(False, "Department name is required.")
    exists = session.execute(
        select(Department.department_id).where(func.lower(Department.department_name) == name.lower())
    ).first()
    if exists:
        return ServiceResult(False, f'A department named "{name}" already exists.')
    dept = Department(department_name=name, description=description or None, head_name="", is_active=True)
    session.add(dept)
    session.flush()
    log_action(session, admin_id, "ADD_DEPARTMENT", "departments", dept.department_id, None, name)
    return ServiceResult(True, data={"department_id": dept.department_id})


def edit_department(session: Session, department_id: int, name: str, description: str, is_active: bool,
                     head_employee_id: Optional[int], admin_id: Optional[int]) -> ServiceResult:
    dept = session.get(Department, department_id)
    if not dept:
        return ServiceResult(False, "Department not found.")

    head_name = ""
    if head_employee_id:
        emp = session.execute(
            select(Employee).where(
                Employee.employee_id == head_employee_id,
                Employee.department_id == department_id,
                Employee.employment_status == "active",
            )
        ).scalar_one_or_none()
        if not emp:
            return ServiceResult(False, "Invalid: selected employee does not belong to this department.")
        head_name = emp.full_name

    dept.department_name = name
    dept.description = description or None
    dept.head_name = head_name
    dept.is_active = is_active
    session.flush()
    log_action(session, admin_id, "EDIT_DEPARTMENT", "departments", department_id, None, name)
    return ServiceResult(True)


def delete_department(session: Session, department_id: int, admin_id: Optional[int]) -> ServiceResult:
    dept = session.get(Department, department_id)
    if not dept:
        return ServiceResult(False, "Department not found.")

    pos_count = session.execute(
        select(func.count()).select_from(Position).where(
            Position.department_id == department_id, Position.is_active == True  # noqa: E712
        )
    ).scalar_one()
    if pos_count > 0:
        return ServiceResult(False, f'Cannot delete "{dept.department_name}": it still has {pos_count} '
                                     f"active position(s). Archive or move all positions first.")

    emp_count = session.execute(
        select(func.count()).select_from(Employee).where(Employee.department_id == department_id)
    ).scalar_one()
    if emp_count > 0:
        return ServiceResult(False, f'Cannot delete "{dept.department_name}": it still has {emp_count} '
                                     f"employee(s) assigned (including inactive). Archive or reassign all employees first.")

    name = dept.department_name
    session.delete(dept)
    session.flush()
    log_action(session, admin_id, "DELETE_DEPARTMENT", "departments", department_id, name, None)
    return ServiceResult(True)


@dataclass
class DepartmentRow:
    department_id: int
    department_name: str
    description: Optional[str]
    head_name: Optional[str]
    is_active: bool
    emp_count: int
    pos_count: int


def list_departments(session: Session) -> list[DepartmentRow]:
    depts = session.execute(select(Department).order_by(Department.department_name)).scalars().all()
    rows = []
    for d in depts:
        emp_count = session.execute(
            select(func.count()).select_from(Employee).where(Employee.department_id == d.department_id)
        ).scalar_one()
        pos_count = session.execute(
            select(func.count()).select_from(Position).where(
                Position.department_id == d.department_id, Position.is_active == True  # noqa: E712
            )
        ).scalar_one()
        rows.append(DepartmentRow(d.department_id, d.department_name, d.description, d.head_name,
                                   d.is_active, emp_count, pos_count))
    return rows


def active_employees_in_department(session: Session, department_id: int) -> list[Employee]:
    return list(session.execute(
        select(Employee).where(Employee.department_id == department_id, Employee.employment_status == "active")
        .order_by(Employee.first_name)
    ).scalars().all())


# ─────────────────────────────────────────────────────────────────────────
#  Positions
# ─────────────────────────────────────────────────────────────────────────

def add_position(session: Session, department_id: int, title: str, base_salary, employment_type: str,
                  description: str, admin_id: Optional[int]) -> ServiceResult:
    title = (title or "").strip()
    dup = session.execute(
        select(Position.position_id).where(
            func.lower(Position.position_title) == title.lower(), Position.department_id == department_id
        )
    ).first()
    if dup:
        return ServiceResult(False, f'A position named "{title}" already exists in that department.')
    pos = Position(department_id=department_id, position_title=title, base_salary=base_salary,
                    employment_type=employment_type, description=description or None, is_active=True)
    session.add(pos)
    session.flush()
    log_action(session, admin_id, "ADD_POSITION", "positions", pos.position_id, None, title)
    return ServiceResult(True, data={"position_id": pos.position_id})


def edit_position(session: Session, position_id: int, department_id: int, title: str, base_salary,
                   employment_type: str, description: str, is_active: bool, admin_id: Optional[int]) -> ServiceResult:
    pos = session.get(Position, position_id)
    if not pos:
        return ServiceResult(False, "Position not found.")
    pos.department_id = department_id
    pos.position_title = title
    pos.base_salary = base_salary
    pos.employment_type = employment_type
    pos.description = description or None
    pos.is_active = is_active
    session.flush()
    log_action(session, admin_id, "EDIT_POSITION", "positions", position_id, None, title)
    return ServiceResult(True)


def archive_position(session: Session, position_id: int, admin_id: Optional[int]) -> ServiceResult:
    pos = session.get(Position, position_id)
    if not pos:
        return ServiceResult(False, "Position not found.")
    dept = session.get(Department, pos.department_id)

    emp_count = session.execute(
        select(func.count()).select_from(Employee).where(Employee.position_id == position_id)
    ).scalar_one()
    if emp_count > 0:
        return ServiceResult(False, f'Cannot archive position "{pos.position_title}": it has active employees assigned.')

    session.add(PositionArchive(
        position_id=pos.position_id, department_id=pos.department_id,
        department_name=dept.department_name if dept else None, position_title=pos.position_title,
        base_salary=pos.base_salary, employment_type=pos.employment_type, description=pos.description,
        archived_by=admin_id,
    ))
    title = pos.position_title
    session.delete(pos)
    session.flush()
    log_action(session, admin_id, "ARCHIVE_POSITION", "positions", position_id, title, None)
    return ServiceResult(True, data={"title": title})


@dataclass
class PositionRow:
    position_id: int
    department_id: int
    department_name: str
    position_title: str
    base_salary: float
    employment_type: str
    description: Optional[str]
    is_active: bool
    emp_count: int


def list_positions(session: Session, department_id: int = 0) -> list[PositionRow]:
    q = (
        select(Position, Department.department_name)
        .join(Department, Position.department_id == Department.department_id)
        .order_by(Department.department_name, Position.position_title)
    )
    if department_id:
        q = q.where(Position.department_id == department_id)
    rows = []
    for pos, dept_name in session.execute(q).all():
        emp_count = session.execute(
            select(func.count()).select_from(Employee).where(
                Employee.position_id == pos.position_id, Employee.employment_status == "active"
            )
        ).scalar_one()
        rows.append(PositionRow(pos.position_id, pos.department_id, dept_name, pos.position_title,
                                 float(pos.base_salary), pos.employment_type, pos.description,
                                 pos.is_active, emp_count))
    return rows


# ─────────────────────────────────────────────────────────────────────────
#  Allowance / Deduction types
# ─────────────────────────────────────────────────────────────────────────

def add_allowance_type(session: Session, name: str, description: str, is_taxable: bool) -> ServiceResult:
    name = (name or "").strip()
    if not name:
        return ServiceResult(False, "Allowance name is required.")
    if session.execute(select(AllowanceType.allowance_type_id).where(
        func.lower(AllowanceType.type_name) == name.lower())
    ).first():
        return ServiceResult(False, f'An allowance type named "{name}" already exists.')
    row = AllowanceType(type_name=name, description=description or None, is_taxable=is_taxable, is_active=True)
    session.add(row)
    session.flush()
    return ServiceResult(True, data={"id": row.allowance_type_id})


def edit_allowance_type(session: Session, type_id: int, name: str, description: str, is_taxable: bool) -> ServiceResult:
    row = session.get(AllowanceType, type_id)
    if not row:
        return ServiceResult(False, "Allowance type not found.")
    row.type_name = name
    row.description = description or None
    row.is_taxable = is_taxable
    session.flush()
    return ServiceResult(True)


def delete_allowance_type(session: Session, type_id: int) -> ServiceResult:
    row = session.get(AllowanceType, type_id)
    if row:
        session.delete(row)
        session.flush()
    return ServiceResult(True)


def add_deduction_type(session: Session, name: str, description: str, is_mandatory: bool) -> ServiceResult:
    name = (name or "").strip()
    if not name:
        return ServiceResult(False, "Deduction name is required.")
    if session.execute(select(DeductionType.deduction_type_id).where(
        func.lower(DeductionType.type_name) == name.lower())
    ).first():
        return ServiceResult(False, f'A deduction type named "{name}" already exists.')
    row = DeductionType(type_name=name, description=description or None, is_mandatory=is_mandatory, is_active=True)
    session.add(row)
    session.flush()
    return ServiceResult(True, data={"id": row.deduction_type_id})


def edit_deduction_type(session: Session, type_id: int, name: str, description: str, is_mandatory: bool) -> ServiceResult:
    row = session.get(DeductionType, type_id)
    if not row:
        return ServiceResult(False, "Deduction type not found.")
    row.type_name = name
    row.description = description or None
    row.is_mandatory = is_mandatory
    session.flush()
    return ServiceResult(True)


def delete_deduction_type(session: Session, type_id: int) -> ServiceResult:
    row = session.get(DeductionType, type_id)
    if row:
        session.delete(row)
        session.flush()
    return ServiceResult(True)


def list_allowance_types(session: Session, active_only: bool = False) -> list[AllowanceType]:
    q = select(AllowanceType).order_by(AllowanceType.type_name)
    if active_only:
        q = q.where(AllowanceType.is_active == True)  # noqa: E712
    return list(session.execute(q).scalars().all())


def list_deduction_types(session: Session, active_only: bool = False) -> list[DeductionType]:
    q = select(DeductionType).order_by(DeductionType.type_name)
    if active_only:
        q = q.where(DeductionType.is_active == True)  # noqa: E712
    return list(session.execute(q).scalars().all())
