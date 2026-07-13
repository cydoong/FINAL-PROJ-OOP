"""
PayrollPro (Python Edition) — Seed Data
==========================================
Populates a *fresh* database (new SQLite file, or an empty MySQL
schema) with the same baseline reference data the original PHP
system shipped with: departments, positions, allowance/deduction
types, and one default administrator account.

This never overwrites existing data — if departments/users already
exist (e.g. you pointed the app at your existing XAMPP payroll_db),
seeding is skipped automatically.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from core.security import hash_password
from database.models import (
    AllowanceType, ContributionRateConfig, DeductionType, Department, Position, TaxBracket, User,
)


DEPARTMENTS = [
    ("Human Resources", "Manages employee relations, recruitment, and HR policies"),
    ("Information Technology", "Handles all IT infrastructure, development, and support"),
    ("Finance & Accounting", "Manages financial records, budgeting, and payroll"),
    ("Operations", "Oversees daily operational activities and logistics"),
    ("Marketing", "Handles brand, promotions, and customer acquisition"),
]

# (department index into DEPARTMENTS, title, base_salary, employment_type)
POSITIONS = [
    (0, "HR Manager", 45000.00, "full_time"),
    (0, "HR Specialist", 28000.00, "full_time"),
    (0, "HR Assistant", 20000.00, "full_time"),
    (1, "IT Manager", 55000.00, "full_time"),
    (1, "Senior Developer", 45000.00, "full_time"),
    (1, "Junior Developer", 28000.00, "full_time"),
    (1, "IT Support", 22000.00, "full_time"),
    (2, "Finance Manager", 50000.00, "full_time"),
    (2, "Accountant", 32000.00, "full_time"),
    (2, "Bookkeeper", 22000.00, "full_time"),
    (3, "Operations Manager", 48000.00, "full_time"),
    (3, "Operations Supervisor", 35000.00, "full_time"),
    (3, "Operations Staff", 20000.00, "full_time"),
    (4, "Marketing Manager", 46000.00, "full_time"),
    (4, "Marketing Specialist", 30000.00, "full_time"),
    (4, "Marketing Assistant", 20000.00, "probationary"),
]

ALLOWANCE_TYPES = [
    # (name, description, is_taxable, auto_type)
    # Regular/Special Holiday Premium are auto-computed each payroll run
    # from the Holiday calendar + Attendance — see core.payroll_engine.
    ("Rice Allowance", "Monthly rice subsidy", False, None),
    ("Transportation", "Daily transportation reimbursement", False, None),
    ("Meal Allowance", "Daily meal subsidy", False, None),
    ("Communication", "Mobile and internet allowance", False, None),
    ("Housing Allowance", "Monthly housing assistance", True, None),
    ("Medical Allowance", "Annual medical reimbursement", False, None),
    ("Performance Bonus", "Quarterly performance-based bonus", True, None),
    ("13th Month Pay", "Annual 13th month salary", False, None),
    ("Regular Holiday Premium", "Extra 100% for working a regular holiday", True, "regular_holiday_premium"),
    ("Special Holiday Premium", "Extra 30% for working a special (non-working) holiday", True, "special_holiday_premium"),
]

DEDUCTION_TYPES = [
    # (name, description, is_mandatory, auto_type)
    # SSS / PhilHealth / Pag-IBIG are auto-computed each payroll run from
    # ContributionRateConfig — no typed amount, no "oops wrong number".
    # Withholding tax isn't in this list at all: it's computed straight
    # onto Payroll.tax_withheld using the TaxBracket table, so it can never
    # be double-counted or accidentally skipped.
    # Late/Absence/Undertime are likewise auto-computed each run from the
    # Attendance log and the employee's actual daily/hourly/minute rate —
    # never a flat guess, never manually typed.
    ("SSS Contribution", "Social Security System monthly contribution", True, "sss"),
    ("PhilHealth Contribution", "Philippine Health Insurance Corporation premium", True, "philhealth"),
    ("Pag-IBIG Contribution", "Home Development Mutual Fund savings", True, "pagibig"),
    ("Late Deduction", "Minute-rate deduction for tardiness", False, "late"),
    ("Absence Deduction", "Daily-rate deduction for unpaid absences", False, "absence"),
    ("Undertime Deduction", "Minute-rate deduction for leaving early", False, "undertime"),
    ("Loan Repayment", "Employee loan amortization", False, None),
    ("Cash Advance", "Salary advance deduction", False, None),
    ("Uniform Deduction", "Company uniform amortization", False, None),
]

# BIR revised withholding-tax table (TRAIN law, RR 11-2018 as amended,
# in effect from 2023 onward). Stored per-period so payroll can withhold
# the right amount regardless of pay frequency. Bi-weekly isn't an
# officially published BIR column, so it's derived by doubling the
# weekly bracket boundaries (2 weekly periods \u2248 1 bi-weekly period) —
# see _double_brackets() below.
# (bracket_order, min_amount, max_amount(None=no cap), base_tax, rate_percent)
TAX_BRACKETS_MONTHLY = [
    (1, 0, 20833, 0, 0.00),
    (2, 20833, 33333, 0, 0.15),
    (3, 33333, 66667, 1875, 0.20),
    (4, 66667, 166667, 8541.80, 0.25),
    (5, 166667, 666667, 33541.80, 0.30),
    (6, 666667, None, 183541.80, 0.35),
]
TAX_BRACKETS_SEMI_MONTHLY = [
    (1, 0, 10417, 0, 0.00),
    (2, 10417, 16667, 0, 0.15),
    (3, 16667, 33333, 937.50, 0.20),
    (4, 33333, 83333, 4270.70, 0.25),
    (5, 83333, 333333, 16770.70, 0.30),
    (6, 333333, None, 91770.70, 0.35),
]
TAX_BRACKETS_WEEKLY = [
    (1, 0, 4808, 0, 0.00),
    (2, 4808, 7692, 0, 0.15),
    (3, 7692, 15385, 432.60, 0.20),
    (4, 15385, 38462, 1971.20, 0.25),
    (5, 38462, 153846, 7740.45, 0.30),
    (6, 153846, None, 42355.65, 0.35),
]


def _double_brackets(brackets):
    return [
        (order, mn * 2, (mx * 2 if mx is not None else None), base * 2, rate)
        for order, mn, mx, base, rate in brackets
    ]


TAX_BRACKETS_BY_PERIOD = {
    "monthly": TAX_BRACKETS_MONTHLY,
    "semi_monthly": TAX_BRACKETS_SEMI_MONTHLY,
    "weekly": TAX_BRACKETS_WEEKLY,
    "bi_weekly": _double_brackets(TAX_BRACKETS_WEEKLY),
}

# SSS / PhilHealth / Pag-IBIG rate configuration (2025\u20132026 schedules).
# (scheme, employee_rate, employer_rate, salary_floor, salary_ceiling, low_tier_ceiling, low_tier_employee_rate)
CONTRIBUTION_RATES = [
    ("sss", 0.05, 0.10, 5000, 35000, None, None),
    ("philhealth", 0.025, 0.025, 10000, 100000, None, None),
    ("pagibig", 0.02, 0.02, 0, 10000, 1500, 0.01),
]


def seed_if_empty(session: Session, admin_password: str = "admin123") -> bool:
    """Seed reference data + default admin if the database looks empty.
    Returns True if seeding actually happened."""
    if session.query(Department).count() > 0 or session.query(User).count() > 0:
        return False  # Already has data (existing XAMPP DB, or already seeded)

    dept_rows = []
    for name, desc in DEPARTMENTS:
        d = Department(department_name=name, description=desc, is_active=True)
        session.add(d)
        dept_rows.append(d)
    session.flush()  # assign IDs

    for dept_idx, title, salary, emp_type in POSITIONS:
        session.add(Position(
            department_id=dept_rows[dept_idx].department_id,
            position_title=title,
            base_salary=salary,
            employment_type=emp_type,
            is_active=True,
        ))

    for name, desc, taxable, auto_type in ALLOWANCE_TYPES:
        session.add(AllowanceType(type_name=name, description=desc, is_taxable=taxable,
                                   is_active=True, auto_type=auto_type))

    for name, desc, mandatory, auto_type in DEDUCTION_TYPES:
        session.add(DeductionType(type_name=name, description=desc, is_mandatory=mandatory,
                                   is_active=True, auto_type=auto_type))

    for period_type, brackets in TAX_BRACKETS_BY_PERIOD.items():
        for order, mn, mx, base, rate in brackets:
            session.add(TaxBracket(
                period_type=period_type, bracket_order=order, min_amount=mn, max_amount=mx,
                base_tax=base, rate_percent=rate, is_active=True,
            ))

    for scheme, ee_rate, er_rate, floor, ceiling, low_ceil, low_ee_rate in CONTRIBUTION_RATES:
        session.add(ContributionRateConfig(
            scheme=scheme, employee_rate=ee_rate, employer_rate=er_rate,
            salary_floor=floor, salary_ceiling=ceiling,
            low_tier_ceiling=low_ceil, low_tier_employee_rate=low_ee_rate,
        ))

    admin = User(
        username="admin",
        password=hash_password(admin_password),
        role="admin",
        is_active=True,
        account_activated=True,
    )
    session.add(admin)

    session.commit()
    return True
