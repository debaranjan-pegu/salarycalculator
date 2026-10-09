"""Builds the formatted .xlsx salary-breakup report.

Mirrors the layout of the original workbook: a Current CTC column beside the
Proposed CTC column, grouped into Cash Benefit / Deduction / Variable Pay /
Employer Contributions / Cost To Company, with a highlighted Take Home row.
"""
from __future__ import annotations

from typing import Any

import xlsx

INK = "1E1B4B"        # indigo-950
HEAD = "312E81"       # indigo-900
SECTION = "E0E7FF"    # indigo-100
SECTION_TX = "312E81"
TOTAL_BG = "EEF2FF"
CTC_BG = "DBEAFE"
TAKE_BG = "FDE68A"
WARN_BG = "FEF9C3"
INFO_LB = "F1F5F9"
MUTED = "64748B"


def build(location: dict, current: dict, proposed: dict,
          min_wage: float, prepared_on: str) -> bytes:
    wb = xlsx.Workbook("Salary Breakup")
    s = wb.styles
    symbol = proposed.get("currency_symbol") or "₹"

    st = {
        "title": s.xf(bold=True, size=16, color="FFFFFF", fill=INK, align="center"),
        "subtitle": s.xf(size=10, color=MUTED, align="center"),
        "section": s.xf(bold=True, size=11, color=SECTION_TX, fill=SECTION, border=True),
        "label": s.xf(bold=True, fill=INFO_LB, border=True),
        "value": s.xf(border=True),
        "thead": s.xf(bold=True, size=11, color="FFFFFF", fill=HEAD, border=True, align="center"),
        "thsub": s.xf(bold=True, size=10, color=SECTION_TX, fill=SECTION, border=True, align="center"),
        "blank": s.xf(border=True),
        "num": s.xf(border=True, num=True, align="right"),
        "total": s.xf(bold=True, fill=TOTAL_BG, border=True, num=True, align="right"),
        "total_l": s.xf(bold=True, fill=TOTAL_BG, border=True),
        "ctc": s.xf(bold=True, fill=CTC_BG, border=True, num=True, align="right"),
        "ctc_l": s.xf(bold=True, fill=CTC_BG, border=True),
        "take": s.xf(bold=True, size=12, fill=TAKE_BG, border=True, num=True, align="right"),
        "take_l": s.xf(bold=True, size=12, fill=TAKE_BG, border=True),
        "note": s.xf(size=10, color=MUTED, wrap=True, valign="top"),
        "note_warn": s.xf(size=10, color="92400E", fill=WARN_BG, wrap=True, valign="top"),
    }

    for col, w in ((1, 44), (2, 14), (3, 15), (4, 14), (5, 15)):
        wb.width(col, w)

    r = 1
    wb.height(r, 26)
    wb.cell(r, 1, "SALARY BREAKUP", st["title"])
    wb.merge(r, 1, r, 5)
    r += 1
    wb.cell(r, 1, f"Prepared {prepared_on}  ·  all amounts in {symbol}", st["subtitle"])
    wb.merge(r, 1, r, 5)
    r += 2

    # ---- candidate details -------------------------------------------------
    wb.cell(r, 1, "CANDIDATE DETAILS", st["section"])
    wb.merge(r, 1, r, 5)
    r += 1
    details = [
        ("Candidate name", location.get("name") or "—"),
        ("Company", location.get("company") or "—"),
        ("Experience", location.get("experience") or "—"),
        ("Age", location.get("age") or "—"),
        ("Designation", location.get("designation") or "—"),
        ("Level", location.get("level") or "—"),
        ("Band", location.get("band") or "—"),
        ("Insurance cover", (f"{symbol}{location['insurance']:,.0f}"
                             if location.get("insurance") else "—")),
        ("Country", location.get("country") or "—"),
        ("State / Territory", location.get("state") or "—"),
        ("City", location.get("city") or "—"),
        ("Wage category", location.get("category") or "—"),
        ("Minimum wage applicable",
         f"{symbol}{min_wage:,.0f} per month" if min_wage else "Not defined for this location"),
        ("Previous CTC (annual)", f"{symbol}{proposed.get('previous_ctc', 0):,.0f}"),
        ("Proposed CTC (annual)", f"{symbol}{proposed.get('proposed_ctc', 0):,.0f}"),
        ("Increment", f"{proposed.get('increment_pct', 0):g}%"),
    ]
    for label, value in details:
        wb.cell(r, 1, label, st["label"])
        wb.cell(r, 2, value, st["value"])
        wb.merge(r, 2, r, 5)
        r += 1
    r += 1

    # ---- table header ------------------------------------------------------
    hdr = r
    wb.height(hdr, 20)
    wb.cell(hdr, 1, "Particular", st["thead"])
    wb.cell(hdr, 2, "Current CTC", st["thead"])
    wb.merge(hdr, 2, hdr, 3)
    wb.cell(hdr, 4, "Proposed CTC", st["thead"])
    wb.merge(hdr, 4, hdr, 5)
    r += 1
    wb.cell(r, 1, "", st["thsub"])
    for col, text in ((2, "Per Month"), (3, "Per Annum"), (4, "Per Month"), (5, "Per Annum")):
        wb.cell(r, col, text, st["thsub"])
    r += 1

    def nz(x):
        return None if x is None or abs(float(x)) < 0.5 else round(float(x))

    def row(label, cm, ca, pm, pa, kind="num", label_style=None):
        nonlocal r
        ls = label_style or ("total_l" if kind in ("total", "ctc", "take") else "value")
        wb.cell(r, 1, label, st[ls])
        wb.cell(r, 2, nz(cm), st[kind])
        wb.cell(r, 3, nz(ca), st[kind])
        wb.cell(r, 4, nz(pm), st[kind])
        wb.cell(r, 5, nz(pa), st[kind])
        r += 1

    def section(title):
        nonlocal r
        wb.cell(r, 1, title, st["section"])
        wb.merge(r, 1, r, 5)
        r += 1

    section("CASH BENEFIT")
    row("Basic", current["basic"], current["basic"] * 12, proposed["basic"], proposed["basic"] * 12)
    row("HRA", current["hra"], current["hra"] * 12, proposed["hra"], proposed["hra"] * 12)
    row("General Purpose Allowance", current["gpa"], current["gpa"] * 12, proposed["gpa"], proposed["gpa"] * 12)
    row("Total Cash Benefits", current["cash"], current["cash"] * 12, proposed["cash"], proposed["cash"] * 12, "total")

    section("DEDUCTION")
    row("Deduction – PF Employee Contribution", current["employee_pf"], current["employee_pf"] * 12,
        proposed["employee_pf"], proposed["employee_pf"] * 12)
    row("PT (Professional Tax)", current["professional_tax"], current["professional_tax"] * 12,
        proposed["professional_tax"], proposed["professional_tax"] * 12)
    row("ESIC – Employee", current["esic_employee"], current["esic_employee"] * 12,
        proposed["esic_employee"], proposed["esic_employee"] * 12)
    row("Income Tax", current["income_tax"], current["income_tax"] * 12,
        proposed["income_tax"], proposed["income_tax"] * 12)
    row("Total Deduction", current["employee_deductions"], current["employee_deductions"] * 12,
        proposed["employee_deductions"], proposed["employee_deductions"] * 12, "total")

    section("VARIABLE PAY")
    wb.cell(r, 1, "% Variable Pay (paid quarterly basis the target)", st["value"])
    wb.cell(r, 2, current.get("vp_pct") or None, st["num"])
    wb.cell(r, 3, None, st["num"])
    wb.cell(r, 4, proposed.get("vp_pct") or None, st["num"])
    wb.cell(r, 5, None, st["num"])
    r += 1
    row("Variable Pay", 0, current["vp_annual"], 0, proposed["vp_annual"])

    section("EMPLOYER CONTRIBUTIONS")
    row("Gratuity", current["gratuity"], current["gratuity"] * 12, proposed["gratuity"], proposed["gratuity"] * 12)
    row("Employer PF", current["employer_pf"], current["employer_pf"] * 12, proposed["employer_pf"], proposed["employer_pf"] * 12)
    row("ESIC – Employer", current["esic_employer"], current["esic_employer"] * 12,
        proposed["esic_employer"], proposed["esic_employer"] * 12)
    row("Asset / Other Allowance", current["asset_allowance"], current["asset_allowance"] * 12,
        proposed["asset_allowance"], proposed["asset_allowance"] * 12)

    section("COST TO COMPANY")
    row("Cost To Company (Without Variable)", current["ctc_without_vp"] / 12, current["ctc_without_vp"],
        proposed["ctc_without_vp"] / 12, proposed["ctc_without_vp"], "ctc")
    row("Cost to Company (Including Variable Pay)", current["ctc_with_vp"] / 12, current["ctc_with_vp"],
        proposed["ctc_with_vp"] / 12, proposed["ctc_with_vp"], "ctc")
    row("Take Home", current["take_home"], current["take_home"] * 12,
        proposed["take_home"], proposed["take_home"] * 12, "take")
    r += 1

    # ---- notes -------------------------------------------------------------
    if min_wage and not proposed.get("feasible"):
        note = (f"Minimum wage of {symbol}{min_wage:,.0f} cannot be honoured while keeping the CTC "
                f"unchanged. The CTC would need to rise to about {symbol}{proposed.get('min_ctc_required', 0):,.0f} "
                "per annum to pay the statutory minimum.")
        style = "note_warn"
    elif proposed.get("min_wage_applied"):
        note = (f"Basic was raised to the statutory minimum wage of {symbol}{min_wage:,.0f}; "
                "HRA and the General Purpose Allowance were adjusted so the Cost To Company is unchanged.")
        style = "note_warn"
    elif min_wage:
        note = (f"Basic is above the applicable minimum wage of {symbol}{min_wage:,.0f} per month; "
                "no adjustment was required.")
        style = "note"
    else:
        note = "No statutory minimum wage is defined for this location and category."
        style = "note"
    wb.cell(r, 1, note, st[style])
    wb.merge(r, 1, r, 5)
    wb.height(r, 42)
    r += 1

    if proposed.get("pf_type"):
        wb.cell(r, 1, f"PF scheme: {proposed['pf_type']}.  Employer PF {proposed.get('employer_pf', 0):,.0f} / month.",
                st["note"])
        wb.merge(r, 1, r, 5)

    wb.freeze(0)
    return wb.to_bytes()
