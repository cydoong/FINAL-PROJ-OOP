"""
core.auth_service
=====================
Precise Python port of includes/auth.php: login, passcode generation
and validation, account activation, OTP issue/verify, and every
password-reset flow (admin-assisted, self-service OTP, legacy
lockout self-reset).
"""
from __future__ import annotations

import random
import string
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from config.settings import get_settings
from core.audit import log_action
from core.security import hash_password, verify_password
from core.utils import clean_phone, local_ip
from database.models import Employee, User

PASSCODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I, O, 0, 1 (visually ambiguous)


@dataclass
class AuthResult:
    success: bool
    error: Optional[str] = None
    locked: bool = False
    attempts: int = 0
    reset_available: bool = False
    not_activated: bool = False
    user: Optional[User] = None
    extra: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────
#  Passcodes
# ─────────────────────────────────────────────────────────────────────────

def generate_passcode(session: Session) -> str:
    length = get_settings().otp.passcode_length
    while True:
        code = "".join(random.choice(PASSCODE_CHARS) for _ in range(length))
        exists = session.execute(select(User.user_id).where(User.passcode == code)).first()
        if not exists:
            return code


def validate_passcode(session: Session, username: str, passcode: str) -> AuthResult:
    username = (username or "").strip().lower()
    passcode = (passcode or "").strip().upper().replace("-", "")
    user = session.execute(
        select(User).where(User.username == username, User.role == "employee", User.is_active == True)  # noqa: E712
    ).scalar_one_or_none()
    if not user:
        return AuthResult(False, "Username not found or not an employee account.")
    if not user.passcode:
        return AuthResult(False, "No passcode assigned. Contact your administrator.")
    if user.passcode.upper() != passcode:
        return AuthResult(False, "Invalid passcode. Please check and try again.")
    return AuthResult(True, user=user)


# ─────────────────────────────────────────────────────────────────────────
#  Login
# ─────────────────────────────────────────────────────────────────────────

def login_user(session: Session, username: str, password: str) -> AuthResult:
    max_failed = get_settings().max_failed_logins
    user = session.execute(
        select(User).where(User.username == username, User.is_active == True)  # noqa: E712
    ).scalar_one_or_none()

    if not user:
        log_action(session, None, "FAILED_LOGIN", "users", None, None, f"unknown_user:{username}", local_ip())
        return AuthResult(False, "Invalid credentials.")

    if user.locked_until and user.locked_until > datetime.now():
        return AuthResult(False, "Account temporarily locked.", locked=True,
                           attempts=user.failed_attempts, reset_available=True)

    if user.role == "employee" and not user.account_activated:
        return AuthResult(False, 'Your account has not been activated yet. Please use "Activate Account" with your passcode.',
                           not_activated=True)

    if not verify_password(password, user.password):
        new_attempts = (user.failed_attempts or 0) + 1
        lock_until = None
        if new_attempts >= max_failed:
            lock_until = datetime.now() + timedelta(minutes=30)
        user.failed_attempts = new_attempts
        user.locked_until = lock_until
        log_action(session, user.user_id, "FAILED_LOGIN", "users", user.user_id, None, f"attempt:{new_attempts}")
        reset_avail = new_attempts >= max_failed
        if reset_avail:
            log_action(session, user.user_id, "PASSWORD_RESET_REQ", "users", user.user_id, None,
                       f"auto_after_{new_attempts}_fails")
            user.reset_requested = True
        session.flush()
        return AuthResult(False, "Invalid credentials.", locked=reset_avail,
                           attempts=new_attempts, reset_available=reset_avail)

    # Success
    user.failed_attempts = 0
    user.locked_until = None
    user.reset_requested = False
    session.flush()

    emp = session.execute(select(Employee).where(Employee.user_id == user.user_id)).scalar_one_or_none()
    full_name = emp.full_name if emp else user.username

    log_action(session, user.user_id, "LOGIN", "users", user.user_id, None, "success")
    return AuthResult(True, user=user, extra={
        "employee_id": emp.employee_id if emp else None,
        "full_name": full_name,
    })


# ─────────────────────────────────────────────────────────────────────────
#  Account activation
# ─────────────────────────────────────────────────────────────────────────

def activate_employee_account(session: Session, user_id: int, email: str, phone: str) -> AuthResult:
    from core.notifications import (
        notify_send_email, notify_send_sms, welcome_email_html, sms_welcome,
    )

    user = session.get(User, user_id)
    emp = session.execute(select(Employee).where(Employee.user_id == user_id)).scalar_one_or_none()
    if not user or not emp:
        return AuthResult(False, "Employee record not found.")

    email = (email or "").strip()
    phone_clean = clean_phone(phone)

    email_taken = session.execute(
        select(User.user_id).where(User.auth_email == email, User.user_id != user_id)
    ).first()
    if email_taken:
        return AuthResult(False, "This email is already linked to another account.")

    phone_taken = session.execute(
        select(User.user_id).where(User.auth_phone == phone_clean, User.user_id != user_id)
    ).first()
    if phone_taken:
        return AuthResult(False, "This phone number is already linked to another account.")

    reset_pw = get_settings().reset_default_password
    user.auth_email = email
    user.auth_phone = phone_clean
    user.account_activated = True
    user.password = hash_password(reset_pw)
    user.failed_attempts = 0
    user.locked_until = None
    emp.email = email
    emp.phone = phone_clean
    session.flush()

    full_name = emp.full_name
    username = user.username
    company = get_settings().mail.company_name

    email_result = notify_send_email(
        session, email, full_name, f"Welcome to {company} \u2014 Account Activated",
        welcome_email_html(full_name, username), "", emp.employee_id, "welcome", user_id,
    )
    sms_result = notify_send_sms(
        session, phone_clean, sms_welcome(full_name, username, company), emp.employee_id, "welcome", user_id,
    )

    log_action(session, user_id, "ACCOUNT_ACTIVATED", "users", user_id, None, f"email:{email} phone:{phone_clean}")

    return AuthResult(True, extra={
        "email_sent": email_result.success,
        "sms_sent": sms_result.success,
        "sms_skipped": sms_result.skipped,
        "email_error": email_result.error,
        "sms_error": None if sms_result.skipped else sms_result.error,
        "full_name": full_name,
        "username": username,
        "default_password": reset_pw,
    })


# ─────────────────────────────────────────────────────────────────────────
#  OTP
# ─────────────────────────────────────────────────────────────────────────

def generate_otp() -> str:
    length = get_settings().otp.otp_length
    return "".join(random.choice(string.digits) for _ in range(length))


def issue_otp(session: Session, user_id: int, channel: str = "both") -> AuthResult:
    from core.notifications import notify_send_email, notify_send_sms, otp_email_html, sms_otp

    user = session.get(User, user_id)
    if not user:
        return AuthResult(False, "User not found.")

    otp_cfg = get_settings().otp
    otp = generate_otp()
    expiry = datetime.now() + timedelta(minutes=otp_cfg.expiry_minutes)
    user.otp_code = otp
    user.otp_expires_at = expiry
    user.otp_purpose = "reset_password"
    session.flush()

    emp = session.execute(select(Employee).where(Employee.user_id == user_id)).scalar_one_or_none()
    name = emp.full_name if emp else user.username
    email = user.auth_email
    phone = user.auth_phone

    email_sent = sms_sent = False
    errors = []

    if channel != "sms" and email:
        r = notify_send_email(
            session, email, name, "PayrollPro \u2014 Your One-Time Password (OTP)",
            otp_email_html(name, otp, otp_cfg.expiry_minutes), "",
            emp.employee_id if emp else None, "otp", user_id,
        )
        email_sent = r.success
        if not r.success:
            errors.append(f"Email: {r.error}")

    if channel != "email" and phone:
        r = notify_send_sms(session, phone, sms_otp(otp, otp_cfg.expiry_minutes),
                             emp.employee_id if emp else None, "otp", user_id)
        sms_sent = r.success
        if not r.success and not r.skipped and r.error:
            errors.append(f"SMS: {r.error}")

    sms_skipped = not get_settings().sms.enabled
    if not email_sent and not sms_sent:
        msg = "; ".join(errors) if errors else (
            "Could not send OTP via email. Check your email settings in Settings \u2192 Mail."
            if sms_skipped else
            "Could not send OTP. Check email/SMS settings."
        )
        return AuthResult(False, msg)

    log_action(session, user_id, "OTP_ISSUED", "users", user_id, None, f"channel:{channel}")
    return AuthResult(True, extra={"email_sent": email_sent, "sms_sent": sms_sent})


def verify_otp(session: Session, user_id: int, entered_otp: str) -> AuthResult:
    user = session.get(User, user_id)
    if not user or not user.otp_code:
        return AuthResult(False, "No OTP found. Please request a new one.")
    if not user.otp_expires_at or user.otp_expires_at < datetime.now():
        user.otp_code = None
        user.otp_expires_at = None
        session.flush()
        return AuthResult(False, "OTP has expired. Please request a new one.")
    if user.otp_code != (entered_otp or "").strip():
        return AuthResult(False, "Incorrect OTP. Please try again.")

    user.otp_code = None
    user.otp_expires_at = None
    user.otp_purpose = None
    session.flush()
    log_action(session, user_id, "OTP_VERIFIED", "users", user_id, None, "success")
    return AuthResult(True)


# ─────────────────────────────────────────────────────────────────────────
#  Password reset flows
# ─────────────────────────────────────────────────────────────────────────

def admin_reset_employee_password(session: Session, admin_uid: Optional[int], target_uid: int,
                                   entered_passcode: str) -> AuthResult:
    entered_passcode = (entered_passcode or "").strip().upper().replace("-", "")
    user = session.execute(
        select(User).where(User.user_id == target_uid, User.role == "employee", User.is_active == True)  # noqa: E712
    ).scalar_one_or_none()
    if not user:
        return AuthResult(False, "Employee user not found.")
    if not user.passcode:
        return AuthResult(False, "No passcode on record for this employee.")
    if user.passcode.upper() != entered_passcode:
        log_action(session, admin_uid, "RESET_PASS_FAILED", "users", target_uid, None, "wrong_passcode")
        return AuthResult(False, "Incorrect passcode. Password was NOT reset.")

    reset_pw = get_settings().reset_default_password
    user.password = hash_password(reset_pw)
    user.failed_attempts = 0
    user.locked_until = None
    user.reset_requested = False
    session.flush()
    log_action(session, admin_uid, "RESET_PASSWORD", "users", target_uid, None,
               f"admin_reset_with_passcode:{user.username}")
    return AuthResult(True, extra={"default_password": reset_pw})


def find_user_for_reset(session: Session, username: str, passcode: str, contact: str) -> AuthResult:
    username = (username or "").strip().lower()
    passcode = (passcode or "").strip().upper().replace("-", "")
    contact = (contact or "").strip()

    user = session.execute(
        select(User).where(User.username == username, User.role == "employee", User.is_active == True)  # noqa: E712
    ).scalar_one_or_none()
    if not user:
        return AuthResult(False, "Username not found or not an employee account.")
    if not user.passcode or user.passcode.upper() != passcode:
        return AuthResult(False, "Incorrect passcode.")
    if not user.account_activated:
        return AuthResult(False, 'Account not yet activated. Please use "Activate Account" first.')

    email_match = bool(user.auth_email) and user.auth_email.lower() == contact.lower()
    phone_clean = clean_phone(contact)
    phone_match = bool(user.auth_phone) and clean_phone(user.auth_phone) == phone_clean

    if not email_match and not phone_match:
        return AuthResult(False, "The contact info provided does not match records on file.")

    channel = "email" if (email_match and not phone_match) else ("both" if (email_match and phone_match) else "sms")
    return AuthResult(True, extra={"user_id": user.user_id, "channel": channel})


def reset_password_final(session: Session, user_id: int, new_password: str) -> AuthResult:
    if len(new_password or "") < 6:
        return AuthResult(False, "Password must be at least 6 characters.")
    user = session.get(User, user_id)
    if not user:
        return AuthResult(False, "User not found.")
    user.password = hash_password(new_password)
    user.failed_attempts = 0
    user.locked_until = None
    user.reset_requested = False
    session.flush()
    log_action(session, user_id, "RESET_PASSWORD", "users", user_id, None, "self_otp_reset")
    return AuthResult(True)


def employee_check_passcode(session: Session, user_id: int, entered_passcode: str) -> bool:
    entered_passcode = (entered_passcode or "").strip().upper().replace("-", "")
    user = session.get(User, user_id)
    if not user or not user.passcode:
        return False
    return user.passcode.upper() == entered_passcode


def employee_self_reset(session: Session, username: str) -> AuthResult:
    """Legacy: reset to default password after lockout, no passcode required."""
    max_failed = get_settings().max_failed_logins
    username = (username or "").strip().lower()
    user = session.execute(
        select(User).where(User.username == username, User.role == "employee", User.is_active == True)  # noqa: E712
    ).scalar_one_or_none()
    if not user:
        return AuthResult(False, "Username not found or not an employee account.")
    if (user.failed_attempts or 0) < max_failed and not user.locked_until:
        return AuthResult(False, f"Password reset is only available after {max_failed} failed login attempts.")

    reset_pw = get_settings().reset_default_password
    user.password = hash_password(reset_pw)
    user.failed_attempts = 0
    user.locked_until = None
    user.reset_requested = False
    session.flush()
    log_action(session, user.user_id, "RESET_PASSWORD", "users", user.user_id, None, "self_reset_to_default")
    return AuthResult(True, extra={"default_password": reset_pw})
