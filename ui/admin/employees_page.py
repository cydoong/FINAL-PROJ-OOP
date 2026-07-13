"""
ui.admin.employees_page
===========================
Full employee management: searchable/filterable table, Add/Edit
dialog (with live username/duplicate-name checks), archive, passcode
generation, and admin password reset — exact port of admin/employees.php.
"""
from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QVBoxLayout, QWidget,
)

import core.employee_service as es
import core.reference_service as rs
from core.session import current_session
from core.utils import format_currency, format_passcode
from database.db_manager import get_db
from ui import theme
from ui.widgets.common import (
    Badge, CopyableInfoDialog, DigitCounterField, SearchBox, SectionHeader, confirm, error as show_err,
    info as show_info, make_button, warn,
)
from ui.widgets.dialogs import BaseFormDialog
from ui.widgets.table import DataTable, action_bar


GENDER_OPTIONS = ["male", "female", "other"]
STATUS_OPTIONS = ["active", "inactive", "terminated", "on_leave"]


class EmployeeCell(QWidget):
    """Name + employee code, with the username shown underneath in a
    small muted/monospace line — so it's visible right on the main list
    without crowding the row (full detail still lives in Passcodes)."""
    def __init__(self, full_name: str, employee_code: str, username: str | None):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(1)
        top = QLabel(f"{full_name}  ({employee_code})")
        top.setStyleSheet(f"font-weight: 600; color: {theme.TEXT_STRONG};")
        lay.addWidget(top)
        if username:
            bottom = QLabel(f"@{username}")
            bottom.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px; font-family: monospace;")
            lay.addWidget(bottom)


class EmployeeFormDialog(BaseFormDialog):
    def __init__(self, parent, departments, positions_by_dept, editing=None):
        title = "Edit Employee" if editing else "Add New Employee"
        super().__init__(title, "Fields marked * are required.", parent, width=640, height=760)
        self.editing = editing
        self.departments = departments
        self.positions_by_dept = positions_by_dept

        self.first_name = QLineEdit()
        self.last_name = QLineEdit()
        self.middle_name = QLineEdit()
        self.email = QLineEdit()
        self.phone = DigitCounterField(max_digits=11, placeholder="09171234567")
        self.address = QTextEdit()
        self.address.setFixedHeight(60)
        self.gender = QComboBox()
        self.gender.addItems([g.title() for g in GENDER_OPTIONS])
        self.birthdate = QDateEdit(calendarPopup=True)
        self.birthdate.setDisplayFormat("yyyy-MM-dd")
        self.birthdate.setDate(date(1995, 1, 1))
        self.hire_date = QDateEdit(calendarPopup=True)
        self.hire_date.setDisplayFormat("yyyy-MM-dd")
        self.hire_date.setDate(date.today())

        self.department = QComboBox()
        for d in departments:
            self.department.addItem(d.department_name, d.department_id)
        self.department.currentIndexChanged.connect(self._reload_positions)

        self.position = QComboBox()
        self._reload_positions()

        self.status = QComboBox()
        self.status.addItems([s.replace("_", " ").title() for s in STATUS_OPTIONS])

        self.sss = QLineEdit()
        self.philhealth = QLineEdit()
        self.pagibig = QLineEdit()
        self.tin = QLineEdit()
        self.bank_name = QLineEdit()
        self.bank_account = QLineEdit()
        self.payment_method = QComboBox()
        self._payment_methods = ["bank_transfer", "gcash", "maya", "cash", "check"]
        self.payment_method.addItems(["Bank Transfer", "GCash", "Maya", "Cash", "Check"])
        self.payment_method.currentIndexChanged.connect(self._update_payment_fields)
        self.gcash_number = DigitCounterField(max_digits=11, placeholder="09171234567")
        self.maya_number = DigitCounterField(max_digits=11, placeholder="09171234567")
        self.username = QLineEdit()
        self.username.setPlaceholderText("juan.delacruz")
        self.username_status = QLabel("")
        self.username_status.setMinimumWidth(90)
        self.username_status.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px; font-weight: 700;")
        self._username_timer = QTimer(self)
        self._username_timer.setSingleShot(True)
        self._username_timer.timeout.connect(self._check_username_availability)
        self.username.textChanged.connect(lambda: self._username_timer.start(400))

        self.add_row("First Name*", self.first_name)
        self.add_row("Last Name*", self.last_name)
        self.add_row("Middle Name", self.middle_name)
        self.add_row("Email", self.email)
        self.add_row("Phone", self.phone)
        self.add_row("Address", self.address)
        self.add_row("Gender", self.gender)
        self.add_row("Birthdate", self.birthdate)
        self.add_row("Hire Date*", self.hire_date)
        self.add_row("Department*", self.department)
        self.add_row("Position*", self.position)
        self.add_row("Employment Status", self.status)
        self.add_row("SSS Number", self.sss)
        self.add_row("PhilHealth Number", self.philhealth)
        self.add_row("Pag-IBIG Number", self.pagibig)
        self.add_row("TIN Number*", self.tin)
        self.add_row("Bank Name", self.bank_name)
        self.add_row("Bank Account #", self.bank_account)
        self.add_row("Payment Method*", self.payment_method)
        self.add_row("GCash Number", self.gcash_number)
        self.add_row("Maya Number", self.maya_number)
        self._update_payment_fields()
        if not editing:
            username_row = QWidget()
            ur_lay = QHBoxLayout(username_row)
            ur_lay.setContentsMargins(0, 0, 0, 0)
            ur_lay.addWidget(self.username, 1)
            ur_lay.addWidget(self.username_status)
            self.add_row("Username*", username_row)
            hint = QLabel("Lowercase letters, numbers, dots, and underscores only.")
            hint.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
            self.add_full_row(hint)

        if editing:
            self._populate(editing)

    def _check_username_availability(self):
        from core.utils import is_valid_username
        username = self.username.text().strip().lower()
        if not username:
            self.username_status.setText("")
            self.username.setProperty("error", "false")
            self.username.setProperty("success", "false")
            self._repolish(self.username)
            return
        if not is_valid_username(username):
            self._set_username_status("\u2717 Invalid format", theme.DANGER, error=True)
            return
        db = get_db()
        with db.session() as s:
            available = es.check_username_available(s, username)
        if available:
            self._set_username_status("\u2713 Available", theme.SUCCESS, success=True)
        else:
            self._set_username_status("\u2717 Taken", theme.DANGER, error=True)

    def _set_username_status(self, text: str, color: str, error: bool = False, success: bool = False):
        self.username_status.setText(text)
        self.username_status.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 700;")
        self.username.setProperty("error", "true" if error else "false")
        self.username.setProperty("success", "true" if success else "false")
        self._repolish(self.username)

    @staticmethod
    def _repolish(widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _update_payment_fields(self):
        method = self._payment_methods[self.payment_method.currentIndex()] if self.payment_method.currentIndex() >= 0 else "bank_transfer"
        self.set_row_visible(self.bank_name, method == "bank_transfer")
        self.set_row_visible(self.bank_account, method == "bank_transfer")
        self.set_row_visible(self.gcash_number, method == "gcash")
        self.set_row_visible(self.maya_number, method == "maya")

    def _reload_positions(self):
        self.position.clear()
        dept_id = self.department.currentData()
        for p in self.positions_by_dept.get(dept_id, []):
            self.position.addItem(f"{p.position_title} ({format_currency(p.base_salary)})", p.position_id)

    def _populate(self, emp):
        self.first_name.setText(emp.first_name)
        self.last_name.setText(emp.last_name)
        self.middle_name.setText(emp.middle_name or "")
        self.email.setText(emp.email or "")
        self.phone.setText(emp.phone or "")
        self.address.setPlainText(emp.address or "")
        if emp.gender:
            self.gender.setCurrentText(emp.gender.title())
        if emp.birthdate:
            self.birthdate.setDate(emp.birthdate if isinstance(emp.birthdate, date) else date.today())
        if emp.hire_date:
            self.hire_date.setDate(emp.hire_date if isinstance(emp.hire_date, date) else date.today())
        idx = self.department.findData(emp.department_id)
        if idx >= 0:
            self.department.setCurrentIndex(idx)
        self._reload_positions()
        pidx = self.position.findData(emp.position_id)
        if pidx >= 0:
            self.position.setCurrentIndex(pidx)
        self.status.setCurrentText(emp.employment_status.replace("_", " ").title())
        self.sss.setText(emp.sss_number or "")
        self.philhealth.setText(emp.philhealth_number or "")
        self.pagibig.setText(emp.pagibig_number or "")
        self.tin.setText(emp.tin_number or "")
        self.bank_name.setText(emp.bank_name or "")
        self.bank_account.setText(emp.bank_account or "")
        pm_idx = self._payment_methods.index(emp.payment_method) if emp.payment_method in self._payment_methods else 0
        self.payment_method.setCurrentIndex(pm_idx)
        self.gcash_number.setText(emp.gcash_number or "")
        self.maya_number.setText(emp.maya_number or "")
        self._update_payment_fields()

    def to_form_data(self) -> es.EmployeeFormData:
        return es.EmployeeFormData(
            first_name=self.first_name.text().strip(), last_name=self.last_name.text().strip(),
            middle_name=self.middle_name.text().strip(), email=self.email.text().strip(),
            phone=self.phone.text().strip(), address=self.address.toPlainText().strip(),
            gender=self.gender.currentText().lower(), birthdate=self.birthdate.date().toPyDate(),
            hire_date=self.hire_date.date().toPyDate(), department_id=self.department.currentData(),
            position_id=self.position.currentData(), employment_status=self.status.currentText().lower().replace(" ", "_"),
            sss_number=self.sss.text().strip(), philhealth_number=self.philhealth.text().strip(),
            pagibig_number=self.pagibig.text().strip(), tin_number=self.tin.text().strip(),
            bank_name=self.bank_name.text().strip(), bank_account=self.bank_account.text().strip(),
            payment_method=self._payment_methods[self.payment_method.currentIndex()] if self.payment_method.currentIndex() >= 0 else "bank_transfer",
            gcash_number=self.gcash_number.text().strip(), maya_number=self.maya_number.text().strip(),
            username=self.username.text().strip().lower(),
        )


class EmployeesPage(QWidget):
    PER_PAGE = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.page = 1
        self.search_text = ""
        self.dept_filter = 0
        self.status_filter = ""

        lay = QVBoxLayout(self)
        lay.setSpacing(16)

        header = SectionHeader("Employees", "Manage your workforce", "+ Add Employee")
        header.action_btn.clicked.connect(self.open_add_dialog)
        lay.addWidget(header)

        filters = QHBoxLayout()
        self.search_box = SearchBox("Search by name, code, or email...")
        self.search_box.textChanged.connect(self._on_search)
        filters.addWidget(self.search_box)

        self.dept_combo = QComboBox()
        self.dept_combo.addItem("All Departments", 0)
        self.dept_combo.currentIndexChanged.connect(self._on_filter_change)
        filters.addWidget(self.dept_combo)

        self.status_combo = QComboBox()
        self.status_combo.addItem("All Statuses", "")
        for st in STATUS_OPTIONS:
            self.status_combo.addItem(st.replace("_", " ").title(), st)
        self.status_combo.currentIndexChanged.connect(self._on_filter_change)
        filters.addWidget(self.status_combo)
        filters.addStretch()
        passcodes_btn = make_button("\U0001F511 View Passcodes", "ghost")
        passcodes_btn.setToolTip("See every employee's username & activation passcode in one place")
        passcodes_btn.clicked.connect(self.open_passcodes_panel)
        filters.addWidget(passcodes_btn)
        lay.addLayout(filters)

        self.table = DataTable([
            "Employee", "Department", "Position", "Salary", "Status", "Account", "Actions"
        ])
        self.table.set_col_width(6)
        lay.addWidget(self.table, 1)

        pager = QHBoxLayout()
        self.page_label = QLabel("")
        self.page_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        pager.addWidget(self.page_label)
        pager.addStretch()
        self.prev_btn = make_button("\u2190 Prev", "ghost")
        self.prev_btn.clicked.connect(self._prev_page)
        self.next_btn = make_button("Next \u2192", "ghost")
        self.next_btn.clicked.connect(self._next_page)
        pager.addWidget(self.prev_btn)
        pager.addWidget(self.next_btn)
        lay.addLayout(pager)

        self.refresh()

    # ------------------------------------------------------------------
    def _load_departments_positions(self):
        db = get_db()
        with db.session() as s:
            depts = rs.list_departments(s)
            positions = rs.list_positions(s)
        positions_by_dept: dict = {}
        for p in positions:
            positions_by_dept.setdefault(p.department_id, []).append(p)
        return depts, positions_by_dept

    def refresh(self):
        db = get_db()
        with db.session() as s:
            rows, total = es.list_employees(
                s, self.search_text, self.dept_filter, self.status_filter, self.page, self.PER_PAGE
            )
            depts = rs.list_departments(s)

        current_dept = self.dept_combo.currentData()
        self.dept_combo.blockSignals(True)
        self.dept_combo.clear()
        self.dept_combo.addItem("All Departments", 0)
        for d in depts:
            self.dept_combo.addItem(d.department_name, d.department_id)
        if current_dept:
            idx = self.dept_combo.findData(current_dept)
            if idx >= 0:
                self.dept_combo.setCurrentIndex(idx)
        self.dept_combo.blockSignals(False)

        self.table.clear_rows()
        for row in rows:
            r = self.table.add_row([
                None, row.department_name, row.position_title,
                format_currency(row.base_salary), "", "", None,
            ])
            self.table.set_widget(r, 0, EmployeeCell(row.full_name, row.employee_code, row.username))
            self.table.set_widget(r, 4, Badge(row.employment_status))
            account_badge = Badge("Activated", theme.SUCCESS) if row.account_activated else Badge("Pending", theme.WARNING)
            self.table.set_widget(r, 5, account_badge)
            actions = action_bar([
                ("\u270F\uFE0F", "ghost", lambda _, e=row: self.open_edit_dialog(e), "Edit this employee's details"),
                ("\U0001F511", "ghost", lambda _, e=row: self.show_passcode(e), "View or regenerate activation passcode"),
                ("\U0001F513", "ghost", lambda _, e=row: self.reset_password(e), "Reset password to the default"),
                ("\U0001F5D1\uFE0F", "danger", lambda _, e=row: self.archive(e), "Move this employee to Archive"),
            ])
            self.table.set_widget(r, 6, actions)

        total_pages = max(1, (total + self.PER_PAGE - 1) // self.PER_PAGE)
        self.page_label.setText(f"Page {self.page} of {total_pages} \u00b7 {total} employee(s)")
        self.prev_btn.setEnabled(self.page > 1)
        self.next_btn.setEnabled(self.page < total_pages)

    def _on_search(self, text):
        self.search_text = text
        self.page = 1
        self.refresh()

    def _on_filter_change(self):
        self.dept_filter = self.dept_combo.currentData() or 0
        self.status_filter = self.status_combo.currentData() or ""
        self.page = 1
        self.refresh()

    def _prev_page(self):
        if self.page > 1:
            self.page -= 1
            self.refresh()

    def _next_page(self):
        self.page += 1
        self.refresh()

    # ------------------------------------------------------------------
    def _confirm_blank_gov_numbers(self, form) -> bool:
        """SSS/PhilHealth/Pag-IBIG deductions only get computed for
        schemes the employee is actually registered under (has a
        number on file). Confirm each blank one individually so it's a
        deliberate choice, not an accident."""
        checks = [
            ("sss_number", "SSS Number", "SSS"),
            ("philhealth_number", "PhilHealth Number", "PhilHealth"),
            ("pagibig_number", "Pag-IBIG Number", "Pag-IBIG"),
        ]
        for field_attr, field_label, scheme_label in checks:
            value = (getattr(form, field_attr, "") or "").strip()
            if not value:
                ok = confirm(
                    self, f"Leave {field_label} Blank?",
                    f"You didn't enter a {field_label}. This means <b>{scheme_label} contributions will "
                    f"NOT be deducted</b> from this employee's payroll — the system only withholds for "
                    f"schemes an employee is on record as registered under.<br><br>"
                    f"Continue without a {field_label}?",
                )
                if not ok:
                    return False
        return True

    def open_add_dialog(self):
        depts, pos_by_dept = self._load_departments_positions()
        if not depts:
            warn(self, "No Departments", "Please add a department and position first.")
            return
        dlg = EmployeeFormDialog(self, depts, pos_by_dept)
        dlg.save_btn.clicked.connect(lambda: self._submit_add(dlg))
        dlg.exec()

    def _submit_add(self, dlg: EmployeeFormDialog):
        dlg.clear_error()
        form = dlg.to_form_data()
        if not form.first_name or not form.last_name:
            dlg.show_error("First and last name are required.")
            return
        if not form.username:
            dlg.show_error("Username is required.")
            return
        if not (form.tin_number or "").strip():
            dlg.show_error("TIN Number is required.")
            return
        if not self._confirm_blank_gov_numbers(form):
            return
        db = get_db()
        with db.session() as s:
            result = es.add_employee(s, form, current_session.user_id)
        if not result.success:
            dlg.show_error(result.error)
            return
        dlg.accept()
        info_dlg = CopyableInfoDialog(
            self, "Employee Added",
            f"<b>{result.data['name']}</b> was added successfully. Share the credentials below "
            f"with the employee so they can activate their account.",
            fields=[
                ("Employee Code", result.data["employee_code"]),
                ("Username", result.data["username"]),
                ("Passcode", format_passcode(result.data["passcode"])),
            ],
        )
        info_dlg.exec()
        self.refresh()

    def open_edit_dialog(self, row):
        depts, pos_by_dept = self._load_departments_positions()
        db = get_db()
        with db.session() as s:
            from database.models import Employee
            emp = s.get(Employee, row.employee_id)
            dlg = EmployeeFormDialog(self, depts, pos_by_dept, editing=emp)
        dlg.save_btn.clicked.connect(lambda: self._submit_edit(dlg, row.employee_id))
        dlg.exec()

    def _submit_edit(self, dlg: EmployeeFormDialog, employee_id: int):
        dlg.clear_error()
        form = dlg.to_form_data()
        if not form.first_name or not form.last_name:
            dlg.show_error("First and last name are required.")
            return
        if not (form.tin_number or "").strip():
            dlg.show_error("TIN Number is required.")
            return
        if not self._confirm_blank_gov_numbers(form):
            return
        db = get_db()
        with db.session() as s:
            result = es.edit_employee(s, employee_id, form, current_session.user_id)
        if not result.success:
            dlg.show_error(result.error)
            return
        dlg.accept()
        self.refresh()

    def show_passcode(self, row):
        if not row.user_id:
            warn(self, "No Account", "This employee has no linked user account.")
            return
        if confirm(self, "Regenerate Passcode?",
                   f"Generate a new passcode for {row.full_name}? The old passcode will stop working."):
            db = get_db()
            with db.session() as s:
                result = es.generate_passcode_for_employee(s, row.user_id, current_session.user_id)
            if result.success:
                info_dlg = CopyableInfoDialog(
                    self, "New Passcode Generated", f"A new passcode was generated for <b>{result.data['name']}</b>.",
                    fields=[
                        ("Employee Code", result.data.get("emp_code") or "\u2014"),
                        ("Username", result.data["username"]),
                        ("New Passcode", format_passcode(result.data["passcode"])),
                    ],
                )
                info_dlg.exec()
                self.refresh()
            else:
                show_err(self, "Error", result.error)
        else:
            if row.passcode:
                info_dlg = CopyableInfoDialog(
                    self, f"Passcode for {row.full_name}", "",
                    fields=[
                        ("Employee Code", row.employee_code),
                        ("Username", row.username or "\u2014"),
                        ("Current Passcode", format_passcode(row.passcode)),
                    ],
                )
                info_dlg.exec()

    def reset_password(self, row):
        if not row.user_id:
            warn(self, "No Account", "This employee has no linked user account.")
            return
        import core.auth_service as auth
        dlg = BaseFormDialog("Reset Password", f"Enter {row.full_name}'s passcode to confirm this reset.",
                              self, width=420)
        pw_field = QLineEdit()
        pw_field.setPlaceholderText("ABCD-1234")
        dlg.add_row("Passcode", pw_field)
        dlg.save_btn.setText("Reset to Default")

        def do_reset():
            db = get_db()
            with db.session() as s:
                result = auth.admin_reset_employee_password(s, current_session.user_id, row.user_id, pw_field.text())
            if not result.success:
                dlg.show_error(result.error)
                return
            dlg.accept()
            show_info(self, "Password Reset",
                       f"{row.full_name}'s password has been reset to the default: "
                       f"\"{result.extra['default_password']}\"")
        dlg.save_btn.clicked.connect(do_reset)
        dlg.exec()

    def archive(self, row):
        if not confirm(self, "Archive Employee?",
                        f"Archive {row.full_name}? Their record moves to the Archive and can be restored later.",
                        danger=True):
            return
        db = get_db()
        with db.session() as s:
            result = es.archive_employee(s, row.employee_id, current_session.user_id)
        if result.success:
            show_info(self, "Archived", f"{result.data['name']} has been archived.")
            self.refresh()
        else:
            show_err(self, "Cannot Archive", result.error)

    def open_passcodes_panel(self):
        db = get_db()
        with db.session() as s:
            rows = es.list_all_passcodes(s)
        dlg = PasscodesPanelDialog(self, rows)
        dlg.exec()


class PasscodesPanelDialog(QDialog):
    """Read-only reference panel listing every active employee's
    username + activation passcode, with a Copy button per row —
    handy when re-sharing credentials without regenerating them."""

    def __init__(self, parent, rows: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Employee Passcodes")
        self.resize(720, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(14)

        title = QLabel("Employee Passcodes")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {theme.TEXT_STRONG};")
        lay.addWidget(title)
        sub = QLabel("Every active employee's username and activation passcode, all in one place.")
        sub.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px;")
        lay.addWidget(sub)

        table = DataTable(["Employee", "Code", "Username", "Passcode", "Status", ""])
        table.set_col_width(5)
        for r in rows:
            row_idx = table.add_row([
                r["full_name"], r["employee_code"], r["username"],
                format_passcode(r["passcode"]), "", None,
            ])
            table.set_widget(row_idx, 4, Badge("Activated" if r["account_activated"] else "Pending",
                                                 theme.SUCCESS if r["account_activated"] else theme.WARNING))
            copy_btn = make_button("\U0001F4CB Copy", "ghost", compact=True)
            copy_btn.setToolTip("Copy username and passcode to clipboard")
            copy_btn.clicked.connect(
                lambda _, u=r["username"], p=r["passcode"], b=None: self._copy_row(u, p, copy_btn)
            )
            table.set_widget(row_idx, 5, copy_btn)
        lay.addWidget(table, 1)

        if not rows:
            empty = QLabel("No employee accounts yet.")
            empty.setStyleSheet(f"color: {theme.TEXT_MUTED};")
            lay.addWidget(empty)

        close_btn = make_button("Close", "primary")
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn)

    def _copy_row(self, username: str, passcode: str, btn):
        from ui.widgets.common import copy_to_clipboard
        copy_to_clipboard(f"Username: {username} | Passcode: {format_passcode(passcode)}")
        original = btn.text()
        btn.setText("\u2713 Copied")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1200, lambda: btn.setText(original) if btn else None)
