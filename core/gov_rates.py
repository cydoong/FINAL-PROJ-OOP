"""
core.gov_rates
=================
Computes SSS / PhilHealth / Pag-IBIG contributions and BIR withholding
tax from the database-backed rate tables (ContributionRateConfig,
TaxBracket) instead of hardcoded percentages, so the office can update
figures the day the government revises them — no code change, no
redeploy. See database/models.py for why these two are shaped
differently (contributions are flat-rate-on-clamped-salary; tax is
progressive/bracketed).
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import ContributionRateConfig, TaxBracket


def _d(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def round2(value) -> Decimal:
    return _d(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class ContributionResult(NamedTuple):
    employee_share: Decimal
    employer_share: Decimal


_DEFAULT_RATES = {
    # Fallback figures if the config table is ever empty (e.g. someone
    # wiped the reference tables by hand) — matches the seeded defaults.
    "sss": (Decimal("0.05"), Decimal("0.10"), Decimal("5000"), Decimal("35000"), None, None),
    "philhealth": (Decimal("0.025"), Decimal("0.025"), Decimal("10000"), Decimal("100000"), None, None),
    "pagibig": (Decimal("0.02"), Decimal("0.02"), Decimal("0"), Decimal("10000"), Decimal("1500"), Decimal("0.01")),
}


_PERIODS_PER_YEAR = {"monthly": 12, "semi_monthly": 24, "bi_weekly": 26, "weekly": 52}
AVG_DAYS_PER_MONTH = Decimal("30.4368")  # 365.25 / 12


def period_days_between(start_date, end_date) -> int:
    """Inclusive day count for a pay period's date range."""
    return (end_date - start_date).days + 1


def period_proration_factor(period_days: int) -> Decimal:
    """SSS/PhilHealth/Pag-IBIG schedules are monthly figures. Prorate by
    the pay period's *actual calendar length* (not by an admin-selected
    'period type' label) so a mislabeled period — say, one that's
    really a full month but got tagged "weekly" by mistake — can't
    silently shrink a month's worth of contributions down to a
    fraction of what they should be. A real 30-day period always
    prorates to ~1.0 regardless of what its type label says."""
    return (_d(period_days) / AVG_DAYS_PER_MONTH).quantize(Decimal("0.000001"))


def effective_tax_period_type(period_days: int) -> str:
    """Picks which BIR bracket table actually matches this period's real
    length. This is deliberately based on the *dates*, not the stored
    period_type — a period tagged 'weekly' that actually spans a month
    would otherwise get taxed on the weekly table, which assumes a much
    smaller weekly income and pushes a full month's pay into brackets
    meant for a fraction of that amount (wildly overtaxing it)."""
    if period_days <= 3:
        return "daily"
    if period_days <= 10:
        return "weekly"
    if period_days <= 20:
        return "semi_monthly"
    if period_days <= 35:
        return "monthly"
    return "monthly"  # unusually long period — annualize() below handles it


def get_contribution_config(session: Session, scheme: str) -> ContributionRateConfig | None:
    return session.execute(
        select(ContributionRateConfig).where(ContributionRateConfig.scheme == scheme)
    ).scalar_one_or_none()


def compute_contribution(session: Session, scheme: str, monthly_basic_salary) -> ContributionResult:
    """Employee/employer shares for sss/philhealth/pagibig, given the
    employee's *monthly basic salary* (not gross-with-allowances —
    that's how SSS/PhilHealth/Pag-IBIG define "compensation")."""
    salary = _d(monthly_basic_salary)
    cfg = get_contribution_config(session, scheme)
    if cfg:
        ee_rate, er_rate = _d(cfg.employee_rate), _d(cfg.employer_rate)
        floor, ceiling = _d(cfg.salary_floor), _d(cfg.salary_ceiling)
        low_ceiling = _d(cfg.low_tier_ceiling) if cfg.low_tier_ceiling is not None else None
        low_ee_rate = _d(cfg.low_tier_employee_rate) if cfg.low_tier_employee_rate is not None else None
    else:
        ee_rate, er_rate, floor, ceiling, low_ceiling, low_ee_rate = _DEFAULT_RATES[scheme]

    base = max(floor, min(salary, ceiling)) if floor > 0 else min(salary, ceiling)
    if scheme == "pagibig":
        # Pag-IBIG bases the *rate* on the actual salary tier, but the
        # *peso amount* on the ceiling-clamped base.
        base = min(salary, ceiling)
        effective_ee_rate = low_ee_rate if (low_ceiling is not None and salary <= low_ceiling) else ee_rate
    else:
        effective_ee_rate = ee_rate

    employee_share = round2(base * effective_ee_rate)
    employer_share = round2(base * er_rate)
    return ContributionResult(employee_share, employer_share)


def employee_has_scheme_number(employee, scheme: str) -> bool:
    """Whether the employee has the government-issued number on file
    for this scheme. An employee with no SSS number, for instance,
    isn't registered with SSS yet, so nothing should be withheld for
    it — deducting a contribution the employee can't actually remit
    doesn't make sense."""
    value = {
        "sss": getattr(employee, "sss_number", None),
        "philhealth": getattr(employee, "philhealth_number", None),
        "pagibig": getattr(employee, "pagibig_number", None),
    }.get(scheme)
    return bool(value and value.strip())


SCHEME_LABELS = {"sss": "SSS", "philhealth": "PhilHealth", "pagibig": "Pag-IBIG"}


def compute_all_contributions(session: Session, monthly_basic_salary) -> dict[str, ContributionResult]:
    return {
        scheme: compute_contribution(session, scheme, monthly_basic_salary)
        for scheme in ("sss", "philhealth", "pagibig")
    }


def get_tax_brackets(session: Session, period_type: str) -> list[TaxBracket]:
    rows = session.execute(
        select(TaxBracket)
        .where(TaxBracket.period_type == period_type, TaxBracket.is_active == True)  # noqa: E712
        .order_by(TaxBracket.bracket_order)
    ).scalars().all()
    return list(rows)


def compute_withholding_tax(session: Session, taxable_income, period_days: int) -> Decimal:
    """Progressive BIR withholding tax on `taxable_income` (gross pay
    minus mandatory SSS/PhilHealth/Pag-IBIG contributions), selecting
    the bracket table that actually matches this period's real number
    of days — see effective_tax_period_type() for why that matters."""
    income = _d(taxable_income)
    if income <= 0:
        return Decimal("0.00")

    period_type = effective_tax_period_type(period_days)
    brackets = get_tax_brackets(session, period_type)
    if not brackets:
        brackets = get_tax_brackets(session, "monthly")
        period_type = "monthly"
    if not brackets:
        return Decimal("0.00")  # no tax tables configured at all

    # Unusually long/short periods (rare — most periods land squarely in
    # one of the 4 standard buckets) get annualized against the monthly
    # table instead of forcing them into a bucket that doesn't really fit.
    if period_days > 35 and period_type == "monthly":
        months = _d(period_days) / AVG_DAYS_PER_MONTH
        monthly_equivalent_income = income / months if months > 0 else income
        monthly_tax = _tax_from_brackets(brackets, monthly_equivalent_income)
        return round2(monthly_tax * months)

    tax = _tax_from_brackets(brackets, income)
    return round2(max(tax, Decimal("0.00")))


def _tax_from_brackets(brackets: list[TaxBracket], income: Decimal) -> Decimal:
    chosen: Optional[TaxBracket] = None
    for b in brackets:
        mn = _d(b.min_amount)
        mx = _d(b.max_amount) if b.max_amount is not None else None
        if income >= mn and (mx is None or income < mx):
            chosen = b
            break
    if chosen is None:
        chosen = brackets[-1]
    excess = income - _d(chosen.min_amount)
    return _d(chosen.base_tax) + excess * _d(chosen.rate_percent)
