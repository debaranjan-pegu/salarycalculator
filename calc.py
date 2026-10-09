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
    min_ctc_with_hra = None
    if not feasible:
        gpa = 0.0
        hra = 0.0
        # The hard floor: the minimum wage plus the employer's statutory costs,
        # with HRA and the allowance squeezed to nothing. Nothing at all can be
        # paid below this, so it is the smallest CTC that can carry the wage.
        esic_floor = basic * esic_er_pct / 100 if basic < esic_ceiling else 0.0
        min_ctc_required = _r((basic + employer_pf + gratuity + esic_floor + asset) * months)
        # The same wage while still paying HRA at the usual rate, for comparison.
        cash_full = basic + desired_hra
        esic_full = cash_full * esic_er_pct / 100 if cash_full < esic_ceiling else 0.0
        min_ctc_with_hra = _r(
            (basic + desired_hra + employer_pf + gratuity + esic_full + asset) * months)

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

    if not feasible and not inputs.get("_no_raise"):
        return _raise_to_minimum(inputs, settings, min_wage, min_ctc_required,
                                 min_ctc_with_hra, proposed_ctc)

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
        "min_ctc_with_hra": min_ctc_with_hra,
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


def _raise_to_minimum(inputs: dict, settings: dict | None, min_wage: float,
                      min_ctc_required: float, min_ctc_with_hra: float,
                      requested_ctc: float) -> dict:
    """Recalculate at the CTC the minimum wage requires.

    Paying less than that is not legal, so the useful answer is the compliant
    package: every figure then agrees — the card, the table and the export all
    show the same CTC — while the caller can still see what was asked for.
    """
    target = float(min_ctc_required or 0)
    result = compute({**inputs, "proposed_ctc": target, "_no_raise": True}, settings, min_wage)
    for _ in range(8):
        if result.get("feasible"):
            break
        target = _r(target * 1.01) + 1
        result = compute({**inputs, "proposed_ctc": target, "_no_raise": True}, settings, min_wage)

    result["requested_ctc"] = _r(requested_ctc)
    result["raised_to_minimum"] = True
    result["min_ctc_required"] = min_ctc_required
    result["min_ctc_with_hra"] = min_ctc_with_hra
    notes = [
        f"The minimum wage of {_r(min_wage):,.0f} cannot be paid on a CTC of "
        f"{_r(requested_ctc):,.0f}. Raised it to {result['proposed_ctc']:,.0f} — the lowest "
        "CTC that can carry it, with HRA and the allowance squeezed to fit."
    ]
    if min_ctc_with_hra and min_ctc_with_hra > result["proposed_ctc"] + 1:
        notes.append(
            f"To also pay HRA at the usual {result.get('hra_pct', 50):g}% of Basic, "
            f"the CTC would need to be about {min_ctc_with_hra:,.0f}."
        )
    result["warnings"] = notes + [
        w for w in result.get("warnings", [])
        if "cannot be honoured" not in w and "HRA reduced" not in w]
    return result


def solve_ctc_for_take_home(inputs: dict, settings: dict | None, min_wage: float | None,
                            target_monthly: float) -> dict:
    """Reverse solve: the smallest *payable* annual CTC that reaches a monthly take-home.

    A minimum wage pins the Basic, so a CTC below what that costs is not really
    payable — the search therefore stays inside the feasible region, and if the
    target is lower than that floor it says so rather than inventing a CTC.
    """
    base = dict(inputs)
    base.pop("proposed_ctc", None)
    target = float(target_monthly or 0)

    probe = compute({**base, "proposed_ctc": 0, "_no_raise": True}, settings, min_wage)
    floor_ctc = 0 if probe.get("feasible") else int(round(probe.get("min_ctc_required") or 0))
    floor_result = compute({**base, "proposed_ctc": floor_ctc, "_no_raise": True}, settings, min_wage)
    floor_take_home = floor_result.get("take_home") or 0

    def result_at(ctc):
        return compute({**base, "proposed_ctc": ctc, "_no_raise": True}, settings, min_wage)

    def pays(ctc):
        result = result_at(ctc)
        return bool(result.get("feasible")) and (result.get("take_home") or 0) >= target

    if target <= 0:
        return {"ctc": floor_ctc, "achieved": False, "result": floor_result,
                "floor_ctc": floor_ctc, "floor_take_home": floor_take_home, "below_minimum": False}

    if target <= floor_take_home:
        return {"ctc": floor_ctc, "achieved": True, "result": floor_result,
                "floor_ctc": floor_ctc, "floor_take_home": floor_take_home, "below_minimum": True}

    hi = max(12.0 * target * 4.0, 200_000.0)
    for _ in range(25):
        if pays(hi):
            break
        hi *= 2.0

    lo = float(floor_ctc)
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if pays(mid):
            hi = mid
        else:
            lo = mid

    guess = int(round(hi))
    best = None
    for candidate in range(max(floor_ctc, guess - 300), guess + 301):
        if pays(candidate):
            best = (candidate, result_at(candidate))
            break
    if best is None:
        best = (guess, result_at(guess))

    ctc, result = best
    return {"ctc": ctc, "achieved": (result.get("take_home") or 0) >= target - 0.5,
            "result": result, "floor_ctc": floor_ctc, "floor_take_home": floor_take_home,
            "below_minimum": False}
