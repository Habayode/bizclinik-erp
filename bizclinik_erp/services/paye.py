"""Nigerian PAYE — graduated bands per CITA.

Replaces the flat per-employee `paye_rate` model with proper graduated
calculation. Used by services.payroll.run_payroll().

Bands and reliefs are kept as module-level constants so they're easy to
update when FIRS revises the rates (next expected: 2025/26 budget cycle).

Calculation (annual):
    chargeable = gross_annual − consolidated_relief_allowance − pension_contribution
    paye_annual = sum(rate × min(remaining_chargeable, band_width))
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


# Graduated PAYE bands. (band_width_annual, rate)
# CITA Sixth Schedule — current as at 2026.
_BANDS: List[Tuple[float, float]] = [
    (  300_000.0, 0.07),   # First ₦300,000
    (  300_000.0, 0.11),   # Next ₦300,000
    (  500_000.0, 0.15),   # Next ₦500,000
    (  500_000.0, 0.19),   # Next ₦500,000
    (1_600_000.0, 0.21),   # Next ₦1,600,000
    (float("inf"), 0.24),  # Above ₦3,200,000
]

# Consolidated Relief Allowance:
#   max(₦200,000, 1% of gross) + 20% of gross
_CRA_FIXED_FLOOR = 200_000.0
_CRA_GROSS_PERCENT = 0.20
_CRA_MIN_PERCENT_FLOOR = 0.01   # 1% of gross floor

# Pension contributions are exempt from PAYE. 7.5% employee minimum under PRA.
_PENSION_EMPLOYEE_RATE = 0.08   # we treat the actual contributed rate
# NHIS 5% of basic — typically optional in SMEs, but available as a relief
_NHIS_DEFAULT_RATE = 0.05


@dataclass
class PAYEResult:
    gross_annual: float
    cra: float
    pension_relief: float
    nhis_relief: float
    chargeable: float
    paye_annual: float
    paye_monthly: float
    effective_rate: float
    band_breakdown: list[tuple[float, float, float]]  # (band_width, rate, paye_in_band)


def compute_paye_annual(
    gross_annual: float, *,
    pension_employee_rate: float = _PENSION_EMPLOYEE_RATE,
    nhis_rate: float = 0.0,
    other_reliefs: float = 0.0,
) -> PAYEResult:
    """Graduated PAYE calculation on an annualised gross."""
    gross_annual = max(0.0, float(gross_annual))
    if gross_annual == 0:
        return PAYEResult(0, 0, 0, 0, 0, 0, 0, 0.0, [])

    pension = round(gross_annual * pension_employee_rate, 2)
    nhis = round(gross_annual * nhis_rate, 2)
    cra = round(max(_CRA_FIXED_FLOOR, gross_annual * _CRA_MIN_PERCENT_FLOOR)
                 + gross_annual * _CRA_GROSS_PERCENT, 2)

    chargeable = max(0.0, gross_annual - cra - pension - nhis - max(0.0, other_reliefs))

    remaining = chargeable
    total = 0.0
    breakdown: list[tuple[float, float, float]] = []
    for band_width, rate in _BANDS:
        if remaining <= 0:
            break
        in_band = min(remaining, band_width)
        band_paye = round(in_band * rate, 2)
        total += band_paye
        breakdown.append((in_band, rate, band_paye))
        remaining -= in_band

    paye_annual = round(total, 2)
    effective = round(paye_annual / gross_annual, 4) if gross_annual else 0.0
    return PAYEResult(
        gross_annual=gross_annual,
        cra=cra,
        pension_relief=pension,
        nhis_relief=nhis,
        chargeable=round(chargeable, 2),
        paye_annual=paye_annual,
        paye_monthly=round(paye_annual / 12, 2),
        effective_rate=effective,
        band_breakdown=breakdown,
    )


def compute_paye_monthly(
    monthly_gross: float, *,
    pension_employee_rate: float = _PENSION_EMPLOYEE_RATE,
    nhis_rate: float = 0.0,
    other_reliefs: float = 0.0,
) -> PAYEResult:
    """Same calc, takes a monthly figure and annualises it."""
    return compute_paye_annual(
        monthly_gross * 12,
        pension_employee_rate=pension_employee_rate,
        nhis_rate=nhis_rate,
        other_reliefs=other_reliefs * 12,
    )
