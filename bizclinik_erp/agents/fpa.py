"""FP&A Agent — financial planning & analysis.

Compares this period's P&L against the prior equal-length period, tracks gross
margin and the operating-expense ratio against the company's learned norms, and
flags margin compression, expense spikes, losses, and cash outflow.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from .base import Agent, Finding, Memory, register, upsert_baseline


def _pct_change(now: float, prev: float) -> float:
    if abs(prev) < 1e-9:
        return 0.0 if abs(now) < 1e-9 else 1.0
    return (now - prev) / abs(prev)


class FPAAgent(Agent):
    key = "fpa"
    label = "FP&A Agent"
    icon = "📈"
    description = ("financial planning & analysis — period-over-period revenue "
                   "and expense variance, margin trends, and cash movement")

    def gather(self, session: Session, start: date, end: date) -> dict:
        from ..services import reports
        span = (end - start).days
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span)
        return {
            "pnl": reports.profit_and_loss(session, period_start=start, period_end=end),
            "prev": reports.profit_and_loss(session, period_start=prev_start,
                                            period_end=prev_end),
            "cash": reports.cash_flow(session, period_start=start, period_end=end),
        }

    def analyze(self, session: Session, context: dict, memory: Memory) -> list[Finding]:
        p = context["pnl"]
        q = context["prev"]
        cash = context["cash"]
        findings: list[Finding] = []

        rev, prev_rev = p["total_revenue"], q["total_revenue"]
        opex, prev_opex = p["total_operating_expenses"], q["total_operating_expenses"]

        rev_chg = _pct_change(rev, prev_rev)
        if prev_rev > 0 and rev_chg <= -0.15:
            findings.append(Finding(
                kind="revenue_drop", severity="warn",
                title=f"Revenue down {abs(rev_chg):.0%} vs prior period "
                      f"(₦{rev:,.0f} vs ₦{prev_rev:,.0f})",
                detail="Top-line revenue fell materially against the previous "
                       "equal-length period.",
                metric_value=rev, baseline_value=prev_rev,
                signature="fpa:revenue_drop"))
        elif prev_rev > 0 and rev_chg >= 0.25:
            findings.append(Finding(
                kind="revenue_growth", severity="info",
                title=f"Revenue up {rev_chg:.0%} vs prior period",
                detail="Strong top-line growth — confirm it flows through to "
                       "margin and cash.",
                metric_value=rev, baseline_value=prev_rev,
                signature="fpa:revenue_growth"))

        opex_chg = _pct_change(opex, prev_opex)
        if prev_opex > 0 and opex_chg >= 0.20 and opex_chg > rev_chg + 0.10:
            findings.append(Finding(
                kind="opex_spike", severity="warn",
                title=f"Operating expenses up {opex_chg:.0%} — faster than revenue",
                detail=f"Opex rose to ₦{opex:,.0f} (from ₦{prev_opex:,.0f}), "
                       f"outpacing revenue growth. Watch margin.",
                metric_value=opex, baseline_value=prev_opex,
                signature="fpa:opex_spike"))

        # Gross margin vs learned norm.
        if rev > 0:
            margin = p["gross_profit"] / rev
            base = memory.baseline("fpa:gross_margin")
            if base and base[2] >= 3 and margin < base[0] - 2 * max(base[1], 0.03):
                findings.append(Finding(
                    kind="margin_compression", severity="warn",
                    title=f"Gross margin {margin:.0%} below its usual {base[0]:.0%}",
                    detail="Gross margin compressed against the company's own "
                           "historical average — check input costs / pricing.",
                    metric_value=margin, baseline_value=base[0],
                    signature="fpa:margin_compression"))

        if p["net_profit"] < 0:
            findings.append(Finding(
                kind="net_loss", severity="critical",
                title=f"Net loss of ₦{abs(p['net_profit']):,.0f} for the period",
                detail="Expenses exceeded income for the period.",
                metric_value=p["net_profit"], signature="fpa:net_loss"))

        ncc = cash["net_change_in_cash"]
        if ncc < 0:
            findings.append(Finding(
                kind="cash_outflow", severity="info",
                title=f"Net cash outflow of ₦{abs(ncc):,.0f}",
                detail="Cash decreased over the period — reconcile against "
                       "receivables and payables timing.",
                metric_value=ncc, signature="fpa:cash_outflow"))

        if not findings:
            findings.append(Finding(
                kind="fpa_stable", severity="info",
                title="Financials stable vs the prior period",
                detail="No material variance in revenue, expenses, margin, or "
                       "cash for the period.",
                signature="fpa:stable"))
        return findings

    def update_baselines(self, session: Session, context: dict, memory: Memory) -> None:
        p = context["pnl"]
        rev = p["total_revenue"]
        if rev <= 0:
            return
        for key, value in (("fpa:gross_margin", p["gross_profit"] / rev),
                           ("fpa:opex_ratio", p["total_operating_expenses"] / rev)):
            base = memory.baseline(key)
            if base is None:
                mean, var, n = value, 0.0, 1
            else:
                pm, pstd, pn = base
                n = pn + 1
                mean = pm + (value - pm) / n
                var = ((pstd ** 2) * pn + (value - pm) * (value - mean)) / n
            upsert_baseline(session, self.key, key, mean, var ** 0.5, n)


register(FPAAgent())
