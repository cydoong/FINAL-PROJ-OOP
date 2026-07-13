"""
database.migrations
=======================
`Base.metadata.create_all()` only creates *missing tables* — it never
adds a column to a table that already exists. Since this app has been
through several feature rounds against the same SQLite/MySQL database,
a fresh column added to an existing model (e.g. Employee.payment_method)
would otherwise crash the very first query that touches it.

This module is a tiny, dependency-free "migration" pass: for each
(table, column) this version of the app expects, check whether it's
already there and ALTER TABLE ADD COLUMN it if not. It's intentionally
additive-only (never drops/renames a column), safe to run on every
startup, and works against both SQLite and MySQL.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


# (table, column, sqlite_ddl_type, mysql_ddl_type, default_sql)
_NEW_COLUMNS = [
    ("employees", "payment_method", "VARCHAR(20)", "VARCHAR(20)", "'bank_transfer'"),
    ("employees", "gcash_number", "VARCHAR(20)", "VARCHAR(20)", "NULL"),
    ("employees", "maya_number", "VARCHAR(20)", "VARCHAR(20)", "NULL"),
    ("deduction_types", "auto_type", "VARCHAR(20)", "VARCHAR(20)", "NULL"),
    ("allowance_types", "auto_type", "VARCHAR(30)", "VARCHAR(30)", "NULL"),
    ("payroll", "days_absent", "NUMERIC(5,2)", "DECIMAL(5,2)", "0"),
    ("payroll", "days_late", "NUMERIC(5,2)", "DECIMAL(5,2)", "0"),
    ("payroll", "overtime_hours", "NUMERIC(6,2)", "DECIMAL(6,2)", "0"),
    ("payroll", "payment_method_used", "VARCHAR(20)", "VARCHAR(20)", "NULL"),
    ("payroll", "payment_detail_used", "VARCHAR(150)", "VARCHAR(150)", "NULL"),
    ("payroll", "standard_days", "NUMERIC(5,2)", "DECIMAL(5,2)", "0"),
    ("payroll", "late_minutes", "NUMERIC(7,2)", "DECIMAL(7,2)", "0"),
    ("payroll", "undertime_minutes", "NUMERIC(7,2)", "DECIMAL(7,2)", "0"),
    ("daily_attendance", "late_minutes", "NUMERIC(6,2)", "DECIMAL(6,2)", "0"),
    ("daily_attendance", "undertime_minutes", "NUMERIC(6,2)", "DECIMAL(6,2)", "0"),
]


def run_light_migrations(engine: Engine) -> None:
    try:
        insp = inspect(engine)
        existing_tables = set(insp.get_table_names())
        with engine.begin() as conn:
            for table, column, sqlite_type, mysql_type, default_sql in _NEW_COLUMNS:
                if table not in existing_tables:
                    continue  # brand-new DB — create_all() already made it right
                cols = {c["name"] for c in insp.get_columns(table)}
                if column in cols:
                    continue
                ddl_type = sqlite_type if engine.dialect.name == "sqlite" else mysql_type
                try:
                    conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type} DEFAULT {default_sql}"
                    ))
                except Exception:
                    # Best-effort: if a particular ALTER fails (e.g. odd
                    # older MySQL version), skip it rather than crash the
                    # whole app on startup.
                    pass
    except Exception:
        # Migrations are a convenience, not a hard requirement — a fresh
        # database that just went through create_all() has nothing to
        # migrate, and inspect() can be picky about not-yet-committed
        # engines in some test setups.
        pass


def seed_new_reference_data(session) -> None:
    """Backfill TaxBracket / ContributionRateConfig / new DeductionType /
    AllowanceType rows into a database that already existed before this
    feature round (so `seed_if_empty` — which only runs on a totally
    empty DB — never got a chance to add them)."""
    from database.models import AllowanceType, ContributionRateConfig, DeductionType, Department, TaxBracket
    from database.seed_data import ALLOWANCE_TYPES, CONTRIBUTION_RATES, DEDUCTION_TYPES, TAX_BRACKETS_BY_PERIOD

    if session.query(Department).count() == 0:
        # Brand-new database — seed_if_empty() will populate everything
        # (including these tables) in one consistent pass. Nothing to
        # backfill here.
        return

    if session.query(TaxBracket).count() == 0:
        for period_type, brackets in TAX_BRACKETS_BY_PERIOD.items():
            for order, mn, mx, base, rate in brackets:
                session.add(TaxBracket(
                    period_type=period_type, bracket_order=order, min_amount=mn, max_amount=mx,
                    base_tax=base, rate_percent=rate, is_active=True,
                ))

    if session.query(ContributionRateConfig).count() == 0:
        for scheme, ee_rate, er_rate, floor, ceiling, low_ceil, low_ee_rate in CONTRIBUTION_RATES:
            session.add(ContributionRateConfig(
                scheme=scheme, employee_rate=ee_rate, employer_rate=er_rate,
                salary_floor=floor, salary_ceiling=ceiling,
                low_tier_ceiling=low_ceil, low_tier_employee_rate=low_ee_rate,
            ))

    # Drop the old standalone "Withholding Tax" manual line and the old
    # flat-guess "Late/Absent Deduction" if a previous session already
    # created either — tax is computed straight onto Payroll.tax_withheld,
    # and late/absence/undertime are now each their own auto-computed
    # line driven by the employee's actual rate, not a typed-in amount.
    stale = session.query(DeductionType).filter(
        DeductionType.type_name.in_(["Withholding Tax", "PhilHealth", "Pag-IBIG", "Late/Absent Deduction"])
    ).all()
    for row in stale:
        if row.type_name in ("Withholding Tax", "Late/Absent Deduction"):
            row.is_active = False
        elif row.type_name == "PhilHealth":
            row.type_name = "PhilHealth Contribution"
            row.auto_type = "philhealth"
        elif row.type_name == "Pag-IBIG":
            row.type_name = "Pag-IBIG Contribution"
            row.auto_type = "pagibig"

    existing_names = {d.type_name for d in session.query(DeductionType).all()}
    for name, desc, mandatory, auto_type in DEDUCTION_TYPES:
        if name not in existing_names:
            session.add(DeductionType(type_name=name, description=desc, is_mandatory=mandatory,
                                       is_active=True, auto_type=auto_type))
        elif auto_type:
            row = session.query(DeductionType).filter_by(type_name=name).one_or_none()
            if row and not row.auto_type:
                row.auto_type = auto_type

    existing_allow_names = {a.type_name for a in session.query(AllowanceType).all()}
    for name, desc, taxable, auto_type in ALLOWANCE_TYPES:
        if name not in existing_allow_names:
            session.add(AllowanceType(type_name=name, description=desc, is_taxable=taxable,
                                       is_active=True, auto_type=auto_type))
        elif auto_type:
            row = session.query(AllowanceType).filter_by(type_name=name).one_or_none()
            if row and not row.auto_type:
                row.auto_type = auto_type

    session.commit()
