"""CFO Agent — executive financial health roll-up.

Looks across the balance sheet, receivables/payables aging, and profitability to
give a CFO-level read: solvency, working capital, overdue exposure, and an
approximate cash runway. This is the most synthesis-oriented agent; when LLM is
enabled it produces a board-ready narrative.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from .base import Agent, Finding, Memory, register


class CFOAgent(Agent):
    key = "cfo"
    label = "CFO Agent"
    icon = "🏛️"
    description = ("executive financial health — solvency, working capital, "
                   "overdue receivables/payables, profitability and cash runway")

    def gather(self, session: Session, start: date, end: date) -> dict:
        from ..services import reports
        return {
            "bs": reports.balance_sheet(session, as_of=end),
            "ar": reports.ar_aging(session, as_of=end),
            "ap": reports.ap_aging(session, as_of=end),
            "pnl": reports.profit_and_loss(session, period_start=start, period_end=end),
            "span_days": max((end - start).days, 1),
        }

    def analyze(self, session: Session, context: dict, memory: Memory) -> list[Finding]:
        bs = context["bs"]
        ar = context["ar"]
        ap = context["ap"]
        pnl = context["pnl"]
        findings: list[Finding] = []

        if not bs.get("balanced", True):
            findings.append(Finding(
                kind="bs_imbalance", severity="critical",
                title=f"Balance sheet out by ₦{abs(bs.get('imbalance', 0)):,.2f}",
                detail="Assets do not equal liabilities plus equity — a posting "
                       "integrity issue to resolve before relying on these figures.",
                metric_value=bs.get("imbalance", 0.0),
                signature="cfo:bs_imbalance"))

        assets = bs["total_assets"]
        liabs = bs["total_liabilities"]
        coverage = assets / liabs if liabs > 0 else None
        if coverage is not None:
            sev = "critical" if coverage < 1 else ("warn" if coverage < 1.3 else "info")
            if coverage < 1.3:
                findings.append(Finding(
                    kind="solvency", severity=sev,
                    title=f"Asset cover {coverage:.2f}× liabilities",
                    detail="Total assets relative to total liabilities is thin — "
                           "watch solvency and gearing.",
                    metric_value=coverage, baseline_value=1.3,
                    signature="cfo:solvency"))

        ar_total = sum(r["total"] for r in ar)
        ap_total = sum(r["total"] for r in ap)
        wc = ar_total - ap_total
        findings.append(Finding(
            kind="working_capital",
            severity="info" if wc >= 0 else "warn",
            title=f"Receivables ₦{ar_total:,.0f} vs payables ₦{ap_total:,.0f} "
                  f"(net ₦{wc:,.0f})",
            detail="Net trade working-capital position. Negative means suppliers "
                   "are owed more than customers owe you.",
            metric_value=wc, signature="cfo:working_capital"))

        ar_overdue = sum(r.get("61-90", 0) + r.get("90+", 0) for r in ar)
        if ar_overdue > 0:
            sev = "warn" if ar_overdue > 0.25 * max(ar_total, 1) else "info"
            findings.append(Finding(
                kind="ar_overdue", severity=sev,
                title=f"₦{ar_overdue:,.0f} of receivables overdue 60+ days",
                detail="Aged debt ties up cash and raises bad-debt risk — "
                       "prioritise collections on the oldest balances.",
                metric_value=ar_overdue, signature="cfo:ar_overdue"))

        ap_overdue = sum(r.get("90+", 0) for r in ap)
        if ap_overdue > 0:
            findings.append(Finding(
                kind="ap_overdue", severity="warn",
                title=f"₦{ap_overdue:,.0f} of payables overdue 90+ days",
                detail="Long-overdue supplier balances risk supply disruption and "
                       "late fees.",
                metric_value=ap_overdue, signature="cfo:ap_overdue"))

        # Rough cash runway: cash on hand ÷ average monthly burn (if loss-making).
        net = pnl["net_profit"]
        months = context["span_days"] / 30.0
        if net < 0 and months > 0:
            burn = -net / months
            cash = _cash_on_hand(bs)
            if burn > 0 and cash is not None:
                runway = cash / burn
                findings.append(Finding(
                    kind="runway",
                    severity="critical" if runway < 3 else ("warn" if runway < 6 else "info"),
                    title=f"Approx. cash runway: {runway:.1f} months",
                    detail=f"At the current burn (₦{burn:,.0f}/month) against cash "
                           f"of ₦{cash:,.0f}. Indicative only.",
                    metric_value=runway, signature="cfo:runway"))
        return findings


def _cash_on_hand(bs: dict) -> float | None:
    """Best-effort cash/bank from the balance-sheet asset lines."""
    total = None
    for a in bs.get("assets", []):
        name = (a.get("name") or "").lower()
        if any(w in name for w in ("cash", "bank")):
            total = (total or 0.0) + a.get("amount", 0.0)
    return total


register(CFOAgent())
