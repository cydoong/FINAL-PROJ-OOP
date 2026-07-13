"""
core.utils
============
Small formatting / validation helpers used throughout the app —
equivalents of format_currency()/format_date() from includes/db.php
and the passcode formatter from includes/auth.php.
"""
from __future__ import annotations

import re
import socket
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Union

Number = Union[int, float, Decimal]


def format_currency(value: Optional[Number]) -> str:
    if value is None:
        value = 0
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0
    return f"\u20b1{value:,.2f}"  # ₱


def format_date(value) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, (datetime, date)):
        # Build manually instead of using the %-d / %#d "no leading zero"
        # flag: %-d is a Linux/Mac (glibc) extension and %#d is the
        # Windows equivalent — using either one crashes on the other
        # platform. value.day sidesteps the whole problem.
        return f"{value.strftime('%b')} {value.day}, {value.year}"
    return str(value)


def format_datetime(value) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, datetime):
        return f"{value.strftime('%b')} {value.day}, {value.year} {value.strftime('%I:%M %p')}"
    return str(value)


def format_time(value) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, datetime):
        return value.strftime("%I:%M %p").lstrip("0") or value.strftime("%I:%M %p")
    return str(value)


def format_passcode(code: Optional[str]) -> str:
    """Format an 8-char passcode with a dash in the middle: ABCD1234 -> ABCD-1234"""
    if not code:
        return "—"
    half = len(code) // 2
    return f"{code[:half]}-{code[half:]}"


def clean_passcode_input(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()


def clean_phone(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def is_valid_ph_mobile(phone: str) -> bool:
    cleaned = clean_phone(phone)
    return len(cleaned) == 11 and cleaned.startswith("0")


def is_valid_email(email: str) -> bool:
    if not email:
        return False
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()) is not None


def is_valid_username(username: str) -> bool:
    return bool(re.match(r"^[a-z0-9._]+$", username or ""))


def title_case_status(status: str) -> str:
    return (status or "").replace("_", " ").title()


def local_ip() -> str:
    """Best-effort 'IP address' equivalent for audit logs on a desktop app."""
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:  # noqa: BLE001
        return "local"


def to_decimal(value, default: str = "0") -> Decimal:
    try:
        if value in (None, ""):
            return Decimal(default)
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return Decimal(default)
