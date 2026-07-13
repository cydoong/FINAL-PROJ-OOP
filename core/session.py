"""
core.session
==============
A desktop app doesn't have HTTP sessions, but the original PHP code
leans heavily on `$_SESSION` to track who's logged in, their role,
and short-lived flows (activation wizard, password-reset wizard,
flash messages). `AppSession` is the in-memory equivalent — a single
object living for the lifetime of the running application.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AppSession:
    user_id: Optional[int] = None
    username: Optional[str] = None
    role: Optional[str] = None          # 'admin' or 'employee'
    employee_id: Optional[int] = None
    full_name: Optional[str] = None

    # Scratch space for multi-step wizards (activation / password reset),
    # mirroring the transient $_SESSION keys used in activate.php /
    # forgot_password.php.
    scratch: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    def is_logged_in(self) -> bool:
        return self.user_id is not None

    def is_admin(self) -> bool:
        return self.is_logged_in() and self.role == "admin"

    def login(self, user_id: int, username: str, role: str,
              employee_id: Optional[int] = None, full_name: Optional[str] = None) -> None:
        self.user_id = user_id
        self.username = username
        self.role = role
        self.employee_id = employee_id
        self.full_name = full_name or username

    def logout(self) -> None:
        self.user_id = None
        self.username = None
        self.role = None
        self.employee_id = None
        self.full_name = None
        self.scratch.clear()

    def initials(self) -> str:
        name = self.full_name or self.username or "U"
        return name.strip()[:1].upper() if name.strip() else "U"


# Process-wide singleton — one logged-in user at a time, exactly like a
# single-user desktop application session.
current_session = AppSession()
