"""
ui.admin.attendance_page
============================
Two tabs:
  * Daily Log   — pick a date (calendar popup), see every active
                  employee's Time In / Time Out for that day, tap to
                  record. Tapping captures the real current time; the
                  small \u270e edit button next to either field lets the
                  admin set an exact time instead (override — handy for
                  testing, or fixing a tap that caught the wrong
                  moment). Auto-filled but always overridable, same as
                  the payroll attendance numbers.
  * Reports     — per-employee monthly attendance report (days present/
                  late/absent, total & overtime hours, full daily
                  breakdown), the "employee detail tracking" the spec
                  asked for.

This is the single source of truth ProcessPayrollDialog reads from —
see core/attendance_service.compute_period_summary().
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, time as dtime

from PyQt6.QtCore import QTime
from PyQt6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QSpinBox,
    QTabWidget, QTimeEdit, QVBoxLayout, QWidget,
)

import core.attendance_service as ats
from core.session import current_session
from core.utils import format_time
from database.db_manager import get_db
from ui import theme
from ui.widgets.common import Badge, SectionHeader, StatCard, confirm, make_button, warn
from ui.widgets.table import DataTable

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]


class TimeEditDialog(QDialog):
    """Small popup for setting an exact time-in/time-out — the
    override path alongside the normal tap-to-record flow."""
    def __init__(self, parent, title: str, initial: datetime | None, work_date: date):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.work_date = work_date
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(12)
        lay.addWidget(QLabel(f"Set the exact time for {work_date.strftime('%B %d, %Y')}:"))
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("hh:mm AP")
        self.time_edit.setTime(QTime(initial.hour, initial.minute) if initial else QTime(8, 0))
        lay.addWidget(self.time_edit)
        note = QLabel("This overrides whatever was tapped (or wasn't tapped yet) for this day.")
        note.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        note.setWordWrap(True)
        lay.addWidget(note)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = make_button("Cancel", "ghost")
        cancel_btn.clicked.connect(self.reject)
        save_btn = make_button("Save", "primary")
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        lay.addLayout(btn_row)

    def get_datetime(self) -> datetime:
        t = self.time_edit.time()
        return datetime.combine(self.work_date, dtime(t.hour(), t.minute()))


class DailyLogTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_date = date.today()
        self._suppress_date_signal = False

        lay = QVBoxLayout(self)
        lay.setSpacing(14)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Date:"))
        self.date_edit = QDateEdit(calendarPopup=True)
        self.date_edit.setDisplayFormat("dddd, MMM d, yyyy")
        self.date_edit.setDate(self.selected_date)
        self.date_edit.dateChanged.connect(self._on_date_changed)
        header_row.addWidget(self.date_edit)
        today_btn = make_button("Today", "ghost")
        today_btn.clicked.connect(lambda: self.date_edit.setDate(date.today()))
        header_row.addWidget(today_btn)
        header_row.addStretch()
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        header_row.addWidget(self.summary_label)
        lay.addLayout(header_row)

        self.holiday_banner = QLabel("")
        self.holiday_banner.setWordWrap(True)
        self.holiday_banner.setVisible(False)
        lay.addWidget(self.holiday_banner)

        self.table = DataTable(["Employee", "Department", "Time In", "Time Out", "Status", "Hours", "Mark"])
        self.table.set_col_width(6)
        lay.addWidget(self.table, 1)

        self.refresh()

    # ------------------------------------------------------------------
    def _on_date_changed(self, qdate):
        if self._suppress_date_signal:
            return
        new_date = qdate.toPyDate()
        today = date.today()
        if new_date != today:
            ok = confirm(
                self, "Different Date Selected",
                f"You picked {new_date.strftime('%B %d, %Y')}, but today is "
                f"{today.strftime('%B %d, %Y')}.\n\n"
                f"Any attendance recorded here will be flagged as a back-dated entry. "
                f"Continue with {new_date.strftime('%B %d, %Y')} anyway?",
            )
            if not ok:
                self._suppress_date_signal = True
                self.date_edit.setDate(today)
                self._suppress_date_signal = False
                self.selected_date = today
                self.refresh()
                return
        self.selected_date = new_date
        self.refresh()

    def refresh(self):
        db = get_db()
        with db.session() as s:
            employees = ats.list_active_employees_for_roster(s)
            day_map = ats.list_day_all_employees(s, self.selected_date)
            holiday = ats.get_holiday_for_date(s, self.selected_date)

        if holiday:
            kind = "Regular Holiday" if holiday.holiday_type == "regular" else "Special (Non-Working) Holiday"
            rule = ("Not worked: paid 100% as usual. Worked: paid 200% (100% premium on top)."
                    if holiday.holiday_type == "regular" else
                    "Not worked: no work, no pay. Worked: paid 130% (30% premium on top).")
            self.holiday_banner.setText(f"\U0001F389 <b>{kind}: {holiday.name}</b> \u2014 {rule}")
            accent = theme.PURPLE if holiday.holiday_type == "regular" else theme.WARNING
            self.holiday_banner.setStyleSheet(
                f"background: {theme.rgba(accent, 0.12)}; border: 1px solid {theme.rgba(accent, 0.35)}; "
                f"border-radius: 8px; padding: 10px 14px; color: {theme.TEXT};"
            )
            self.holiday_banner.setVisible(True)
        else:
            self.holiday_banner.setVisible(False)

        self.table.clear_rows()
        present = late = absent = leave = pending = 0
        for emp in employees:
            rec = day_map.get(emp["employee_id"])
            hours_txt = f"{float(rec.hours_worked):.2f} h" if rec and rec.time_out else "—"
            r = self.table.add_row([
                f"{emp['full_name']}  ({emp['employee_code']})", emp["department_name"],
                None, None, None, hours_txt, None,
            ])
            self.table.set_widget(r, 2, self._time_in_widget(emp, rec))
            self.table.set_widget(r, 3, self._time_out_widget(emp, rec))
            self.table.set_widget(r, 4, Badge(rec.status) if rec else Badge("Pending", theme.TEXT_MUTED))
            self.table.set_widget(r, 6, self._mark_widget(emp, rec))

            if rec:
                if rec.status in ("present", "half_day", "holiday"):
                    present += 1
                elif rec.status == "late":
                    late += 1
                elif rec.status == "absent":
                    absent += 1
                elif rec.status == "on_leave":
                    leave += 1
            else:
                pending += 1

        self.summary_label.setText(
            f"{present} present \u00b7 {late} late \u00b7 {absent} absent \u00b7 "
            f"{leave} on leave \u00b7 {pending} not yet recorded"
        )

    # ------------------------------------------------------------------
    def _time_in_widget(self, emp: dict, rec) -> QWidget:
        container = QWidget()
        hl = QHBoxLayout(container)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        if rec and rec.is_time_in_locked:
            lbl = QLabel(format_time(rec.time_in))
            lbl.setStyleSheet(f"color: {theme.SUCCESS if rec.status != 'late' else theme.WARNING}; font-weight: 700;")
            hl.addWidget(lbl)
        else:
            btn = make_button("Tap Time In", "primary", compact=True)
            btn.clicked.connect(lambda _, e=emp: self._do_time_in(e))
            hl.addWidget(btn)
        edit_btn = QPushButton("\u270e")
        edit_btn.setFixedWidth(28)
        edit_btn.setProperty("variant", "ghost")
        edit_btn.setToolTip("Set an exact Time In (override)")
        edit_btn.clicked.connect(lambda _, e=emp, r=rec: self._edit_time_in(e, r))
        hl.addWidget(edit_btn)
        hl.addStretch()
        return container

    def _time_out_widget(self, emp: dict, rec) -> QWidget:
        if not rec or not rec.is_time_in_locked:
            lbl = QLabel("—")
            lbl.setStyleSheet(f"color: {theme.TEXT_MUTED};")
            return lbl
        container = QWidget()
        hl = QHBoxLayout(container)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        if rec.is_time_out_locked:
            lbl = QLabel(format_time(rec.time_out))
            lbl.setStyleSheet(f"color: {theme.SUCCESS}; font-weight: 700;")
            hl.addWidget(lbl)
        else:
            btn = make_button("Tap Time Out", "success", compact=True)
            btn.clicked.connect(lambda _, e=emp: self._do_time_out(e))
            hl.addWidget(btn)
        edit_btn = QPushButton("\u270e")
        edit_btn.setFixedWidth(28)
        edit_btn.setProperty("variant", "ghost")
        edit_btn.setToolTip("Set an exact Time Out (override)")
        edit_btn.clicked.connect(lambda _, e=emp, r=rec: self._edit_time_out(e, r))
        hl.addWidget(edit_btn)
        hl.addStretch()
        return container

    def _mark_widget(self, emp: dict, rec) -> QWidget:
        if rec is not None:
            return QLabel("")
        btn = QPushButton("Mark \u25be")
        btn.setProperty("variant", "ghost")
        menu = QMenu(btn)
        for label, status in [("Absent", "absent"), ("On Leave", "on_leave"),
                               ("Holiday", "holiday"), ("Rest Day", "rest_day")]:
            action = menu.addAction(label)
            action.triggered.connect(lambda _, e=emp, st=status, lb=label: self._do_mark(e, st, lb))
        btn.setMenu(menu)
        return btn

    # ------------------------------------------------------------------
    def _do_time_in(self, emp: dict):
        db = get_db()
        backdated = self.selected_date != date.today()
        with db.session() as s:
            res = ats.record_time_in(s, emp["employee_id"], self.selected_date,
                                      current_session.user_id, backdated=backdated)
        if not res.success:
            warn(self, "Can't Record Time In", res.error)
        self.refresh()

    def _do_time_out(self, emp: dict):
        db = get_db()
        with db.session() as s:
            res = ats.record_time_out(s, emp["employee_id"], self.selected_date, current_session.user_id)
        if not res.success:
            warn(self, "Can't Record Time Out", res.error)
        self.refresh()

    def _edit_time_in(self, emp: dict, rec):
        initial = rec.time_in if rec else None
        dlg = TimeEditDialog(self, f"Set Time In \u2014 {emp['full_name']}", initial, self.selected_date)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_time = dlg.get_datetime()
            db = get_db()
            with db.session() as s:
                res = ats.override_time_in(s, emp["employee_id"], self.selected_date, new_time, current_session.user_id)
            if not res.success:
                warn(self, "Can't Set Time In", res.error)
            self.refresh()

    def _edit_time_out(self, emp: dict, rec):
        initial = rec.time_out if rec else None
        dlg = TimeEditDialog(self, f"Set Time Out \u2014 {emp['full_name']}", initial, self.selected_date)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_time = dlg.get_datetime()
            db = get_db()
            with db.session() as s:
                res = ats.override_time_out(s, emp["employee_id"], self.selected_date, new_time, current_session.user_id)
            if not res.success:
                warn(self, "Can't Set Time Out", res.error)
            self.refresh()

    def _do_mark(self, emp: dict, status: str, label: str):
        ok = confirm(
            self, f"Mark as {label}?",
            f"This will mark {emp['full_name']} as {label} for "
            f"{self.selected_date.strftime('%B %d, %Y')}. Once saved, this can't be changed. Continue?",
        )
        if not ok:
            return
        db = get_db()
        backdated = self.selected_date != date.today()
        with db.session() as s:
            res = ats.mark_special_status(s, emp["employee_id"], self.selected_date, status,
                                           current_session.user_id, backdated=backdated)
        if not res.success:
            warn(self, "Can't Save", res.error)
        self.refresh()


class ReportsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(16)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Employee:"))
        self.employee_combo = QComboBox()
        self.employee_combo.setMinimumWidth(220)
        filter_row.addWidget(self.employee_combo, 1)
        filter_row.addWidget(QLabel("Month:"))
        self.month_combo = QComboBox()
        self.month_combo.addItems(MONTH_NAMES)
        self.month_combo.setCurrentIndex(date.today().month - 1)
        filter_row.addWidget(self.month_combo)
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2020, 2035)
        self.year_spin.setValue(date.today().year)
        filter_row.addWidget(self.year_spin)
        view_btn = make_button("View Report", "primary")
        view_btn.clicked.connect(self.refresh)
        filter_row.addWidget(view_btn)
        lay.addLayout(filter_row)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        self.card_present = StatCard("Days Present", "0", "\u2705", theme.SUCCESS)
        self.card_late = StatCard("Days Late", "0", "\u23F0", theme.WARNING)
        self.card_absent = StatCard("Days Absent", "0", "\U0001F6AB", theme.DANGER)
        self.card_hours = StatCard("Total Hours", "0", "\U0001F550", theme.CYAN)
        self.card_ot = StatCard("Overtime Hours", "0", "\u26A1", theme.PURPLE)
        for c in (self.card_present, self.card_late, self.card_absent, self.card_hours, self.card_ot):
            cards_row.addWidget(c)
        lay.addLayout(cards_row)

        self.table = DataTable(["Date", "Day", "Time In", "Time Out", "Hours", "OT Hours", "Status"])
        lay.addWidget(self.table, 1)

        self._load_employees()
        self.refresh()

    def _load_employees(self):
        db = get_db()
        with db.session() as s:
            employees = ats.list_active_employees_for_roster(s)
        self.employee_combo.clear()
        for e in employees:
            self.employee_combo.addItem(f"{e['full_name']} ({e['employee_code']})", e["employee_id"])

    def refresh(self):
        emp_id = self.employee_combo.currentData()
        if not emp_id:
            self.table.clear_rows()
            return
        year = self.year_spin.value()
        month = self.month_combo.currentIndex() + 1
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])

        db = get_db()
        with db.session() as s:
            rows = ats.list_range(s, emp_id, start, end)
            summary = ats.compute_period_summary(s, emp_id, start, end)

        self.card_present.set_value(f"{summary.days_worked:g}")
        self.card_late.set_value(f"{summary.days_late:g}")
        self.card_absent.set_value(f"{summary.days_absent:g}")
        self.card_hours.set_value(f"{summary.total_hours:.1f}")
        self.card_ot.set_value(f"{summary.overtime_hours:.1f}")

        self.table.clear_rows()
        for rec in rows:
            r = self.table.add_row([
                rec.work_date.strftime("%b %d, %Y"), rec.work_date.strftime("%A"),
                format_time(rec.time_in), format_time(rec.time_out),
                f"{rec.hours_worked:.2f}" if rec.hours_worked else "—",
                f"{rec.overtime_hours:.2f}" if rec.overtime_hours else "—",
                None,
            ])
            self.table.set_widget(r, 6, Badge(rec.status))


class HolidaysTab(QWidget):
    """Company holiday calendar — the single source of truth for
    holiday pay. Payroll cross-references this against each employee's
    actual attendance to apply the DOLE-style regular/special holiday
    rules (see database.models.Holiday)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(14)

        hint = QLabel(
            "Regular holidays: paid 100% even if not worked, 200% if worked. "
            "Special (non-working) holidays: no work no pay, 130% if worked."
        )
        hint.setWordWrap(True)
        hint.setProperty("role", "muted")
        lay.addWidget(hint)

        form_row = QHBoxLayout()
        self.date_edit = QDateEdit(calendarPopup=True)
        self.date_edit.setDisplayFormat("MMM d, yyyy")
        self.date_edit.setDate(date.today())
        form_row.addWidget(self.date_edit)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Holiday name, e.g. Independence Day")
        form_row.addWidget(self.name_edit, 1)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Regular Holiday", "Special (Non-Working) Holiday"])
        form_row.addWidget(self.type_combo)
        add_btn = make_button("+ Add Holiday", "primary")
        add_btn.clicked.connect(self._add_holiday)
        form_row.addWidget(add_btn)
        lay.addLayout(form_row)

        self.table = DataTable(["Date", "Name", "Type", ""])
        lay.addWidget(self.table, 1)

        self.refresh()

    def _add_holiday(self):
        name = self.name_edit.text().strip()
        if not name:
            warn(self, "Name Required", "Please enter a name for this holiday.")
            return
        holiday_type = "regular" if self.type_combo.currentIndex() == 0 else "special"
        work_date = self.date_edit.date().toPyDate()
        db = get_db()
        with db.session() as s:
            res = ats.add_holiday(s, work_date, name, holiday_type, current_session.user_id)
        if not res.success:
            warn(self, "Can't Add Holiday", res.error)
            return
        self.name_edit.clear()
        self.refresh()

    def _delete_holiday(self, holiday_id: int):
        ok = confirm(self, "Remove Holiday?", "This removes it from the holiday calendar. Continue?")
        if not ok:
            return
        db = get_db()
        with db.session() as s:
            ats.delete_holiday(s, holiday_id, current_session.user_id)
        self.refresh()

    def refresh(self):
        db = get_db()
        with db.session() as s:
            holidays = ats.list_holidays(s)
        self.table.clear_rows()
        for h in holidays:
            r = self.table.add_row([h.holiday_date.strftime("%b %d, %Y"), h.name, None, None])
            self.table.set_widget(r, 2, Badge("Regular" if h.holiday_type == "regular" else "Special",
                                               theme.PURPLE if h.holiday_type == "regular" else theme.WARNING))
            del_btn = make_button("Remove", "danger", compact=True)
            del_btn.clicked.connect(lambda _, hid=h.holiday_id: self._delete_holiday(hid))
            self.table.set_widget(r, 3, del_btn)


class AttendancePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        lay.addWidget(SectionHeader(
            "Attendance", "Daily time-in/out tracking — feeds directly into payroll processing"
        ))
        tabs = QTabWidget()
        tabs.addTab(DailyLogTab(), "Daily Log")
        tabs.addTab(ReportsTab(), "Reports")
        tabs.addTab(HolidaysTab(), "Holidays")
        lay.addWidget(tabs, 1)
