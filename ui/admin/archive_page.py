"""
ui.admin.archive_page
=========================
Restore/purge for archived employees and positions, exact port of
admin/archive.php.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

import core.archive_service as ars
from core.session import current_session
from core.utils import format_currency, format_datetime
from database.db_manager import get_db
from ui.widgets.common import SectionHeader, confirm, error as show_err, info as show_info
from ui.widgets.table import DataTable, action_bar


class ArchivePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        header = SectionHeader("Archive", "Restore or permanently remove archived records")
        lay.addWidget(header)

        tabs = QTabWidget()
        self.emp_table = DataTable(["Employee", "Code", "Department", "Position", "Archived At", "Actions"])
        self.pos_table = DataTable(["Position", "Department", "Salary", "Archived At", "Actions"])
        tabs.addTab(self.emp_table, "Archived Employees")
        tabs.addTab(self.pos_table, "Archived Positions")
        lay.addWidget(tabs, 1)

        self.refresh()

    def refresh(self):
        db = get_db()
        with db.session() as s:
            employees = ars.list_archived_employees(s)
            positions = ars.list_archived_positions(s)

        self.emp_table.clear_rows()
        for e in employees:
            r = self.emp_table.add_row([
                f"{e.first_name} {e.last_name}", e.employee_code, e.department_name or "\u2014",
                e.position_title or "\u2014", format_datetime(e.archived_at), None,
            ])
            actions = action_bar([
                ("\u267B\uFE0F", "primary", lambda _, x=e: self.restore_employee(x), "Restore this employee"),
                ("\U0001F5D1\uFE0F", "danger", lambda _, x=e: self.purge_employee(x), "Permanently delete"),
            ])
            self.emp_table.set_widget(r, 5, actions)

        self.pos_table.clear_rows()
        for p in positions:
            r = self.pos_table.add_row([
                p.position_title, p.department_name or "\u2014", format_currency(p.base_salary),
                format_datetime(p.archived_at), None,
            ])
            actions = action_bar([
                ("\u267B\uFE0F", "primary", lambda _, x=p: self.restore_position(x), "Restore this position"),
                ("\U0001F5D1\uFE0F", "danger", lambda _, x=p: self.purge_position(x), "Permanently delete"),
            ])
            self.pos_table.set_widget(r, 4, actions)

    def restore_employee(self, arc):
        if not confirm(self, "Restore Employee?", f"Restore {arc.first_name} {arc.last_name}?"):
            return
        db = get_db()
        with db.session() as s:
            result = ars.restore_employee(s, arc.archive_id, current_session.user_id)
        if not result.success:
            show_err(self, "Cannot Restore", result.error)
            return
        msg = f"{result.data['name']} restored as {result.data['employee_code']}."
        if result.data.get("new_passcode"):
            msg += f"\nNew passcode: {result.data['new_passcode']}"
        show_info(self, "Restored", msg)
        self.refresh()

    def purge_employee(self, arc):
        if not confirm(self, "Permanently Delete?",
                        f"Permanently delete the archived record for {arc.first_name} {arc.last_name}? "
                        f"This cannot be undone.", danger=True):
            return
        db = get_db()
        with db.session() as s:
            ars.purge_employee(s, arc.archive_id, current_session.user_id)
        self.refresh()

    def restore_position(self, arc):
        if not confirm(self, "Restore Position?", f'Restore "{arc.position_title}"?'):
            return
        db = get_db()
        with db.session() as s:
            result = ars.restore_position(s, arc.archive_id, current_session.user_id)
        if not result.success:
            show_err(self, "Cannot Restore", result.error)
            return
        self.refresh()

    def purge_position(self, arc):
        if not confirm(self, "Permanently Delete?", f'Permanently delete "{arc.position_title}"?', danger=True):
            return
        db = get_db()
        with db.session() as s:
            ars.purge_position(s, arc.archive_id, current_session.user_id)
        self.refresh()
