"""
ui.main_window
=================
The post-login application shell: sidebar navigation (role-aware),
topbar with user menu, and a QStackedWidget content area. Pages are
created lazily and cached so switching is instant after first visit.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QPushButton,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from core.session import current_session
from database.db_manager import get_db
from ui import theme
from ui.widgets.common import make_button

ADMIN_NAV = [
    ("dashboard", "\U0001F3E0", "Dashboard"),
    ("employees", "\U0001F465", "Employees"),
    ("departments", "\U0001F3E2", "Departments"),
    ("positions", "\U0001F4BC", "Positions"),
    ("pay_periods", "\U0001F4C5", "Pay Periods"),
    ("attendance", "\U0001F4C6", "Attendance"),
    ("payroll", "\U0001F4B0", "Payroll"),
    ("allowances", "\u2795", "Allowances & Deductions"),
    ("reports", "\U0001F4C8", "Reports"),
    ("notifications", "\U0001F514", "Notifications"),
    ("audit_log", "\U0001F4DC", "Audit Log"),
    ("archive", "\U0001F5C4\uFE0F", "Archive"),
]

EMPLOYEE_NAV = [
    ("emp_dashboard", "\U0001F3E0", "Dashboard"),
    ("emp_payslips", "\U0001F4C4", "My Payslips"),
    ("emp_attendance", "\U0001F4C6", "My Attendance"),
    ("emp_profile", "\U0001F464", "My Profile"),
]


class Sidebar(QFrame):
    nav_selected = pyqtSignal(str)
    logout_requested = pyqtSignal()

    def __init__(self, nav_items, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(240)
        self.nav_items = nav_items
        self.buttons: dict = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 20, 16, 16)
        lay.setSpacing(4)

        brand = QHBoxLayout()
        logo = QLabel("\U0001F4BC")
        logo.setStyleSheet(f"font-size: 20px; background: {theme.rgba(theme.PINK, 0.14)}; border-radius: 10px; "
                            f"padding: 6px 8px;")
        brand.addWidget(logo)
        title = QLabel("PayrollPro")
        title.setStyleSheet(f"font-size: 16px; font-weight: 800; color: {theme.TEXT_STRONG};")
        brand.addWidget(title)
        brand.addStretch()
        lay.addLayout(brand)
        lay.addSpacing(24)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        nav_box = QWidget()
        nav_lay = QVBoxLayout(nav_box)
        nav_lay.setContentsMargins(0, 0, 0, 0)
        nav_lay.setSpacing(3)

        for key, icon, label in nav_items:
            btn = make_button(f"  {icon}   {label}")
            btn.setProperty("nav", "true")
            btn.setStyleSheet("text-align: left;")
            btn.clicked.connect(lambda _, k=key: self.nav_selected.emit(k))
            nav_lay.addWidget(btn)
            self.buttons[key] = btn
        nav_lay.addStretch()
        scroll.setWidget(nav_box)
        lay.addWidget(scroll, 1)

        # Logout lives here, pinned at the bottom of the sidebar — same
        # side as the rest of the navigation, so it's easy to find
        # instead of buried in a topbar dropdown.
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {theme.BORDER}; border: none;")
        lay.addWidget(divider)
        lay.addSpacing(8)
        logout_btn = make_button("  \U0001F6AA   Logout", "ghost")
        logout_btn.setProperty("nav", "true")
        logout_btn.setStyleSheet(f"text-align: left; color: {theme.DANGER};")
        logout_btn.clicked.connect(lambda: self.logout_requested.emit())
        lay.addWidget(logout_btn)

    def set_active(self, key: str):
        for k, b in self.buttons.items():
            b.setProperty("active", "true" if k == key else "false")
            b.style().unpolish(b)
            b.style().polish(b)


class TopBar(QFrame):
    settings_requested = pyqtSignal()
    appearance_requested = pyqtSignal()
    refresh_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topbar")
        self.setFixedHeight(64)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 0, 24, 0)

        self.page_title = QLabel("Dashboard")
        self.page_title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {theme.TEXT_STRONG};")
        lay.addWidget(self.page_title)

        refresh_btn = make_button("\U0001F504 Refresh", "ghost")
        refresh_btn.setToolTip("Reload this page's data now")
        refresh_btn.clicked.connect(lambda: self.refresh_requested.emit())
        lay.addSpacing(12)
        lay.addWidget(refresh_btn)

        theme_btn = make_button("\U0001F3A8 Theme", "ghost")
        theme_btn.setToolTip("Change the app's color theme")
        theme_btn.clicked.connect(lambda: self.appearance_requested.emit())
        lay.addSpacing(8)
        lay.addWidget(theme_btn)

        lay.addStretch()

        role_text = "Administrator" if current_session.is_admin() else "Employee"
        role_badge = QLabel(role_text)
        role_badge.setStyleSheet(f"""
            color: {theme.PINK}; background: {theme.rgba(theme.PINK, 0.12)};
            border: 1px solid {theme.rgba(theme.PINK, 0.3)}; border-radius: 10px;
            padding: 3px 10px; font-size: 11px; font-weight: 700;
        """)
        lay.addWidget(role_badge)
        lay.addSpacing(12)

        avatar = QLabel(current_session.initials())
        avatar.setFixedSize(36, 36)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(f"""
            background: {theme.GRADIENT_PRIMARY}; color: {theme.TEXT_ON_ACCENT}; font-weight: 800;
            border-radius: 18px; font-size: 14px;
        """)
        lay.addWidget(avatar)

        name_lbl = QLabel(current_session.full_name or current_session.username or "")
        name_lbl.setStyleSheet(f"font-weight: 700; color: {theme.TEXT_STRONG}; margin-left: 4px;")
        lay.addWidget(name_lbl)

        if current_session.is_admin():
            menu_btn = make_button("\u25BE", "ghost")
            menu_btn.setFixedWidth(36)
            menu = QMenu(menu_btn)
            settings_action = menu.addAction("\u2699\uFE0F  Settings")
            settings_action.triggered.connect(lambda: self.settings_requested.emit())
            menu_btn.setMenu(menu)
            lay.addWidget(menu_btn)


class MainWindow(QWidget):
    logout_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_admin = current_session.is_admin()
        self.nav_items = ADMIN_NAV if self.is_admin else EMPLOYEE_NAV
        self._page_cache: dict = {}
        self._page_titles = {key: label for key, _, label in self.nav_items}

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar(self.nav_items)
        root.addWidget(self.sidebar)

        right = QFrame()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        self.topbar = TopBar()
        right_lay.addWidget(self.topbar)
        self._right_lay = right_lay

        self.content_scroll = QScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_stack = QStackedWidget()
        content_wrap = QWidget()
        wrap_lay = QVBoxLayout(content_wrap)
        wrap_lay.setContentsMargins(28, 24, 28, 24)
        wrap_lay.addWidget(self.content_stack)
        self.content_scroll.setWidget(content_wrap)
        right_lay.addWidget(self.content_scroll, 1)

        root.addWidget(right, 1)

        self.sidebar.nav_selected.connect(self.navigate_to)
        self.sidebar.logout_requested.connect(self._handle_logout)
        self.topbar.settings_requested.connect(self._open_settings)
        self.topbar.appearance_requested.connect(self._open_appearance)
        self.topbar.refresh_requested.connect(self.refresh_current)

        self._current_key = None
        first_key = self.nav_items[0][0]
        self.navigate_to(first_key)

    # ------------------------------------------------------------------
    def navigate_to(self, key: str):
        # Special theme's accent depends on which section is active —
        # set this before building/showing anything so a freshly-built
        # page (and any dialog opened from it) picks up the right one.
        theme.set_active_section(key)
        self._current_key = key
        if key not in self._page_cache:
            page = self._build_page(key)
            self.content_stack.addWidget(page)
            self._page_cache[key] = page
        else:
            # Pages are cached for instant switching, but that means a
            # page you visited earlier won't show changes made elsewhere
            # (e.g. processing payroll, then clicking back to Dashboard)
            # unless we explicitly refresh it every time it's shown.
            page = self._page_cache[key]
            if hasattr(page, "refresh"):
                page.refresh()
        self.content_stack.setCurrentWidget(self._page_cache[key])
        self.sidebar.set_active(key)
        self.topbar.page_title.setText(self._page_titles.get(key, ""))

    def rebuild_theme(self):
        """Called after the Appearance tab in Settings saves a new
        theme. Cached pages/sidebar/topbar all have the *old* palette
        baked into their individual widget stylesheets (see ui/theme.py
        for why that's unavoidable with Qt's styling model), so the
        only reliable fix is to throw them away and rebuild — the app
        re-applies the fresh global stylesheet too."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme.build_stylesheet())

        for page in list(self._page_cache.values()):
            self.content_stack.removeWidget(page)
            page.deleteLater()
        self._page_cache = {}

        layout = self.layout()
        layout.removeWidget(self.sidebar)
        self.sidebar.deleteLater()
        self.sidebar = Sidebar(self.nav_items)
        self.sidebar.nav_selected.connect(self.navigate_to)
        self.sidebar.logout_requested.connect(self._handle_logout)
        layout.insertWidget(0, self.sidebar)

        self._right_lay.removeWidget(self.topbar)
        self.topbar.deleteLater()
        self.topbar = TopBar()
        self.topbar.settings_requested.connect(self._open_settings)
        self.topbar.appearance_requested.connect(self._open_appearance)
        self.topbar.refresh_requested.connect(self.refresh_current)
        self._right_lay.insertWidget(0, self.topbar)

        restore_key = self._current_key or self.nav_items[0][0]
        self.navigate_to(restore_key)

    def refresh_current(self):
        widget = self.content_stack.currentWidget()
        if hasattr(widget, "refresh"):
            widget.refresh()
            from ui.widgets.common import show_toast
            show_toast(self, "Refreshed", "success")

    def _build_page(self, key: str) -> QWidget:
        if key == "dashboard":
            from ui.admin.dashboard_page import DashboardPage
            return DashboardPage(self)
        if key == "employees":
            from ui.admin.employees_page import EmployeesPage
            return EmployeesPage(self)
        if key == "departments":
            from ui.admin.departments_page import DepartmentsPage
            return DepartmentsPage(self)
        if key == "positions":
            from ui.admin.positions_page import PositionsPage
            return PositionsPage(self)
        if key == "pay_periods":
            from ui.admin.pay_periods_page import PayPeriodsPage
            return PayPeriodsPage(self)
        if key == "attendance":
            from ui.admin.attendance_page import AttendancePage
            return AttendancePage(self)
        if key == "payroll":
            from ui.admin.payroll_page import PayrollPage
            return PayrollPage(self)
        if key == "allowances":
            from ui.admin.allowances_page import AllowancesPage
            return AllowancesPage(self)
        if key == "reports":
            from ui.admin.reports_page import ReportsPage
            return ReportsPage(self)
        if key == "notifications":
            from ui.admin.notifications_page import NotificationsPage
            return NotificationsPage(self)
        if key == "audit_log":
            from ui.admin.audit_log_page import AuditLogPage
            return AuditLogPage(self)
        if key == "archive":
            from ui.admin.archive_page import ArchivePage
            return ArchivePage(self)
        if key == "emp_dashboard":
            from ui.employee.dashboard_page import EmployeeDashboardPage
            return EmployeeDashboardPage(self)
        if key == "emp_payslips":
            from ui.employee.payslips_page import PayslipsPage
            return PayslipsPage(self)
        if key == "emp_attendance":
            from ui.employee.attendance_page import AttendancePage
            return AttendancePage(self)
        if key == "emp_profile":
            from ui.employee.profile_page import ProfilePage
            return ProfilePage(self)
        return QLabel(f"Page '{key}' not implemented.")

    def _handle_logout(self):
        import core.audit as audit
        db = get_db()
        with db.session() as s:
            audit.log_action(s, current_session.user_id, "LOGOUT", "users", current_session.user_id)
        current_session.logout()
        self.logout_requested.emit()

    def _open_settings(self):
        from ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
        dlg.exec()

    def _open_appearance(self):
        from ui.settings_dialog import AppearanceDialog
        dlg = AppearanceDialog(self)
        dlg.exec()
