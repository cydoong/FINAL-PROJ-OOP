"""
core.employee_service
=========================
Precise Python port of admin/employees.php: add/edit employees,
username & duplicate-name checks, employee code generation, archive
(with the same guard rails — admin accounts and employees with
payroll history can't be archived), and passcode generation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from core.audit import log_action, log_employee_status_change
from core.auth_service import generate_passcode
from core.security import hash_password
from core.utils import clean_phone, is_valid_username
from config.settings import get_settings
from database.models import (
    Department, Employee, EmployeeArchive, Payroll, Position, User,
)


@dataclass
class ServiceResult:
    success: bool
    error: Optional[str] = None
    data: Optional[dict] = None
    field: Optional[str] = None  # which form field the error relates to, for UI highlighting


# ─────────────────────────────────────────────────────────────────────────
#  AJAX-style checks
# ─────────────────────────────────────────────────────────────────────────

def check_username_available(session: Session, username: str, exclude_uid: Optional[int] = None) -> bool:
    username = (username or "").strip().lower()
    q = select(User.user_id).where(User.username == username)
    if exclude_uid:
        q = q.where(User.user_id != exclude_uid)
    return session.execute(q).first() is None


def check_duplicate_name(session: Session, first: str, last: str, exclude_eid: Optional[int] = None) -> Optional[dict]:
    first = (first or "").strip().lower()
    last = (last or "").strip().lower()
    q = select(Employee).where(func.lower(Employee.first_name) == first, func.lower(Employee.last_name) == last)
    if exclude_eid:
        q = q.where(Employee.employee_id != exclude_eid)
    found = session.execute(q).scalar_one_or_none()
    if not found:
        return None
    return {
        "employee_code": found.employee_code,
        "employment_status": found.employment_status,
        "email": found.email,
        "full_name": found.full_name,
    }


def _generate_employee_code(session: Session) -> str:
    last = session.execute(
        select(Employee.employee_code).order_by(Employee.employee_id.desc()).limit(1)
    ).scalar_one_or_none()
    next_num = int(last[4:]) + 1 if last else 1
    arch = session.execute(
        select(EmployeeArchive.employee_code).order_by(EmployeeArchive.archive_id.desc()).limit(1)
    ).scalar_one_or_none()
    if arch:
        an = int(arch[4:]) if arch[4:].isdigit() else 0
        if an >= next_num:
            next_num = an + 1
    return f"EMP-{next_num:03d}"


# ─────────────────────────────────────────────────────────────────────────
#  Add / Edit
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class EmployeeFormData:
    first_name: str
    last_name: str
    middle_name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    gender: str = "male"
    birthdate: Optional[date] = None
    hire_date: Optional[date] = None
    department_id: int = 0
    position_id: int = 0
    employment_status: str = "active"
    sss_number: str = ""
    philhealth_number: str = ""
    pagibig_number: str = ""
    tin_number: str = ""
    bank_name: str = ""
    bank_account: str = ""
    payment_method: str = "bank_transfer"
    gcash_number: str = ""
    maya_number: str = ""
    username: str = ""  # only used on add


def _validate_payment_method(form: "EmployeeFormData") -> Optional[ServiceResult]:
    from core.utils import is_valid_ph_mobile
    method = (form.payment_method or "bank_transfer").strip().lower()
    if method == "gcash" and not is_valid_ph_mobile(form.gcash_number or ""):
        return ServiceResult(False, "A valid 11-digit GCash number is required (e.g. 09171234567).", field="gcash_number")
    if method == "maya" and not is_valid_ph_mobile(form.maya_number or ""):
        return ServiceResult(False, "A valid 11-digit Maya number is required (e.g. 09171234567).", field="maya_number")
    if method == "bank_transfer" and not (form.bank_name or "").strip():
        return ServiceResult(False, "Bank name is required when payment method is Bank Transfer.", field="bank_name")
    return None


def add_employee(session: Session, form: EmployeeFormData, admin_id: Optional[int]) -> ServiceResult:
    phone = clean_phone(form.phone)
    if phone and len(phone) != 11:
        return ServiceResult(False, "Phone number must be exactly 11 digits (e.g. 09171234567).", field="phone")

    if not (form.tin_number or "").strip():
        return ServiceResult(False, "TIN Number is required — every employee needs one on file for tax withholding.", field="tin_number")

    pm_err = _validate_payment_method(form)
    if pm_err:
        return pm_err

    username = (form.username or "").strip().lower()
    if not username:
        return ServiceResult(False, "Username is required.", field="username")
    if not is_valid_username(username):
        return ServiceResult(False, "Username may only contain lowercase letters, numbers, dots, and underscores.", field="username")
    if not check_username_available(session, username):
        return ServiceResult(False, f'Username "{username}" is already taken.', field="username")

    if form.email and session.execute(select(Employee.employee_id).where(Employee.email == form.email)).first():
        return ServiceResult(False, f'Email "{form.email}" is already registered to another employee.', field="email")

    if phone and session.execute(select(Employee.employee_id).where(Employee.phone == phone)).first():
        return ServiceResult(False, f'Phone number "{phone}" is already registered.', field="phone")

    emp_code = _generate_employee_code(session)
    passcode = generate_passcode(session)
    reset_pw = get_settings().reset_default_password

    user = User(
        username=username, password=hash_password(reset_pw), role="employee",
        passcode=passcode, account_activated=False, is_active=True,
    )
    session.add(user)
    session.flush()

    try:
        emp = Employee(
            user_id=user.user_id, employee_code=emp_code,
            first_name=form.first_name, last_name=form.last_name, middle_name=form.middle_name or None,
            email=form.email or None, phone=phone or None, address=form.address or None,
            gender=form.gender or None, birthdate=form.birthdate, hire_date=form.hire_date or date.today(),
            department_id=form.department_id, position_id=form.position_id,
            employment_status=form.employment_status,
            sss_number=form.sss_number or None, philhealth_number=form.philhealth_number or None,
            pagibig_number=form.pagibig_number or None, tin_number=form.tin_number or None,
            bank_name=form.bank_name or None, bank_account=form.bank_account or None,
            payment_method=form.payment_method or "bank_transfer",
            gcash_number=clean_phone(form.gcash_number) or None, maya_number=clean_phone(form.maya_number) or None,
        )
        session.add(emp)
        session.flush()
    except Exception as e:  # noqa: BLE001
        session.rollback()
        return ServiceResult(False, f"Failed to add employee: {e}")

    log_action(session, admin_id, "ADD_EMPLOYEE", "employees", emp.employee_id, None,
               f"{form.first_name} {form.last_name} | user:{username}")

    return ServiceResult(True, data={
        "employee_id": emp.employee_id,
        "employee_code": emp_code,
        "username": username,
        "passcode": passcode,
        "name": f"{form.first_name} {form.last_name}",
    })


def edit_employee(session: Session, employee_id: int, form: EmployeeFormData, admin_id: Optional[int]) -> ServiceResult:
    emp = session.get(Employee, employee_id)
    if not emp:
        return ServiceResult(False, "Employee not found.")

    phone = clean_phone(form.phone)
    if phone and len(phone) != 11:
        return ServiceResult(False, "Phone number must be exactly 11 digits (e.g. 09171234567).", field="phone")

    if not (form.tin_number or "").strip():
        return ServiceResult(False, "TIN Number is required — every employee needs one on file for tax withholding.", field="tin_number")

    pm_err = _validate_payment_method(form)
    if pm_err:
        return pm_err

    if form.email and session.execute(
        select(Employee.employee_id).where(Employee.email == form.email, Employee.employee_id != employee_id)
    ).first():
        return ServiceResult(False, f'Another employee already uses email "{form.email}".', field="email")

    if phone and session.execute(
        select(Employee.employee_id).where(Employee.phone == phone, Employee.employee_id != employee_id)
    ).first():
        return ServiceResult(False, f'Phone "{phone}" is already registered to another employee.', field="phone")

    old_name = emp.full_name
    old_status = emp.employment_status

    emp.first_name = form.first_name
    emp.last_name = form.last_name
    emp.middle_name = form.middle_name or None
    emp.email = form.email or None
    emp.phone = phone or None
    emp.address = form.address or None
    emp.gender = form.gender or None
    emp.birthdate = form.birthdate
    emp.hire_date = form.hire_date or emp.hire_date
    emp.department_id = form.department_id
    emp.position_id = form.position_id
    emp.employment_status = form.employment_status
    emp.sss_number = form.sss_number or None
    emp.philhealth_number = form.philhealth_number or None
    emp.pagibig_number = form.pagibig_number or None
    emp.tin_number = form.tin_number or None
    emp.bank_name = form.bank_name or None
    emp.bank_account = form.bank_account or None
    emp.payment_method = form.payment_method or "bank_transfer"
    emp.gcash_number = clean_phone(form.gcash_number) or None
    emp.maya_number = clean_phone(form.maya_number) or None
    session.flush()

    log_action(session, admin_id, "EDIT_EMPLOYEE", "employees", employee_id, old_name,
               f"{form.first_name} {form.last_name}")
    log_employee_status_change(session, employee_id, old_status, form.employment_status)

    return ServiceResult(True, data={"name": f"{form.first_name} {form.last_name}"})


# ─────────────────────────────────────────────────────────────────────────
#  Archive
# ─────────────────────────────────────────────────────────────────────────

def archive_employee(session: Session, employee_id: int, admin_id: Optional[int]) -> ServiceResult:
    emp = session.get(Employee, employee_id)
    if not emp:
        return ServiceResult(False, "Employee not found.")

    if emp.user_id:
        user = session.get(User, emp.user_id)
        if user and user.role == "admin":
            return ServiceResult(False, "Admin accounts cannot be archived.")

    has_payroll = session.execute(
        select(Payroll.payroll_id).where(Payroll.employee_id == employee_id).limit(1)
    ).first()
    if has_payroll:
        return ServiceResult(False, "Cannot archive employee with payroll records. Set status to Terminated instead.")

    dept = session.get(Department, emp.department_id)
    pos = session.get(Position, emp.position_id)
    user = session.get(User, emp.user_id) if emp.user_id else None

    archive_row = EmployeeArchive(
        employee_id=emp.employee_id, user_id=emp.user_id, employee_code=emp.employee_code,
        username=user.username if user else None,
        first_name=emp.first_name, last_name=emp.last_name, middle_name=emp.middle_name,
        email=emp.email, phone=emp.phone, address=emp.address, gender=emp.gender,
        birthdate=emp.birthdate, hire_date=emp.hire_date,
        department_id=emp.department_id, department_name=dept.department_name if dept else None,
        position_id=emp.position_id, position_title=pos.position_title if pos else None,
        employment_status=emp.employment_status,
        sss_number=emp.sss_number, philhealth_number=emp.philhealth_number,
        pagibig_number=emp.pagibig_number, tin_number=emp.tin_number,
        bank_name=emp.bank_name, bank_account=emp.bank_account,
        archived_by=admin_id, archive_reason="Manually archived by admin",
    )
    session.add(archive_row)
    session.flush()

    log_action(session, admin_id, "ARCHIVE_EMPLOYEE", "employees", employee_id,
               f"{emp.first_name} {emp.last_name}", None)

    full_name = emp.full_name
    session.delete(emp)
    if user and user.role != "admin":
        session.delete(user)
    session.flush()

    return ServiceResult(True, data={"name": full_name})


# ─────────────────────────────────────────────────────────────────────────
#  Passcode / password admin actions
# ─────────────────────────────────────────────────────────────────────────

def generate_passcode_for_employee(session: Session, target_user_id: int, admin_id: Optional[int]) -> ServiceResult:
    user = session.execute(
        select(User).where(User.user_id == target_user_id, User.role == "employee")
    ).scalar_one_or_none()
    if not user:
        return ServiceResult(False, "Employee account not found.")
    emp = session.execute(select(Employee).where(Employee.user_id == target_user_id)).scalar_one_or_none()

    new_code = generate_passcode(session)
    user.passcode = new_code
    session.flush()
    log_action(session, admin_id, "GENERATE_PASSCODE", "users", target_user_id, None,
               f"regenerated for {user.username}")
    return ServiceResult(True, data={
        "name": emp.full_name if emp else user.username,
        "username": user.username,
        "passcode": new_code,
        "emp_code": emp.employee_code if emp else None,
    })


# ─────────────────────────────────────────────────────────────────────────
#  Listing
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class EmployeeRow:
    employee_id: int
    employee_code: str
    full_name: str
    first_name: str
    last_name: str
    email: Optional[str]
    phone: Optional[str]
    department_name: str
    position_title: str
    base_salary: float
    employment_type: str
    employment_status: str
    username: Optional[str]
    user_id: Optional[int]
    failed_attempts: int
    reset_requested: bool
    locked_until: Optional[str]
    passcode: Optional[str]
    account_activated: bool
    hire_date: Optional[date]


def list_employees(session: Session, search: str = "", department_id: int = 0, status: str = "",
                    page: int = 1, per_page: int = 12) -> tuple[list[EmployeeRow], int]:
    q = (
        select(Employee, Department.department_name, Position.position_title, Position.base_salary,
               Position.employment_type, User)
        .join(Department, Employee.department_id == Department.department_id)
        .join(Position, Employee.position_id == Position.position_id)
        .outerjoin(User, Employee.user_id == User.user_id)
    )
    if search:
        like = f"%{search}%"
        q = q.where(or_(
            Employee.first_name.like(like), Employee.last_name.like(like),
            Employee.email.like(like), Employee.employee_code.like(like),
        ))
    if department_id:
        q = q.where(Employee.department_id == department_id)
    if status:
        q = q.where(Employee.employment_status == status)

    count_q = select(func.count()).select_from(q.order_by(None).subquery())
    total = session.execute(count_q).scalar_one()

    q = q.order_by(Employee.employee_id.desc()).offset((page - 1) * per_page).limit(per_page)
    rows = []
    for emp, dept_name, pos_title, salary, emp_type, user in session.execute(q).all():
        rows.append(EmployeeRow(
            employee_id=emp.employee_id, employee_code=emp.employee_code, full_name=emp.full_name,
            first_name=emp.first_name, last_name=emp.last_name, email=emp.email, phone=emp.phone,
            department_name=dept_name, position_title=pos_title, base_salary=float(salary),
            employment_type=emp_type, employment_status=emp.employment_status,
            username=user.username if user else None, user_id=user.user_id if user else None,
            failed_attempts=user.failed_attempts if user else 0,
            reset_requested=user.reset_requested if user else False,
            locked_until=user.locked_until if user else None,
            passcode=user.passcode if user else None,
            account_activated=user.account_activated if user else False,
            hire_date=emp.hire_date,
        ))
    return rows, total


def list_all_passcodes(session: Session) -> list[dict]:
    q = (
        select(User.username, User.passcode, User.account_activated, Employee.first_name,
               Employee.last_name, Employee.employee_code)
        .join(Employee, Employee.user_id == User.user_id)
        .where(User.role == "employee", User.is_active == True)  # noqa: E712
        .order_by(Employee.employee_id.desc())
    )
    return [
        {"username": u, "passcode": p, "account_activated": act,
         "full_name": f"{fn} {ln}", "employee_code": code}
        for u, p, act, fn, ln, code in session.execute(q).all()
    ]
