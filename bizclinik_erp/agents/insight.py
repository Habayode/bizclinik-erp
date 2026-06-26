"""Insight Agent — opportunities, concentration risk, and idle capital.

Surfaces customer/receivable concentration, the company's heaviest expense
categories, and slow-moving inventory tying up cash. Concentration thresholds
adapt to the company's own history.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .base import Agent, Finding, Memory, register, upsert_baseline


class InsightAgent(Agent):
    key = "insight"
    label = "Insight Agent"
    icon = "💡"
    description = ("opportunities and risks — customer concentration, top expense "
                   "categories, and slow-moving inventory tying up cash")

    def gather(self, session: Session, start: date, end: date) -> dict:
        from ..services import reports
        from ..services.ledger import trial_balance
        from ..models import Product, StockMovement

        ar = reports.ar_aging(session, as_of=end)
        tb = trial_balance(session, as_of=end)

        # Slow-moving stock: on-hand products with no outward movement in 90 days.
        cutoff = end - timedelta(days=90)
        recent_out = set(session.execute(
            select(StockMovement.product_id).where(
                StockMovement.qty_out > 0,
                StockMovement.movement_date >= cutoff)
        ).scalars().all())
        slow = []
        for p in session.execute(
            select(Product).where(Product.qty_on_hand > 0)
        ).scalars():
            if p.id in recent_out:
                continue
            tied = round((p.qty_on_hand or 0.0) * (p.avg_cost or 0.0), 2)
            if tied > 0:
                slow.append({"name": getattr(p, "name", f"Product #{p.id}"),
                             "qty": p.qty_on_hand, "tied": tied})
        slow.sort(key=lambda x: x["tied"], reverse=True)
        return {"ar": ar, "tb": tb, "slow": slow}

    def analyze(self, session: Session, context: dict, memory: Memory) -> list[Finding]:
        ar = context["ar"]
        tb = context["tb"]
        slow = context["slow"]
        findings: list[Finding] = []

        # Customer (receivable) concentration.
        ar_total = sum(r["total"] for r in ar)
        if ar_total > 0 and ar:
            top = max(ar, key=lambda r: r["total"])
            share = top["total"] / ar_total
            if share >= 0.40 and len(ar) >= 2:
                findings.append(Finding(
                    kind="customer_concentration", severity="warn",
                    title=f"{top['customer_name']} is {share:.0%} of receivables",
                    detail="Heavy reliance on one customer concentrates credit and "
                           "revenue risk. Diversify or tighten that account's terms.",
                    metric_value=share, signature="insight:customer_concentration"))

        # Expense concentration from the trial balance.
        exp = [(r["name"], round(r["debit"] - r["credit"], 2)) for r in tb
               if "EXPENSE" in str(r.get("type", "")).upper()]
        exp = [(n, v) for n, v in exp if v > 0]
        exp_total = sum(v for _, v in exp)
        if exp_total > 0 and exp:
            name, val = max(exp, key=lambda x: x[1])
            share = val / exp_total
            if share >= 0.35:
                findings.append(Finding(
                    kind="expense_concentration", severity="info",
                    title=f"{name} is {share:.0%} of expenses (₦{val:,.0f})",
                    detail="The single largest expense line — a candidate for "
                           "negotiation or cost control.",
                    metric_value=share, signature="insight:expense_concentration"))

        # Slow-moving inventory.
        if slow:
            tied_total = sum(s["tied"] for s in slow)
            top3 = ", ".join(s["name"] for s in slow[:3])
            findings.append(Finding(
                kind="slow_inventory", severity="warn" if tied_total > 0 else "info",
                title=f"₦{tied_total:,.0f} tied up in {len(slow)} slow-moving "
                      f"product(s)",
                detail=f"On-hand stock with no sales in 90 days (e.g. {top3}). "
                       f"Consider promotions or write-down review.",
                metric_value=tied_total,
                evidence={"top": slow[:5]},
                signature="insight:slow_inventory"))

        if not findings:
            findings.append(Finding(
                kind="insight_none", severity="info",
                title="No concentration or idle-capital flags",
                detail="No single customer/expense dominates and no stock is "
                       "sitting idle beyond 90 days.",
                signature="insight:none"))
        return findings

    def update_baselines(self, session: Session, context: dict, memory: Memory) -> None:
        ar = context["ar"]
        ar_total = sum(r["total"] for r in ar)
        if ar_total <= 0 or not ar:
            return
        top = max(ar, key=lambda r: r["total"])
        share = top["total"] / ar_total
        base = memory.baseline("insight:top_customer_share")
        if base is None:
            mean, var, n = share, 0.0, 1
        else:
            pm, pstd, pn = base
            n = pn + 1
            mean = pm + (share - pm) / n
            var = ((pstd ** 2) * pn + (share - pm) * (share - mean)) / n
        upsert_baseline(session, self.key, "insight:top_customer_share",
                        mean, var ** 0.5, n)


register(InsightAgent())
