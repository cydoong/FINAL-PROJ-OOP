"""
PayrollPro (Python Edition) — Database Models
================================================
SQLAlchemy ORM models that mirror the original MySQL schema
(payroll_db) table-for-table, column-for-column. This means:

  * Pointing the app at an EXISTING XAMPP/MySQL `payroll_db` (the one
    created by the original PHP system) works immediately — same
    tables, same columns, your existing employees/payroll/audit
    history is read and used as-is.
  * Pointing the app at a fresh SQLite file auto-creates the same
    schema (SQLite doesn't support stored procedures/views/triggers,
    so that logic is re-implemented in pure Python inside
    core/payroll_engine.py, core/auth.py and core/audit.py instead —
    behaviour is identical on both backends).

Original stored procedures (sp_process_payroll, sp_finalize_payroll,
sp_payroll_report) and triggers (trg_employee_status_change,
trg_payroll_status_change) are reproduced as plain Python functions
so the exact same code path runs regardless of which database engine
is active underneath.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────
#  Reference / lookup tables
# ─────────────────────────────────────────────────────────────────────────

class Department(Base):
    __tablename__ = "departments"

    department_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    head_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)

    positions = relationship("Position", back_populates="department", cascade="all, delete-orphan")
    employees = relationship("Employee", back_populates="department")


class Position(Base):
    __tablename__ = "positions"

    position_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.department_id", onupdate="CASCADE"), nullable=False)
    position_title: Mapped[str] = mapped_column(String(100), nullable=False)
    base_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    employment_type: Mapped[str] = mapped_column(
        Enum("full_time", "part_time", "contractual", "probationary", name="employment_type_enum"),
        nullable=False, default="full_time",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)

    department = relationship("Department", back_populates="positions")
    employees = relationship("Employee", back_populates="position")


class PositionArchive(Base):
    __tablename__ = "positions_archive"

    archive_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(Integer, nullable=False)
    department_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    department_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    position_title: Mapped[str] = mapped_column(String(100), nullable=False)
    base_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    employment_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    archived_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)


class AllowanceType(Base):
    __tablename__ = "allowance_types"

    allowance_type_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_taxable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Same idea as DeductionType.auto_type: when set, payroll computes and
    # inserts this allowance automatically (holiday premium pay) instead
    # of it being a manually-typed line item.
    auto_type: Mapped[str | None] = mapped_column(
        Enum("regular_holiday_premium", "special_holiday_premium", name="allowance_auto_type_enum"),
        nullable=True,
    )


class DeductionType(Base):
    __tablename__ = "deduction_types"

    deduction_type_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # When set, payroll processing computes this deduction automatically
    # instead of a typed-in amount — sss/philhealth/pagibig from the
    # employee's basic salary via ContributionRateConfig; late/absence/
    # undertime from the Attendance log via the employee's daily/hourly/
    # minute rate. NULL means it's a manual/variable deduction (cash
    # advance, loan, etc).
    auto_type: Mapped[str | None] = mapped_column(
        Enum("sss", "philhealth", "pagibig", "late", "absence", "undertime",
             name="deduction_auto_type_enum"), nullable=True,
    )



# ─────────────────────────────────────────────────────────────────────────
#  Users / Auth
# ─────────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(Enum("admin", "employee", name="user_role_enum"), nullable=False, default="employee")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reset_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    passcode: Mapped[str | None] = mapped_column(String(16), nullable=True, unique=True)
    account_activated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auth_email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    auth_phone: Mapped[str | None] = mapped_column(String(25), nullable=True)
    otp_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    otp_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    otp_purpose: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now, onupdate=dt.datetime.now)

    employee = relationship("Employee", back_populates="user", uselist=False)


class Employee(Base):
    __tablename__ = "employees"

    employee_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, unique=True)
    employee_code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    first_name: Mapped[str] = mapped_column(String(60), nullable=False)
    last_name: Mapped[str] = mapped_column(String(60), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    email: Mapped[str | None] = mapped_column(String(150), nullable=True, unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    gender: Mapped[str | None] = mapped_column(Enum("male", "female", "other", name="gender_enum"), nullable=True)
    birthdate: Mapped[dt.date | None] = mapped_column(DateTime, nullable=True)
    hire_date: Mapped[dt.date] = mapped_column(DateTime, nullable=False)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.department_id"), nullable=False)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.position_id"), nullable=False)
    employment_status: Mapped[str] = mapped_column(
        Enum("active", "inactive", "terminated", "on_leave", name="employment_status_enum"),
        nullable=False, default="active",
    )
    sss_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    philhealth_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pagibig_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tin_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_account: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Flexible payout method — most small/medium PH employers don't pay
    # everyone by bank transfer, so this drives which of the fields below
    # are actually required/shown (see core.employee_service + the
    # Employee form dialog for the show/hide-by-selection logic).
    payment_method: Mapped[str] = mapped_column(
        Enum("bank_transfer", "gcash", "maya", "cash", "check", name="payment_method_enum"),
        nullable=False, default="bank_transfer",
    )
    gcash_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    maya_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    profile_photo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now, onupdate=dt.datetime.now)

    user = relationship("User", back_populates="employee")
    department = relationship("Department", back_populates="employees")
    position = relationship("Position", back_populates="employees")
    payrolls = relationship("Payroll", back_populates="employee")
    attendance_records = relationship("Attendance", back_populates="employee", cascade="all, delete-orphan")
    daily_attendance = relationship("DailyAttendance", back_populates="employee", cascade="all, delete-orphan")

    @property
    def payment_method_label(self) -> str:
        return {
            "bank_transfer": "Bank Transfer", "gcash": "GCash", "maya": "Maya",
            "cash": "Cash", "check": "Check",
        }.get(self.payment_method, self.payment_method.title())

    @property
    def payment_detail(self) -> str:
        """Human-readable payout destination for payslips/receipts."""
        if self.payment_method == "bank_transfer":
            bank = self.bank_name or "Bank"
            acct = self.bank_account or "\u2014"
            return f"{bank} \u2013 {acct}"
        if self.payment_method == "gcash":
            return self.gcash_number or "\u2014"
        if self.payment_method == "maya":
            return self.maya_number or "\u2014"
        return self.payment_method_label

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class EmployeeArchive(Base):
    __tablename__ = "employees_archive"

    archive_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employee_code: Mapped[str] = mapped_column(String(20), nullable=False)
    username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    first_name: Mapped[str] = mapped_column(String(60), nullable=False)
    last_name: Mapped[str] = mapped_column(String(60), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    birthdate: Mapped[dt.date | None] = mapped_column(DateTime, nullable=True)
    hire_date: Mapped[dt.date | None] = mapped_column(DateTime, nullable=True)
    department_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    department_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    position_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    employment_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    sss_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    philhealth_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pagibig_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tin_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_account: Mapped[str | None] = mapped_column(String(30), nullable=True)
    archived_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    archived_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)
    archive_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


# ─────────────────────────────────────────────────────────────────────────
#  Pay periods / Payroll
# ─────────────────────────────────────────────────────────────────────────

class PayPeriod(Base):
    __tablename__ = "pay_periods"

    period_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period_name: Mapped[str] = mapped_column(String(100), nullable=False)
    period_type: Mapped[str] = mapped_column(
        Enum("weekly", "bi_weekly", "semi_monthly", "monthly", name="period_type_enum"),
        nullable=False, default="monthly",
    )
    start_date: Mapped[dt.date] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(DateTime, nullable=False)
    pay_date: Mapped[dt.date] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("open", "processing", "closed", name="period_status_enum"), nullable=False, default="open"
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)

    payrolls = relationship("Payroll", back_populates="period")
    attendance_records = relationship("Attendance", back_populates="period", cascade="all, delete-orphan")


class Payroll(Base):
    __tablename__ = "payroll"
    __table_args__ = (UniqueConstraint("employee_id", "period_id", name="unique_payroll"),)

    payroll_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.employee_id"), nullable=False)
    period_id: Mapped[int] = mapped_column(ForeignKey("pay_periods.period_id"), nullable=False)
    basic_pay: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    daily_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    standard_days: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    days_worked: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    days_absent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    days_late: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    late_minutes: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False, default=0)
    undertime_minutes: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False, default=0)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    overtime_pay: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    gross_pay: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_allowances: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_deductions: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    net_pay: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_withheld: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    # Snapshot of how this specific run was paid out — kept separate from
    # Employee.payment_method so historical payslips stay accurate even if
    # the employee later switches banks/e-wallets.
    payment_method_used: Mapped[str | None] = mapped_column(
        Enum("bank_transfer", "gcash", "maya", "cash", "check", name="payroll_payment_method_enum"),
        nullable=True,
    )
    payment_detail_used: Mapped[str | None] = mapped_column(String(150), nullable=True)
    payroll_status: Mapped[str] = mapped_column(
        Enum("draft", "approved", "paid", "cancelled", name="payroll_status_enum"), nullable=False, default="draft"
    )
    processed_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    processed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now, onupdate=dt.datetime.now)

    employee = relationship("Employee", back_populates="payrolls")
    period = relationship("PayPeriod", back_populates="payrolls")
    allowances = relationship("PayrollAllowance", back_populates="payroll", cascade="all, delete-orphan")
    deductions = relationship("PayrollDeduction", back_populates="payroll", cascade="all, delete-orphan")


class PayrollAllowance(Base):
    __tablename__ = "payroll_allowances"

    pa_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payroll_id: Mapped[int] = mapped_column(ForeignKey("payroll.payroll_id", ondelete="CASCADE"), nullable=False)
    allowance_type_id: Mapped[int] = mapped_column(ForeignKey("allowance_types.allowance_type_id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)

    payroll = relationship("Payroll", back_populates="allowances")
    allowance_type = relationship("AllowanceType")


class PayrollDeduction(Base):
    __tablename__ = "payroll_deductions"

    pd_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payroll_id: Mapped[int] = mapped_column(ForeignKey("payroll.payroll_id", ondelete="CASCADE"), nullable=False)
    deduction_type_id: Mapped[int] = mapped_column(ForeignKey("deduction_types.deduction_type_id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)

    payroll = relationship("Payroll", back_populates="deductions")
    deduction_type = relationship("DeductionType")


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("employee_id", "period_id", name="unique_att"),)

    attendance_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.employee_id", ondelete="CASCADE"), nullable=False)
    period_id: Mapped[int] = mapped_column(ForeignKey("pay_periods.period_id", ondelete="CASCADE"), nullable=False)
    days_worked: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    days_absent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    days_late: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    overtime_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("1.25"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)

    employee = relationship("Employee", back_populates="attendance_records")
    period = relationship("PayPeriod", back_populates="attendance_records")


class DailyAttendance(Base):
    """Daily time-in/time-out log kept by the admin (front-desk style).

    This is the source of truth for the aggregate Attendance rows above:
    once a pay period is processed, days_worked/overtime_hours/etc. are
    computed from these daily records instead of being typed in by hand.

    time_in/time_out are captured as `datetime.now()` at the moment the
    admin taps the button — never hand-entered — and each becomes
    immutable (see is_time_in_locked/is_time_out_locked) the instant it's
    set, so the log can't quietly be edited after the fact.
    """
    __tablename__ = "daily_attendance"
    __table_args__ = (UniqueConstraint("employee_id", "work_date", name="unique_daily_attendance"),)

    daily_attendance_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.employee_id", ondelete="CASCADE"), nullable=False)
    work_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    time_in: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    time_out: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    is_time_in_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_time_out_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        Enum("present", "late", "half_day", "absent", "on_leave", "holiday", "rest_day",
             name="daily_attendance_status_enum"),
        nullable=False, default="present",
    )
    hours_worked: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    # Minutes late (from the exact shift start — grace period only
    # forgives the "late" status label, not the deduction; see
    # core.attendance_service) and minutes left early. Both feed the
    # auto-computed Late/Undertime payroll deductions.
    late_minutes: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    undertime_minutes: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    # True if the admin picked a work_date that didn't match "today" when the
    # record was made and chose to proceed anyway after the warning prompt.
    backdated_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now, onupdate=dt.datetime.now)

    employee = relationship("Employee", back_populates="daily_attendance")


class TaxBracket(Base):
    """BIR withholding-tax brackets, one row per bracket per pay-period type.

    Stored in the database (rather than hardcoded percentages) so the
    figures can be updated the day BIR revises them, with no code change —
    per the guide's recommendation. Seeded with the 2023-onward TRAIN law
    revised withholding tax table.
    """
    __tablename__ = "tax_brackets"

    bracket_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period_type: Mapped[str] = mapped_column(
        Enum("weekly", "bi_weekly", "semi_monthly", "monthly", name="tax_bracket_period_enum"),
        nullable=False,
    )
    bracket_order: Mapped[int] = mapped_column(Integer, nullable=False)
    min_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    max_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    base_tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ContributionRateConfig(Base):
    """Editable SSS / PhilHealth / Pag-IBIG rate configuration.

    One row per scheme. Kept as plain rate/floor/ceiling numbers (rather
    than a giant bracket table) since all three currently reduce to "a
    percentage of salary, clamped to a floor/ceiling, split employee vs
    employer" — Pag-IBIG's lower 1% tier is the one exception, handled by
    low_tier_ceiling/low_tier_employee_rate. Admin-editable under
    Settings ▸ Gov't Rates so the office doesn't need a code change every
    time SSS/PhilHealth/Pag-IBIG revise their schedule.
    """
    __tablename__ = "contribution_rate_config"

    config_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scheme: Mapped[str] = mapped_column(
        Enum("sss", "philhealth", "pagibig", name="contribution_scheme_enum"), nullable=False, unique=True,
    )
    employee_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=0)
    employer_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=0)
    salary_floor: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    salary_ceiling: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    low_tier_ceiling: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    low_tier_employee_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now, onupdate=dt.datetime.now)


class Holiday(Base):
    """Company holiday calendar — the source of truth for holiday pay.
    Payroll checks, for each date in a pay period that appears here,
    whether each employee actually worked that day (has a time_in in
    DailyAttendance) and applies the DOLE-style treatment:
      regular + worked     -> +100% premium on top of the normal day
      regular + not worked -> no change (already paid as a normal day)
      special + worked     -> +30% premium on top of the normal day
      special + not worked -> that day is excluded from paid standard
                               days entirely ("no work, no pay")
    See core/attendance_service.py's holiday helpers and
    core/payroll_engine.py's finalize_payroll().
    """
    __tablename__ = "holidays"

    holiday_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    holiday_date: Mapped[dt.date] = mapped_column(Date, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    holiday_type: Mapped[str] = mapped_column(
        Enum("regular", "special", name="holiday_type_enum"), nullable=False, default="regular",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)

class AuditLog(Base):
    __tablename__ = "audit_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    table_affected: Mapped[str | None] = mapped_column(String(50), nullable=True)
    record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    logged_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)


class NotificationLog(Base):
    __tablename__ = "notification_log"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel: Mapped[str] = mapped_column(Enum("email", "sms", name="notif_channel_enum"), nullable=False)
    notif_type: Mapped[str] = mapped_column(String(50), nullable=False)
    recipient: Mapped[str] = mapped_column(String(150), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(Enum("sent", "failed", name="notif_status_enum"), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)


ALL_MODELS = [
    Department, Position, PositionArchive, AllowanceType, DeductionType,
    User, Employee, EmployeeArchive, PayPeriod, Payroll, PayrollAllowance,
    PayrollDeduction, Attendance, DailyAttendance, TaxBracket, ContributionRateConfig,
    Holiday, AuditLog, NotificationLog,
]
