"""
core.profile_service
========================
Employee self-service profile actions, exact port of
user/my_profile.php: update name, update contact/banking info,
change username (passcode-gated), change password (passcode-gated).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.audit import log_action
from core.auth_service import employee_check_passcode
from core.security import hash_password, verify_password
from core.utils import clean_phone, is_valid_username
from database.models import Employee, User


@dataclass
class ServiceResult:
    success: bool
    error: Optional[str] = None
    data: Optional[dict] = None


def update_name(session: Session, employee_id: int, first: str, last: str, middle: str,
                 user_id: Optional[int]) -> ServiceResult:
    first, last, middle = first.strip(), last.strip(), middle.strip()
    if not first or not last:
        return ServiceResult(False, "First and last name are required.")
    emp = session.get(Employee, employee_id)
    if not emp:
        return ServiceResult(False, "Employee record not found.")
    emp.first_name, emp.last_name, emp.middle_name = first, last, middle or None
    session.flush()
    log_action(session, user_id, "UPDATE_NAME", "employees", employee_id, None, f"{first} {last}")
    return ServiceResult(True)


def update_profile(session: Session, employee_id: int, phone: str, address: str, bank_name: str,
                    bank_account: str, user_id: Optional[int],
                    payment_method: str = "bank_transfer", gcash_number: str = "",
                    maya_number: str = "") -> ServiceResult:
    phone_clean = clean_phone(phone)
    if phone_clean and len(phone_clean) != 11:
        return ServiceResult(False, "Phone number must be exactly 11 digits.")
    method = (payment_method or "bank_transfer").strip().lower()
    from core.utils import is_valid_ph_mobile
    if method == "gcash" and not is_valid_ph_mobile(gcash_number):
        return ServiceResult(False, "A valid 11-digit GCash number is required.")
    if method == "maya" and not is_valid_ph_mobile(maya_number):
        return ServiceResult(False, "A valid 11-digit Maya number is required.")
    if method == "bank_transfer" and not bank_name.strip():
        return ServiceResult(False, "Bank name is required for Bank Transfer.")
    emp = session.get(Employee, employee_id)
    if not emp:
        return ServiceResult(False, "Employee record not found.")
    emp.phone = phone_clean or None
    emp.address = address.strip() or None
    emp.bank_name = bank_name.strip() or None
    emp.bank_account = bank_account.strip() or None
    emp.payment_method = method
    emp.gcash_number = clean_phone(gcash_number) or None
    emp.maya_number = clean_phone(maya_number) or None
    session.flush()
    log_action(session, user_id, "UPDATE_PROFILE", "employees", employee_id, None, "phone/address/payment method updated")
    return ServiceResult(True)


def change_username(session: Session, user_id: int, entered_passcode: str, new_username: str) -> ServiceResult:
    if not entered_passcode:
        return ServiceResult(False, "Passcode is required to change your username.")
    if not employee_check_passcode(session, user_id, entered_passcode):
        log_action(session, user_id, "CHANGE_USERNAME_FAIL", "users", user_id, None, "wrong_passcode")
        return ServiceResult(False, "Incorrect passcode. Username was NOT changed.")

    new_username = (new_username or "").strip().lower()
    if not new_username:
        return ServiceResult(False, "Username cannot be empty.")
    if not is_valid_username(new_username):
        return ServiceResult(False, "Username may only contain lowercase letters, numbers, dots, and underscores.")
    taken = session.execute(
        select(User.user_id).where(User.username == new_username, User.user_id != user_id)
    ).first()
    if taken:
        return ServiceResult(False, f'The username "{new_username}" is already taken.')

    user = session.get(User, user_id)
    old_username = user.username
    user.username = new_username
    session.flush()
    log_action(session, user_id, "CHANGE_USERNAME", "users", user_id, old_username, new_username)
    return ServiceResult(True, data={"new_username": new_username})


def change_password(session: Session, user_id: int, entered_passcode: str, current_password: str,
                     new_password: str, confirm_password: str) -> ServiceResult:
    if not entered_passcode:
        return ServiceResult(False, "Passcode is required to change your password.")
    if not employee_check_passcode(session, user_id, entered_passcode):
        log_action(session, user_id, "CHANGE_PASSWORD_FAIL", "users", user_id, None, "wrong_passcode")
        return ServiceResult(False, "Incorrect passcode. Password was NOT changed.")

    user = session.get(User, user_id)
    if not user or not verify_password(current_password, user.password):
        return ServiceResult(False, "Current password is incorrect.")
    if new_password != confirm_password:
        return ServiceResult(False, "New passwords do not match.")
    if len(new_password) < 6:
        return ServiceResult(False, "Password must be at least 6 characters.")

    user.password = hash_password(new_password)
    session.flush()
    log_action(session, user_id, "CHANGE_PASSWORD", "users", user_id, None, None)
    return ServiceResult(True)
