"""
ui.login_window
==================
The pre-login screen: a branded split layout (gradient panel + form
panel) with three flows, exactly mirroring index.php, activate.php
and forgot_password.php:

    * Login
    * Activate Account (passcode -> email/phone -> done)
    * Forgot Password (passcode+contact -> OTP -> new password)
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from config.settings import get_settings
from core.session import current_session
from database.db_manager import get_db
from ui import theme
from ui.widgets.common import make_button


PASSCODE_PLACEHOLDER = "ABCD-1234"


def _pw_field() -> QLineEdit:
    e = QLineEdit()
    e.setEchoMode(QLineEdit.EchoMode.Password)
    e.setMinimumHeight(40)
    return e


def _text_field(placeholder: str = "") -> QLineEdit:
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setMinimumHeight(40)
    return e


class BrandPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(380)
        self.setStyleSheet(f"""
            QFrame {{
                background: {theme.BRAND_GRADIENT};
                border-right: 1px solid {theme.BORDER};
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 60, 48, 48)
        lay.addStretch(1)

        logo = QLabel("\U0001F4BC")
        logo.setStyleSheet(f"font-size: 46px; background: {theme.rgba(theme.PINK, 0.14)}; border-radius: 20px; "
                            f"padding: 14px; max-width: 30px;")
        logo.setFixedSize(78, 78)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)

        lay.addSpacing(24)
        title = QLabel("PayrollPro")
        title.setStyleSheet("font-size: 32px; font-weight: 900; color: #ffffff;")
        lay.addWidget(title)

        sub = QLabel("Payroll & Workforce Management")
        sub.setStyleSheet(f"font-size: 13px; color: {theme.PINK}; font-weight: 700; "
                           f"text-transform: uppercase; letter-spacing: 0.08em;")
        lay.addWidget(sub)

        lay.addSpacing(28)
        desc = QLabel("Manage employees, run payroll, and keep every payslip, "
                       "department, and audit trail in one secure desktop app.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 13px; line-height: 160%;")
        lay.addWidget(desc)

        lay.addSpacing(36)
        for icon, text in [
            ("\U0001F4B0", "Automated payroll & payslips"),
            ("\U0001F510", "Secure passcode-based activation"),
            ("\U0001F4CA", "Real-time reports & analytics"),
            ("\U0001F5C4\uFE0F", "Works with SQLite or your XAMPP MySQL"),
        ]:
            row = QHBoxLayout()
            ic = QLabel(icon)
            ic.setStyleSheet("font-size: 16px;")
            ic.setFixedWidth(28)
            row.addWidget(ic)
            t = QLabel(text)
            t.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 12.5px;")
            row.addWidget(t)
            row.addStretch()
            lay.addLayout(row)
            lay.addSpacing(8)

        lay.addStretch(2)
        ver = QLabel("PayrollPro Python Edition \u00b7 v7.0")
        ver.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        lay.addWidget(ver)


class LoginPage(QWidget):
    submit_login = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(6)

        title = QLabel("Welcome back")
        title.setStyleSheet(f"font-size: 24px; font-weight: 800; color: {theme.TEXT_STRONG};")
        lay.addWidget(title)
        sub = QLabel("Sign in to your PayrollPro account")
        sub.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 13px;")
        lay.addWidget(sub)
        lay.addSpacing(20)

        lay.addWidget(QLabel("Username"))
        self.username = _text_field("your.username")
        lay.addWidget(self.username)
        lay.addSpacing(10)

        lay.addWidget(QLabel("Password"))
        self.password = _pw_field()
        self.password.returnPressed.connect(self._submit)
        lay.addWidget(self.password)
        lay.addSpacing(6)

        self.error_lbl = QLabel("")
        self.error_lbl.setProperty("role", "error")
        self.error_lbl.setWordWrap(True)
        self.error_lbl.setVisible(False)
        lay.addWidget(self.error_lbl)

        lay.addSpacing(8)
        self.login_btn = make_button("Sign In", "primary")
        self.login_btn.setMinimumHeight(42)
        self.login_btn.clicked.connect(self._submit)
        lay.addWidget(self.login_btn)

        lay.addSpacing(18)
        hint = QLabel("Default admin login: <b>admin</b> / <b>admin123</b> (fresh install)")
        hint.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addStretch()

    def _submit(self):
        self.error_lbl.setVisible(False)
        if not self.username.text().strip() or not self.password.text():
            self.show_error("Please enter your username and password.")
            return
        self.submit_login.emit(self.username.text().strip(), self.password.text())

    def show_error(self, msg: str):
        self.error_lbl.setText("\u26A0  " + msg)
        self.error_lbl.setVisible(True)


class ActivatePage(QWidget):
    validate_passcode = pyqtSignal(str, str)
    do_activate = pyqtSignal(int, str, str)
    back_to_login = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pending_user_id = None
        self.stack = QStackedWidget()
        lay = QVBoxLayout(self)

        title = QLabel("Activate Your Account")
        title.setStyleSheet(f"font-size: 24px; font-weight: 800; color: {theme.TEXT_STRONG};")
        lay.addWidget(title)
        sub = QLabel("Use the passcode provided by your HR administrator")
        sub.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 13px;")
        lay.addWidget(sub)
        lay.addSpacing(16)
        lay.addWidget(self.stack)

        # Step 1: username + passcode
        step1 = QWidget()
        s1 = QVBoxLayout(step1)
        s1.setContentsMargins(0, 0, 0, 0)
        s1.addWidget(QLabel("Username"))
        self.act_username = _text_field("your.username")
        s1.addWidget(self.act_username)
        s1.addSpacing(10)
        s1.addWidget(QLabel("Passcode"))
        self.act_passcode = _text_field(PASSCODE_PLACEHOLDER)
        s1.addWidget(self.act_passcode)
        self.err1 = QLabel("")
        self.err1.setProperty("role", "error")
        self.err1.setWordWrap(True)
        self.err1.setVisible(False)
        s1.addWidget(self.err1)
        s1.addSpacing(8)
        next_btn = make_button("Verify Passcode", "primary")
        next_btn.setMinimumHeight(42)
        next_btn.clicked.connect(self._submit_step1)
        s1.addWidget(next_btn)
        s1.addStretch()
        self.stack.addWidget(step1)

        # Step 2: email + phone
        step2 = QWidget()
        s2 = QVBoxLayout(step2)
        s2.setContentsMargins(0, 0, 0, 0)
        self.step2_welcome = QLabel("")
        self.step2_welcome.setStyleSheet(f"color: {theme.SUCCESS}; font-weight: 700;")
        self.step2_welcome.setWordWrap(True)
        s2.addWidget(self.step2_welcome)
        s2.addSpacing(8)
        s2.addWidget(QLabel("Personal Email"))
        self.act_email = _text_field("you@example.com")
        s2.addWidget(self.act_email)
        s2.addSpacing(10)
        s2.addWidget(QLabel("Mobile Number"))
        self.act_phone = _text_field("09171234567")
        s2.addWidget(self.act_phone)
        self.err2 = QLabel("")
        self.err2.setProperty("role", "error")
        self.err2.setWordWrap(True)
        self.err2.setVisible(False)
        s2.addWidget(self.err2)
        s2.addSpacing(8)
        activate_btn = make_button("Activate Account", "primary")
        activate_btn.setMinimumHeight(42)
        activate_btn.clicked.connect(self._submit_step2)
        s2.addWidget(activate_btn)
        s2.addStretch()
        self.stack.addWidget(step2)

        # Step 3: done
        step3 = QWidget()
        s3 = QVBoxLayout(step3)
        s3.setContentsMargins(0, 0, 0, 0)
        done_icon = QLabel("\u2705")
        done_icon.setStyleSheet("font-size: 40px;")
        s3.addWidget(done_icon)
        self.done_msg = QLabel("")
        self.done_msg.setWordWrap(True)
        self.done_msg.setStyleSheet(f"color: {theme.TEXT}; font-size: 13px; line-height:150%;")
        s3.addWidget(self.done_msg)
        s3.addSpacing(12)
        back_btn = make_button("Back to Login", "primary")
        back_btn.setMinimumHeight(42)
        back_btn.clicked.connect(lambda: self.back_to_login.emit())
        s3.addWidget(back_btn)
        s3.addStretch()
        self.stack.addWidget(step3)

        lay.addStretch()

    def reset(self):
        self.stack.setCurrentIndex(0)
        self.act_username.clear()
        self.act_passcode.clear()
        self.act_email.clear()
        self.act_phone.clear()
        self.err1.setVisible(False)
        self.err2.setVisible(False)

    def _submit_step1(self):
        self.err1.setVisible(False)
        u = self.act_username.text().strip()
        p = self.act_passcode.text().strip()
        if not u or not p:
            self.show_error1("Please enter both your username and passcode.")
            return
        self.validate_passcode.emit(u, p)

    def show_error1(self, msg: str):
        self.err1.setText("\u26A0  " + msg)
        self.err1.setVisible(True)

    def on_passcode_valid(self, user_id: int, full_name: str, existing_email: str = "", existing_phone: str = ""):
        self.pending_user_id = user_id
        if existing_email or existing_phone:
            self.step2_welcome.setText(
                f"Welcome, {full_name}! We've pre-filled the contact info HR already has on file — "
                f"feel free to change it if you'd rather use something else."
            )
        else:
            self.step2_welcome.setText(f"Welcome, {full_name}! Now let's set up your contact info.")
        self.act_email.setText(existing_email)
        self.act_phone.setText(existing_phone)
        self.stack.setCurrentIndex(1)

    def _submit_step2(self):
        self.err2.setVisible(False)
        email = self.act_email.text().strip()
        phone = self.act_phone.text().strip()
        if not email or not phone:
            self.show_error2("Please provide both an email and a mobile number.")
            return
        self.do_activate.emit(self.pending_user_id, email, phone)

    def show_error2(self, msg: str):
        self.err2.setText("\u26A0  " + msg)
        self.err2.setVisible(True)

    def on_activated(self, username: str, default_password: str, email_ok: bool, sms_ok: bool):
        msg = (f"<b>{username}</b> is now active!<br><br>"
               f"Your temporary password is <b>{default_password}</b> "
               f"(please change it after logging in from My Profile).<br><br>")
        if email_ok:
            msg += "\u2713 A welcome email was sent.<br>"
        if sms_ok:
            msg += "\u2713 A welcome SMS was sent.<br>"
        self.done_msg.setText(msg)
        self.stack.setCurrentIndex(2)


class ForgotPasswordPage(QWidget):
    do_find_user = pyqtSignal(str, str, str)
    do_verify_otp = pyqtSignal(int, str)
    do_reset = pyqtSignal(int, str)
    resend_otp = pyqtSignal(int)
    back_to_login = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pending_user_id = None
        self.stack = QStackedWidget()
        lay = QVBoxLayout(self)

        title = QLabel("Reset Your Password")
        title.setStyleSheet(f"font-size: 24px; font-weight: 800; color: {theme.TEXT_STRONG};")
        lay.addWidget(title)
        sub = QLabel("Verify your identity to receive a one-time password")
        sub.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 13px;")
        lay.addWidget(sub)
        lay.addSpacing(16)
        lay.addWidget(self.stack)

        # Step 1
        step1 = QWidget()
        s1 = QVBoxLayout(step1)
        s1.setContentsMargins(0, 0, 0, 0)
        s1.addWidget(QLabel("Username"))
        self.fp_username = _text_field("your.username")
        s1.addWidget(self.fp_username)
        s1.addSpacing(10)
        s1.addWidget(QLabel("Passcode"))
        self.fp_passcode = _text_field(PASSCODE_PLACEHOLDER)
        s1.addWidget(self.fp_passcode)
        s1.addSpacing(10)
        s1.addWidget(QLabel("Registered Email or Mobile Number"))
        self.fp_contact = _text_field("email@example.com or 09171234567")
        s1.addWidget(self.fp_contact)
        self.fp_err1 = QLabel("")
        self.fp_err1.setProperty("role", "error")
        self.fp_err1.setWordWrap(True)
        self.fp_err1.setVisible(False)
        s1.addWidget(self.fp_err1)
        s1.addSpacing(8)
        send_btn = make_button("Send OTP", "primary")
        send_btn.setMinimumHeight(42)
        send_btn.clicked.connect(self._submit_step1)
        s1.addWidget(send_btn)
        s1.addStretch()
        self.stack.addWidget(step1)

        # Step 2: OTP
        step2 = QWidget()
        s2 = QVBoxLayout(step2)
        s2.setContentsMargins(0, 0, 0, 0)
        self.otp_info = QLabel("")
        self.otp_info.setWordWrap(True)
        self.otp_info.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 12.5px;")
        s2.addWidget(self.otp_info)
        s2.addSpacing(8)
        s2.addWidget(QLabel("Enter OTP Code"))
        self.otp_code = _text_field("123456")
        s2.addWidget(self.otp_code)
        self.fp_err2 = QLabel("")
        self.fp_err2.setProperty("role", "error")
        self.fp_err2.setWordWrap(True)
        self.fp_err2.setVisible(False)
        s2.addWidget(self.fp_err2)
        s2.addSpacing(8)
        verify_btn = make_button("Verify OTP", "primary")
        verify_btn.setMinimumHeight(42)
        verify_btn.clicked.connect(self._submit_otp)
        s2.addWidget(verify_btn)
        resend_btn = make_button("Resend OTP", "ghost")
        resend_btn.clicked.connect(lambda: self.resend_otp.emit(self.pending_user_id))
        s2.addWidget(resend_btn)
        s2.addStretch()
        self.stack.addWidget(step2)

        # Step 3: new password
        step3 = QWidget()
        s3 = QVBoxLayout(step3)
        s3.setContentsMargins(0, 0, 0, 0)
        s3.addWidget(QLabel("New Password"))
        self.new_pw1 = _pw_field()
        s3.addWidget(self.new_pw1)
        s3.addSpacing(10)
        s3.addWidget(QLabel("Confirm New Password"))
        self.new_pw2 = _pw_field()
        s3.addWidget(self.new_pw2)
        self.fp_err3 = QLabel("")
        self.fp_err3.setProperty("role", "error")
        self.fp_err3.setWordWrap(True)
        self.fp_err3.setVisible(False)
        s3.addWidget(self.fp_err3)
        s3.addSpacing(8)
        reset_btn = make_button("Reset Password", "primary")
        reset_btn.setMinimumHeight(42)
        reset_btn.clicked.connect(self._submit_reset)
        s3.addWidget(reset_btn)
        s3.addStretch()
        self.stack.addWidget(step3)

        # Step 4: done
        step4 = QWidget()
        s4 = QVBoxLayout(step4)
        s4.setContentsMargins(0, 0, 0, 0)
        done_icon = QLabel("\u2705")
        done_icon.setStyleSheet("font-size: 40px;")
        s4.addWidget(done_icon)
        done_lbl = QLabel("Your password has been reset successfully. You may now sign in.")
        done_lbl.setWordWrap(True)
        s4.addWidget(done_lbl)
        s4.addSpacing(12)
        back_btn2 = make_button("Back to Login", "primary")
        back_btn2.setMinimumHeight(42)
        back_btn2.clicked.connect(lambda: self.back_to_login.emit())
        s4.addWidget(back_btn2)
        s4.addStretch()
        self.stack.addWidget(step4)

        lay.addStretch()

    def reset(self):
        self.stack.setCurrentIndex(0)
        for f in (self.fp_username, self.fp_passcode, self.fp_contact, self.otp_code, self.new_pw1, self.new_pw2):
            f.clear()
        self.fp_err1.setVisible(False)
        self.fp_err2.setVisible(False)
        self.fp_err3.setVisible(False)

    def _submit_step1(self):
        self.fp_err1.setVisible(False)
        u, p, c = self.fp_username.text().strip(), self.fp_passcode.text().strip(), self.fp_contact.text().strip()
        if not u or not p or not c:
            self.show_error1("Please fill in all fields.")
            return
        self.do_find_user.emit(u, p, c)

    def show_error1(self, msg: str):
        self.fp_err1.setText("\u26A0  " + msg)
        self.fp_err1.setVisible(True)

    def on_otp_sent(self, user_id: int, email_sent: bool, sms_sent: bool):
        self.pending_user_id = user_id
        parts = []
        if email_sent:
            parts.append("email")
        if sms_sent:
            parts.append("SMS")
        via = " and ".join(parts) if parts else "your registered contact"
        self.otp_info.setText(f"A one-time password was sent via {via}. It expires in "
                               f"{get_settings().otp.expiry_minutes} minutes.")
        self.stack.setCurrentIndex(1)

    def _submit_otp(self):
        self.fp_err2.setVisible(False)
        if not self.otp_code.text().strip():
            self.show_error2("Please enter the OTP code.")
            return
        self.do_verify_otp.emit(self.pending_user_id, self.otp_code.text().strip())

    def show_error2(self, msg: str):
        self.fp_err2.setText("\u26A0  " + msg)
        self.fp_err2.setVisible(True)

    def on_otp_verified(self):
        self.stack.setCurrentIndex(2)

    def _submit_reset(self):
        self.fp_err3.setVisible(False)
        p1, p2 = self.new_pw1.text(), self.new_pw2.text()
        if len(p1) < 6:
            self.show_error3("Password must be at least 6 characters.")
            return
        if p1 != p2:
            self.show_error3("Passwords do not match.")
            return
        self.do_reset.emit(self.pending_user_id, p1)

    def show_error3(self, msg: str):
        self.fp_err3.setText("\u26A0  " + msg)
        self.fp_err3.setVisible(True)

    def on_reset_done(self):
        self.stack.setCurrentIndex(3)


class LoginWindow(QWidget):
    """Top-level pre-auth widget: branding panel + tabbed auth forms."""
    login_success = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(BrandPanel())

        right = QFrame()
        right.setStyleSheet(f"background-color: {theme.BG_DARK};")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(56, 40, 56, 40)

        # Tab switcher
        tabs_row = QHBoxLayout()
        self.tab_buttons: dict[str, QPushButton] = {}
        for key, label in [("login", "Sign In"), ("activate", "Activate Account"), ("forgot", "Forgot Password")]:
            b = make_button(label, "ghost")
            b.setCheckable(True)
            b.clicked.connect(lambda _, k=key: self._switch_tab(k))
            tabs_row.addWidget(b)
            self.tab_buttons[key] = b
        right_lay.addLayout(tabs_row)
        right_lay.addSpacing(24)

        self.stack = QStackedWidget()
        self.login_page = LoginPage()
        self.activate_page = ActivatePage()
        self.forgot_page = ForgotPasswordPage()
        self.stack.addWidget(self.login_page)
        self.stack.addWidget(self.activate_page)
        self.stack.addWidget(self.forgot_page)
        right_lay.addWidget(self.stack, 1)

        root.addWidget(right, 1)

        # pyqtSignal wiring
        self.login_page.submit_login.connect(self._handle_login)
        self.activate_page.validate_passcode.connect(self._handle_validate_passcode)
        self.activate_page.do_activate.connect(self._handle_activate)
        self.activate_page.back_to_login.connect(lambda: self._switch_tab("login"))
        self.forgot_page.do_find_user.connect(self._handle_find_user)
        self.forgot_page.do_verify_otp.connect(self._handle_verify_otp)
        self.forgot_page.do_reset.connect(self._handle_reset)
        self.forgot_page.resend_otp.connect(self._handle_resend_otp)
        self.forgot_page.back_to_login.connect(lambda: self._switch_tab("login"))

        self._switch_tab("login")

    def _switch_tab(self, key: str):
        for k, b in self.tab_buttons.items():
            b.setChecked(k == key)
        index = {"login": 0, "activate": 1, "forgot": 2}[key]
        self.stack.setCurrentIndex(index)
        if key == "activate":
            self.activate_page.reset()
        elif key == "forgot":
            self.forgot_page.reset()

    # ------------------------------------------------------------------
    def _handle_login(self, username: str, password: str):
        import core.auth_service as auth
        db = get_db()
        with db.session() as s:
            result = auth.login_user(s, username, password)
            if result.success:
                user = result.user
                current_session.login(
                    user_id=user.user_id, username=user.username, role=user.role,
                    employee_id=result.extra.get("employee_id"), full_name=result.extra.get("full_name"),
                )
        if not result.success:
            msg = result.error or "Invalid credentials."
            if result.locked:
                msg += " Too many failed attempts \u2014 use Forgot Password to reset, or wait 30 minutes."
            self.login_page.show_error(msg)
            return
        self.login_success.emit()

    def _handle_validate_passcode(self, username: str, passcode: str):
        import core.auth_service as auth
        from sqlalchemy import select
        from database.models import Employee
        db = get_db()
        with db.session() as s:
            result = auth.validate_passcode(s, username, passcode)
            if result.success:
                emp = s.execute(select(Employee).where(Employee.user_id == result.user.user_id)).scalar_one_or_none()
                full_name = emp.full_name if emp else username
                uid = result.user.user_id
                # If HR already put an email/phone on file for this
                # employee when adding them, pre-fill activation with
                # those values instead of making the employee retype
                # contact info HR already has — still editable, just
                # defaulted, and only pre-filled when actually present.
                existing_email = emp.email if emp and emp.email else ""
                existing_phone = emp.phone if emp and emp.phone else ""
                self.activate_page.on_passcode_valid(uid, full_name, existing_email, existing_phone)
                return
        self.activate_page.show_error1(result.error or "Invalid passcode.")

    def _handle_activate(self, user_id: int, email: str, phone: str):
        import core.auth_service as auth
        db = get_db()
        with db.session() as s:
            result = auth.activate_employee_account(s, user_id, email, phone)
        if not result.success:
            self.activate_page.show_error2(result.error or "Activation failed.")
            return
        self.activate_page.on_activated(
            result.extra["username"], result.extra["default_password"],
            result.extra["email_sent"], result.extra["sms_sent"],
        )

    def _handle_find_user(self, username: str, passcode: str, contact: str):
        import core.auth_service as auth
        db = get_db()
        with db.session() as s:
            result = auth.find_user_for_reset(s, username, passcode, contact)
            if not result.success:
                self.forgot_page.show_error1(result.error or "Verification failed.")
                return
            user_id = result.extra["user_id"]
            channel = result.extra["channel"]
            otp_result = auth.issue_otp(s, user_id, channel)
        if not otp_result.success:
            self.forgot_page.show_error1(otp_result.error or "Could not send OTP.")
            return
        self.forgot_page.on_otp_sent(user_id, otp_result.extra.get("email_sent", False),
                                      otp_result.extra.get("sms_sent", False))

    def _handle_resend_otp(self, user_id: int):
        import core.auth_service as auth
        db = get_db()
        with db.session() as s:
            result = auth.issue_otp(s, user_id, "both")
        if result.success:
            self.forgot_page.on_otp_sent(user_id, result.extra.get("email_sent", False),
                                          result.extra.get("sms_sent", False))
        else:
            self.forgot_page.show_error2(result.error or "Could not resend OTP.")

    def _handle_verify_otp(self, user_id: int, otp: str):
        import core.auth_service as auth
        db = get_db()
        with db.session() as s:
            result = auth.verify_otp(s, user_id, otp)
        if result.success:
            self.forgot_page.on_otp_verified()
        else:
            self.forgot_page.show_error2(result.error or "Invalid OTP.")

    def _handle_reset(self, user_id: int, new_password: str):
        import core.auth_service as auth
        db = get_db()
        with db.session() as s:
            result = auth.reset_password_final(s, user_id, new_password)
        if result.success:
            self.forgot_page.on_reset_done()
        else:
            self.forgot_page.show_error3(result.error or "Could not reset password.")
