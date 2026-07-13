"""
ui.admin.positions_page
===========================
Position CRUD, exact port of admin/positions.php.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLineEdit, QTextEdit, QVBoxLayout, QWidget

import core.reference_service as rs
from core.session import current_session
from core.utils import format_currency
from database.db_manager import get_db
from ui.widgets.common import Badge, SectionHeader, confirm, error as show_err
from ui.widgets.dialogs import BaseFormDialog
from ui.widgets.table import DataTable, action_bar

EMPLOYMENT_TYPES = ["full_time", "part_time", "contractual", "probationary"]


class PositionFormDialog(BaseFormDialog):
    def __init__(self, parent, departments, editing=None):
        title = "Edit Position" if editing else "Add Position"
        super().__init__(title, parent=parent, width=480)
        self.editing = editing
        self.department = QComboBox()
        for d in departments:
            self.department.addItem(d.department_name, d.department_id)
        self.title_field = QLineEdit()
        self.salary = QDoubleSpinBox()
        self.salary.setRange(0, 10_000_000)
        self.salary.setDecimals(2)
        self.salary.setPrefix("\u20b1 ")
        self.emp_type = QComboBox()
        self.emp_type.addItems([t.replace("_", " ").title() for t in EMPLOYMENT_TYPES])
        self.description = QTextEdit()
        self.description.setFixedHeight(60)

        self.add_row("Department*", self.department)
        self.add_row("Position Title*", self.title_field)
        self.add_row("Base Salary (monthly)*", self.salary)
        self.add_row("Employment Type", self.emp_type)
        self.add_row("Description", self.description)

        self.active_check = None
        if editing:
            self.active_check = QCheckBox("Active")
            self.active_check.setChecked(editing.is_active)
            self.add_row("Status", self.active_check)
            idx = self.department.findData(editing.department_id)
            if idx >= 0:
                self.department.setCurrentIndex(idx)
            self.title_field.setText(editing.position_title)
            self.salary.setValue(float(editing.base_salary))
            self.emp_type.setCurrentText(editing.employment_type.replace("_", " ").title())
            self.description.setPlainText(editing.description or "")


class PositionsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        header = SectionHeader("Positions", "Manage job titles and salary grades", "+ Add Position")
        header.action_btn.clicked.connect(self.open_add)
        lay.addWidget(header)

        self.table = DataTable(["Position", "Department", "Salary", "Type", "Employees", "Status", "Actions"])
        lay.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        db = get_db()
        with db.session() as s:
            rows = rs.list_positions(s)
        self.table.clear_rows()
        for p in rows:
            r = self.table.add_row([p.position_title, p.department_name, format_currency(p.base_salary),
                                     p.employment_type.replace("_", " ").title(), str(p.emp_count), "", None])
            self.table.set_widget(r, 5, Badge("active" if p.is_active else "inactive"))
            actions = action_bar([
                ("\u270F\uFE0F", "ghost", lambda _, pp=p: self.open_edit(pp), "Edit position"),
                ("\U0001F5D1\uFE0F", "danger", lambda _, pp=p: self.archive(pp), "Archive position"),
            ])
            self.table.set_widget(r, 6, actions)

    def _departments(self):
        db = get_db()
        with db.session() as s:
            return rs.list_departments(s)

    def open_add(self):
        depts = self._departments()
        if not depts:
            show_err(self, "No Departments", "Please add a department first.")
            return
        dlg = PositionFormDialog(self, depts)
        dlg.save_btn.clicked.connect(lambda: self._submit_add(dlg))
        dlg.exec()

    def _submit_add(self, dlg):
        dlg.clear_error()
        if not dlg.title_field.text().strip():
            dlg.show_error("Position title is required.")
            return
        db = get_db()
        with db.session() as s:
            result = rs.add_position(
                s, dlg.department.currentData(), dlg.title_field.text().strip(), dlg.salary.value(),
                dlg.emp_type.currentText().lower().replace(" ", "_"), dlg.description.toPlainText().strip(),
                current_session.user_id,
            )
        if not result.success:
            dlg.show_error(result.error)
            return
        dlg.accept()
        self.refresh()

    def open_edit(self, pos_row):
        depts = self._departments()
        dlg = PositionFormDialog(self, depts, editing=pos_row)
        dlg.save_btn.clicked.connect(lambda: self._submit_edit(dlg, pos_row.position_id))
        dlg.exec()

    def _submit_edit(self, dlg, position_id):
        dlg.clear_error()
        db = get_db()
        with db.session() as s:
            result = rs.edit_position(
                s, position_id, dlg.department.currentData(), dlg.title_field.text().strip(), dlg.salary.value(),
                dlg.emp_type.currentText().lower().replace(" ", "_"), dlg.description.toPlainText().strip(),
                dlg.active_check.isChecked(), current_session.user_id,
            )
        if not result.success:
            dlg.show_error(result.error)
            return
        dlg.accept()
        self.refresh()

    def archive(self, pos_row):
        if not confirm(self, "Archive Position?", f'Archive "{pos_row.position_title}"?', danger=True):
            return
        db = get_db()
        with db.session() as s:
            result = rs.archive_position(s, pos_row.position_id, current_session.user_id)
        if result.success:
            self.refresh()
        else:
            show_err(self, "Cannot Archive", result.error)
