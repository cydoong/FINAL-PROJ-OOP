"""
ui.admin.departments_page
=============================
Department CRUD, exact port of admin/departments.php.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QTextEdit, QVBoxLayout, QWidget

import core.reference_service as rs
from core.session import current_session
from database.db_manager import get_db
from ui.widgets.common import Badge, SectionHeader, confirm, error as show_err
from ui.widgets.dialogs import BaseFormDialog
from ui.widgets.table import DataTable, action_bar


class DepartmentFormDialog(BaseFormDialog):
    def __init__(self, parent, employees_in_dept=None, editing=None):
        title = "Edit Department" if editing else "Add Department"
        super().__init__(title, parent=parent, width=480)
        self.editing = editing
        self.name = QLineEdit()
        self.description = QTextEdit()
        self.description.setFixedHeight(70)
        self.add_row("Department Name*", self.name)
        self.add_row("Description", self.description)

        self.head = None
        self.active_check = None
        if editing:
            self.head = QComboBox()
            self.head.addItem("(No department head)", None)
            for e in (employees_in_dept or []):
                self.head.addItem(e.full_name, e.employee_id)
            self.add_row("Department Head", self.head)
            self.active_check = QCheckBox("Active")
            self.active_check.setChecked(editing.is_active)
            self.add_row("Status", self.active_check)
            self.name.setText(editing.department_name)
            self.description.setPlainText(editing.description or "")


class DepartmentsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        header = SectionHeader("Departments", "Organize your company structure", "+ Add Department")
        header.action_btn.clicked.connect(self.open_add)
        lay.addWidget(header)

        self.table = DataTable(["Department", "Description", "Head", "Employees", "Positions", "Status", "Actions"])
        lay.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        db = get_db()
        with db.session() as s:
            rows = rs.list_departments(s)
        self.table.clear_rows()
        for d in rows:
            r = self.table.add_row([d.department_name, d.description or "\u2014", d.head_name or "\u2014",
                                     str(d.emp_count), str(d.pos_count), "", None])
            self.table.set_widget(r, 5, Badge("active" if d.is_active else "inactive"))
            actions = action_bar([
                ("\u270F\uFE0F", "ghost", lambda _, dd=d: self.open_edit(dd), "Edit department"),
                ("\U0001F5D1\uFE0F", "danger", lambda _, dd=d: self.delete(dd), "Delete department"),
            ])
            self.table.set_widget(r, 6, actions)

    def open_add(self):
        dlg = DepartmentFormDialog(self)
        dlg.save_btn.clicked.connect(lambda: self._submit_add(dlg))
        dlg.exec()

    def _submit_add(self, dlg):
        dlg.clear_error()
        if not dlg.name.text().strip():
            dlg.show_error("Department name is required.")
            return
        db = get_db()
        with db.session() as s:
            result = rs.add_department(s, dlg.name.text().strip(), dlg.description.toPlainText().strip(),
                                        current_session.user_id)
        if not result.success:
            dlg.show_error(result.error)
            return
        dlg.accept()
        self.refresh()

    def open_edit(self, dept_row):
        db = get_db()
        with db.session() as s:
            employees = rs.active_employees_in_department(s, dept_row.department_id)
            employees_data = [(e.employee_id, e.full_name) for e in employees]
        from types import SimpleNamespace
        emp_ns = [SimpleNamespace(employee_id=i, full_name=n) for i, n in employees_data]
        dlg = DepartmentFormDialog(self, employees_in_dept=emp_ns, editing=dept_row)
        dlg.save_btn.clicked.connect(lambda: self._submit_edit(dlg, dept_row.department_id))
        dlg.exec()

    def _submit_edit(self, dlg, dept_id):
        dlg.clear_error()
        db = get_db()
        with db.session() as s:
            result = rs.edit_department(
                s, dept_id, dlg.name.text().strip(), dlg.description.toPlainText().strip(),
                dlg.active_check.isChecked(), dlg.head.currentData(), current_session.user_id,
            )
        if not result.success:
            dlg.show_error(result.error)
            return
        dlg.accept()
        self.refresh()

    def delete(self, dept_row):
        if not confirm(self, "Delete Department?", f'Permanently delete "{dept_row.department_name}"?', danger=True):
            return
        db = get_db()
        with db.session() as s:
            result = rs.delete_department(s, dept_row.department_id, current_session.user_id)
        if result.success:
            self.refresh()
        else:
            show_err(self, "Cannot Delete", result.error)
