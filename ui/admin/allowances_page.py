"""
ui.admin.allowances_page
============================
Allowance & Deduction type management, exact port of
admin/allowances.php (tabbed: Allowances | Deductions).
"""
from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QLineEdit, QTabWidget, QTextEdit, QVBoxLayout, QWidget

import core.reference_service as rs
from database.db_manager import get_db
from ui import theme
from ui.widgets.common import Badge, SectionHeader, confirm, make_button
from ui.widgets.dialogs import BaseFormDialog
from ui.widgets.table import DataTable, action_bar


class TypeFormDialog(BaseFormDialog):
    def __init__(self, parent, kind: str, editing=None):
        flag_label = "Taxable" if kind == "allowance" else "Mandatory"
        title = f"Edit {kind.title()} Type" if editing else f"Add {kind.title()} Type"
        super().__init__(title, parent=parent, width=440)
        self.name = QLineEdit()
        self.description = QTextEdit()
        self.description.setFixedHeight(60)
        self.flag = QCheckBox(flag_label)
        self.add_row("Name*", self.name)
        self.add_row("Description", self.description)
        self.add_row("", self.flag)
        if editing:
            self.name.setText(editing.type_name)
            self.description.setPlainText(editing.description or "")
            self.flag.setChecked(editing.is_taxable if kind == "allowance" else editing.is_mandatory)


class AllowancesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        header = SectionHeader("Allowances & Deductions", "Manage compensation and deduction types")
        lay.addWidget(header)

        tabs = QTabWidget()
        self.allow_table = DataTable(["Name", "Description", "Taxable", "Actions"])
        self.deduct_table = DataTable(["Name", "Description", "Mandatory", "Actions"])
        allow_wrap = QWidget()
        aw_lay = QVBoxLayout(allow_wrap)
        add_allow_btn = make_button("+ Add Allowance Type", "primary")
        add_allow_btn.clicked.connect(self.open_add_allowance)
        aw_lay.addWidget(add_allow_btn)
        aw_lay.addWidget(self.allow_table)
        deduct_wrap = QWidget()
        dw_lay = QVBoxLayout(deduct_wrap)
        add_deduct_btn = make_button("+ Add Deduction Type", "primary")
        add_deduct_btn.clicked.connect(self.open_add_deduction)
        dw_lay.addWidget(add_deduct_btn)
        dw_lay.addWidget(self.deduct_table)
        tabs.addTab(allow_wrap, "Allowances")
        tabs.addTab(deduct_wrap, "Deductions")
        lay.addWidget(tabs, 1)

        self.refresh()

    def refresh(self):
        db = get_db()
        with db.session() as s:
            allowances = rs.list_allowance_types(s)
            deductions = rs.list_deduction_types(s)

        self.allow_table.clear_rows()
        for a in allowances:
            r = self.allow_table.add_row([a.type_name, a.description or "\u2014", "", None])
            self.allow_table.set_widget(r, 2, Badge("Yes" if a.is_taxable else "No",
                                                       theme.WARNING if a.is_taxable else theme.TEXT_MUTED))
            actions = action_bar([
                ("\u270F\uFE0F", "ghost", lambda _, x=a: self.open_edit_allowance(x), "Edit allowance type"),
                ("\U0001F5D1\uFE0F", "danger", lambda _, x=a: self.delete_allowance(x), "Delete allowance type"),
            ])
            self.allow_table.set_widget(r, 3, actions)

        self.deduct_table.clear_rows()
        for d in deductions:
            r = self.deduct_table.add_row([d.type_name, d.description or "\u2014", "", None])
            self.deduct_table.set_widget(r, 2, Badge("Yes" if d.is_mandatory else "No",
                                                        theme.DANGER if d.is_mandatory else theme.TEXT_MUTED))
            actions = action_bar([
                ("\u270F\uFE0F", "ghost", lambda _, x=d: self.open_edit_deduction(x), "Edit deduction type"),
                ("\U0001F5D1\uFE0F", "danger", lambda _, x=d: self.delete_deduction(x), "Delete deduction type"),
            ])
            self.deduct_table.set_widget(r, 3, actions)

    # ------------------------------------------------------------------
    def open_add_allowance(self):
        dlg = TypeFormDialog(self, "allowance")
        dlg.save_btn.clicked.connect(lambda: self._submit_add_allowance(dlg))
        dlg.exec()

    def _submit_add_allowance(self, dlg):
        dlg.clear_error()
        db = get_db()
        with db.session() as s:
            result = rs.add_allowance_type(s, dlg.name.text().strip(), dlg.description.toPlainText().strip(),
                                            dlg.flag.isChecked())
        if not result.success:
            dlg.show_error(result.error)
            return
        dlg.accept()
        self.refresh()

    def open_edit_allowance(self, row):
        dlg = TypeFormDialog(self, "allowance", editing=row)
        dlg.save_btn.clicked.connect(lambda: self._submit_edit_allowance(dlg, row.allowance_type_id))
        dlg.exec()

    def _submit_edit_allowance(self, dlg, type_id):
        db = get_db()
        with db.session() as s:
            result = rs.edit_allowance_type(s, type_id, dlg.name.text().strip(),
                                             dlg.description.toPlainText().strip(), dlg.flag.isChecked())
        if not result.success:
            dlg.show_error(result.error)
            return
        dlg.accept()
        self.refresh()

    def delete_allowance(self, row):
        if not confirm(self, "Delete Allowance Type?", f'Delete "{row.type_name}"?', danger=True):
            return
        db = get_db()
        with db.session() as s:
            rs.delete_allowance_type(s, row.allowance_type_id)
        self.refresh()

    def open_add_deduction(self):
        dlg = TypeFormDialog(self, "deduction")
        dlg.save_btn.clicked.connect(lambda: self._submit_add_deduction(dlg))
        dlg.exec()

    def _submit_add_deduction(self, dlg):
        dlg.clear_error()
        db = get_db()
        with db.session() as s:
            result = rs.add_deduction_type(s, dlg.name.text().strip(), dlg.description.toPlainText().strip(),
                                            dlg.flag.isChecked())
        if not result.success:
            dlg.show_error(result.error)
            return
        dlg.accept()
        self.refresh()

    def open_edit_deduction(self, row):
        dlg = TypeFormDialog(self, "deduction", editing=row)
        dlg.save_btn.clicked.connect(lambda: self._submit_edit_deduction(dlg, row.deduction_type_id))
        dlg.exec()

    def _submit_edit_deduction(self, dlg, type_id):
        db = get_db()
        with db.session() as s:
            result = rs.edit_deduction_type(s, type_id, dlg.name.text().strip(),
                                             dlg.description.toPlainText().strip(), dlg.flag.isChecked())
        if not result.success:
            dlg.show_error(result.error)
            return
        dlg.accept()
        self.refresh()

    def delete_deduction(self, row):
        if not confirm(self, "Delete Deduction Type?", f'Delete "{row.type_name}"?', danger=True):
            return
        db = get_db()
        with db.session() as s:
            rs.delete_deduction_type(s, row.deduction_type_id)
        self.refresh()
