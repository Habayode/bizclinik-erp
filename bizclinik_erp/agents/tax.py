"""Tax Agent — VAT and WHT position with filing nudges.

Reads the period's VAT return and WHT position, compares the output/input VAT
ratio against the company's learned norm, and flags amounts due to (or
reclaimable from) FIRS.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from .base import Agent, Finding, Memory, register, upsert_baseline


class TaxAgent(Agent):
    key = "tax"
    label = "Tax Agent"
    icon = "🧾"
    description = ("Nigerian VAT (7.5%) and withholding tax — amounts payable, "
                   "WHT credits to reclaim, and filing reminders")

    def gather(self, session: Session, start: date, end: date) -> dict:
        from ..services.tax import vat_return, wht_position
        return {
            "vat": vat_return(session, period_start=start, period_end=end),
            "wht": wht_position(session, period_start=start, period_end=end),
        }

    def analyze(self, session: Session, context: dict, memory: Memory) -> list[Finding]:
        vat = context["vat"]
        wht = context["wht"]
        findings: list[Finding] = []

        net = vat["net_payable"]
        if net > 0.5:
            findings.append(Finding(
                kind="vat_payable", severity="warn",
                title=f"VAT payable to FIRS: ₦{net:,.2f}",
                detail=f"Output VAT ₦{vat['output_vat']:,.2f} less input VAT "
                       f"₦{vat['input_vat']:,.2f}. VAT returns are due by the 21st "
                       f"of the following month.",
                metric_value=net, signature="tax:vat:payable"))
        elif net < -0.5:
            findings.append(Finding(
                kind="vat_credit", severity="info",
                title=f"Input VAT exceeds output by ₦{-net:,.2f}",
                detail="A VAT credit carries forward — verify input VAT is on "
                       "valid, vatable purchases.",
                metric_value=net, signature="tax:vat:credit"))

        # Output/input ratio vs the company's learned norm.
        if vat["input_vat"] > 0:
            ratio = vat["output_vat"] / vat["input_vat"]
            base = memory.baseline("tax:vat:out_in_ratio")
            if base and base[2] >= 3 and abs(ratio - base[0]) > 2 * max(base[1], 0.1):
                direction = "above" if ratio > base[0] else "below"
                findings.append(Finding(
                    kind="vat_ratio_anomaly", severity="warn",
                    title=f"VAT output/input ratio {ratio:.2f} is unusually "
                          f"{direction} the norm ({base[0]:.2f})",
                    detail="A swing in the ratio of VAT charged to VAT suffered "
                           "can indicate mis-coded purchases or sales.",
                    metric_value=ratio, baseline_value=base[0],
                    signature="tax:vat:ratio_anomaly"))

        rec = wht["wht_suffered_receivable"]
        if rec > 0.5:
            findings.append(Finding(
                kind="wht_receivable", severity="info",
                title=f"WHT credit to reclaim: ₦{rec:,.2f}",
                detail="Withholding tax suffered on your income is a credit "
                       "against company income tax — keep the WHT credit notes.",
                metric_value=rec, signature="tax:wht:receivable"))
        pay = wht["wht_withheld_payable"]
        if pay > 0.5:
            findings.append(Finding(
                kind="wht_payable", severity="warn",
                title=f"WHT withheld to remit: ₦{pay:,.2f}",
                detail="WHT deducted from suppliers must be remitted to FIRS, "
                       "usually by the 21st of the following month.",
                metric_value=pay, signature="tax:wht:payable"))

        if not findings:
            findings.append(Finding(
                kind="tax_clear", severity="info",
                title="No VAT/WHT due for the period",
                detail="No net VAT payable and no WHT to remit or reclaim were "
                       "found for the selected period.",
                signature="tax:clear"))
        return findings

    def update_baselines(self, session: Session, context: dict, memory: Memory) -> None:
        vat = context["vat"]
        if vat["input_vat"] <= 0:
            return
        ratio = vat["output_vat"] / vat["input_vat"]
        base = memory.baseline("tax:vat:out_in_ratio")
        if base is None:
            mean, var, n = ratio, 0.0, 1
        else:
            pm, pstd, pn = base
            n = pn + 1
            mean = pm + (ratio - pm) / n
            var = ((pstd ** 2) * pn + (ratio - pm) * (ratio - mean)) / n
        upsert_baseline(session, self.key, "tax:vat:out_in_ratio",
                        mean, var ** 0.5, n)


register(TaxAgent())
