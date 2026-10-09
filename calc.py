"""Salary breakup calculation engine.

Pure functions, no I/O. Replicates the logic of the original workbook and adds
two things it lacked:

* a government **minimum-wage floor** on Basic, and
* an **auto-balance** that keeps the Cost To Company unchanged by adjusting
  HRA and the General Purpose Allowance.

When the floor cannot be honoured without pushing the CTC up, the engine says so
explicitly (``feasible: False``) and reports the CTC that *would* be required.
"""
from __future__ import annotations

import math
from typing import Any

STATUTORY_DEFAULTS: dict[str, float] = {
    "basic_pct": 50.0,
    "hra_pct": 50.0,
    "pf_employee_pct": 12.0,
    "pf_employer_pct": 12.0,
    "pf_cap_amount": 3000.0,
    "esic_employee_pct": 0.75,
    "esic_employer_pct": 3.25,
    "esic_gross_ceiling": 21000.0,
    "gratuity_pct": 4.81,
    "pt_default": 200.0,
    "asset_allowance": 1499.0,
    "pay_frequency": 12.0,
}

PF_ON_BASIC = "12% on Basic"
PF_CAP = "12% Cap"


def _r(x: float) -> float:
    """Round half-up to a whole unit (rupee), like Excel's ROUND()."""
    if x >= 0:
        return float(math.floor(x + 0.5))
    return float(math.ceil(x - 0.5))


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def compute(inputs: dict[str, Any], settings: dict[str, Any] | None = None,
            min_wage: float | None = None) -> dict[str, Any]:
    """Return the full monthly + annual breakup for one candidate.

    ``inputs`` keys
        previous_ctc, increment_pct, proposed_ctc, vp_pct,
        basic_pct, hra_pct, pf_type, asset_allowance, pt, income_tax,
        min_wage_mode ("balance" | "raise_ctc"), label
    """
    s = {**STATUTORY_DEFAULTS, **(settings or {})}
    warnings: list[str] = []

    # ---------------------------------------------------------------- CTC
    previous_ctc = _num(inputs.get("previous_ctc"))
    increment_pct = _num(inputs.get("increment_pct"))
    if inputs.get("proposed_ctc") not in (None, ""):
        proposed_ctc = _num(inputs.get("proposed_ctc"))
    else:
        proposed_ctc = _r(previous_ctc * (1 + increment_pct / 100))

    vp_pct = _num(inputs.get("vp_pct"))
    vp_annual = _r(proposed_ctc * vp_pct / 100)

    months = _num(s.get("pay_frequency"), 12.0) or 12.0
    target_monthly = proposed_ctc / months

    asset = _num(inputs.get("asset_allowance"), _num(s.get("asset_allowance")))
    pt = _num(inputs.get("pt"), _num(s.get("pt_default")))
    income_tax = _num(inputs.get("income_tax"))
    basic_pct = _num(inputs.get("basic_pct"), _num(s.get("basic_pct"), 50.0))
    hra_pct = _num(inputs.get("hra_pct"), _num(s.get("hra_pct"), 50.0))
    pf_type = inputs.get("pf_type") or PF_ON_BASIC

    # ---------------------------------------------------------------- basic + floor
    computed_basic = _r(target_monthly * basic_pct / 100)
    floor = _num(min_wage)
    basic = max(computed_basic, floor)
    min_wage_applied = floor > 0 and basic > computed_basic + 0.5
    if min_wage_applied:
        warnings.append(
            f"Basic raised from {computed_basic:,.0f} to the {floor:,.0f} minimum wage."
        )
    if floor <= 0:
        warnings.append("No minimum wage is defined for this location/category.")

    # ---------------------------------------------------------------- employer costs
    employer_pf_raw = basic * _num(s.get("pf_employer_pct"), 12.0) / 100
    if pf_type == PF_CAP:
        # Workbook convention: "12% Cap" pays a flat capped PF amount (₹3,000).
        employer_pf = _num(s.get("pf_cap_amount"), 3000.0)
    else:
        employer_pf = _r(employer_pf_raw)
    employee_pf = employer_pf
    gratuity = _r(basic * _num(s.get("gratuity_pct"), 4.81) / 100)

    esic_er_pct = _num(s.get("esic_employer_pct"), 3.25)
    esic_ee_pct = _num(s.get("esic_employee_pct"), 0.75)
    esic_ceiling = _num(s.get("esic_gross_ceiling"), 21000.0)

    desired_hra = _r(basic * hra_pct / 100)
    fixed_other = employer_pf + gratuity + asset
    budget = target_monthly - basic - fixed_other  # for HRA + GPA + ESIC(employer)

    hra, gpa, esic_employer, feasible = _balance(
        budget, basic, desired_hra, esic_er_pct, esic_ceiling
    )
    if feasible and abs(hra - desired_hra) > 0.5:
        warnings.append(
            f"HRA reduced from {desired_hra:,.0f} to {hra:,.0f} to keep the CTC unchanged."
        )

    min_ctc_required = None
    if not feasible:
        gpa = 0.0
        hra = 0.0
        cash_probe = basic + desired_hra
        esic_employer = cash_probe * esic_er_pct / 100 if cash_probe < esic_ceiling else 0.0
        required_monthly = basic + desired_hra + employer_pf + gratuity + esic_employer + asset
        min_ctc_required = _r(required_monthly * months)
        warnings.append(
            "Minimum wage cannot be honoured while keeping the CTC unchanged. "
            f"CTC would need to rise to about {min_ctc_required:,.0f}."
        )

    if feasible:
        gpa = target_monthly - basic - hra - employer_pf - gratuity - esic_employer - asset
        if gpa < -0.5:
            hra = max(0.0, hra + gpa)
            gpa = target_monthly - basic - hra - employer_pf - gratuity - esic_employer - asset
        gpa = round(max(0.0, gpa), 2)

    cash = basic + hra + gpa
    esic_employee = _r(cash * esic_ee_pct / 100) if cash < esic_ceiling else 0.0

    employee_deductions = employee_pf + pt + esic_employee + income_tax
    take_home = cash - employee_deductions
    ctc_monthly = cash + employer_pf + gratuity + esic_employer + asset
    ctc_without_vp = _r(ctc_monthly * months)
    ctc_with_vp = _r(ctc_without_vp + vp_annual)

    lines = _build_lines(basic, hra, gpa, employee_pf, pt, esic_employee, income_tax,
                         employer_pf, gratuity, esic_employer, asset, vp_annual, months)

    return {
        "label": inputs.get("label") or "",
        "previous_ctc": previous_ctc,
        "increment_pct": increment_pct,
        "proposed_ctc": proposed_ctc,
        "vp_pct": vp_pct,
        "vp_annual": vp_annual,
        "target_monthly": _r(target_monthly),
        "basic_pct": basic_pct,
        "hra_pct": hra_pct,
        "pf_type": pf_type,
        "min_wage": floor,
        "min_wage_applied": min_wage_applied,
        "min_ctc_required": min_ctc_required,
        "feasible": feasible,
        "basic": basic,
        "computed_basic": computed_basic,
        "hra": hra,
        "desired_hra": desired_hra,
        "gpa": gpa,
        "cash": cash,
        "employer_pf": employer_pf,
        "employee_pf": employee_pf,
        "gratuity": gratuity,
        "esic_employer": esic_employer,
        "esic_employee": esic_employee,
        "professional_tax": pt,
        "income_tax": income_tax,
        "asset_allowance": asset,
        "employee_deductions": employee_deductions,
        "take_home": take_home,
        "ctc_monthly": _r(ctc_monthly),
        "ctc_without_vp": ctc_without_vp,
        "ctc_with_vp": ctc_with_vp,
        "ctc_variance": _r(ctc_without_vp - proposed_ctc),
        "lines": lines,
        "warnings": warnings,
    }


def _balance(budget: float, basic: float, desired_hra: float,
             esic_pct: float, ceiling: float) -> tuple[float, float, float, bool]:
    """Split ``budget`` between HRA, GPA and employer ESIC.

    Preference order: keep the full HRA, absorb the remainder in GPA; if that
    overflows, shrink HRA; if even zero HRA/GPA cannot fit, it is infeasible.
    """
    if budget < -0.5:
        return 0.0, 0.0, 0.0, False

    # Pass 1 – full desired HRA, GPA takes the slack.
    hra, esic = desired_hra, 0.0
    for _ in range(60):
        gpa = budget - hra - esic
        cash = basic + hra + gpa
        new_esic = cash * esic_pct / 100 if cash < ceiling else 0.0
        if abs(new_esic - esic) < 0.005:
            esic = new_esic
            break
        esic = new_esic
    gpa = budget - hra - esic
    if gpa >= -0.5:
        return hra, max(0.0, round(gpa, 2)), _r(esic), True

    # Pass 2 – shrink HRA (GPA → 0) to fit the budget.
    hra, esic = desired_hra, 0.0
    for _ in range(60):
        hra = max(0.0, budget - esic)
        cash = basic + hra
        new_esic = cash * esic_pct / 100 if cash < ceiling else 0.0
        if abs(new_esic - esic) < 0.005:
            esic = new_esic
            break
        esic = new_esic
    hra = max(0.0, budget - esic)
    gpa = max(0.0, budget - hra - esic)
    if hra >= -0.5:
        return _r(hra), round(gpa, 2), _r(esic), True

    return 0.0, 0.0, 0.0, False


def _line(component: str, monthly: float, months: float, kind: str,
          note: str = "") -> dict[str, Any]:
    return {
        "component": component,
        "monthly": _r(monthly),
        "annual": _r(monthly * months),
        "kind": kind,
        "note": note,
    }


def _build_lines(basic, hra, gpa, employee_pf, pt, esic_employee, income_tax,
                 employer_pf, gratuity, esic_employer, asset, vp_annual, months) -> list[dict]:
    lines: list[dict] = []
    lines.append(_line("Basic", basic, months, "earning"))
    lines.append(_line("HRA", hra, months, "earning"))
    lines.append(_line("General Purpose Allowance", gpa, months, "earning", "balancing component"))
    lines.append(_line("PF – Employee", -employee_pf, months, "deduction"))
    lines.append(_line("Professional Tax", -pt, months, "deduction"))
    if esic_employee:
        lines.append(_line("ESIC – Employee", -esic_employee, months, "deduction"))
    if income_tax:
        lines.append(_line("Income Tax", -income_tax, months, "deduction"))
    lines.append(_line("Employer PF", employer_pf, months, "employer"))
    lines.append(_line("Gratuity", gratuity, months, "employer"))
    if esic_employer:
        lines.append(_line("ESIC – Employer", esic_employer, months, "employer"))
    lines.append(_line("Asset / Other Allowance", asset, months, "employer"))
    if vp_annual:
        lines.append(_line("Variable Pay", 0.0, months, "employer", "paid periodically against target"))
    return lines
