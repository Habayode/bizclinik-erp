"""RECON Agent — bank reconciliation health.

Reads each bank statement's reconciliation summary and flags unmatched items,
out-of-balance differences, and statements stuck below the company's own typical
match rate (a learned baseline).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .base import Agent, Finding, Memory, register, upsert_baseline


class ReconAgent(Agent):
    key = "recon"
    label = "RECON Agent"
    icon = "🔗"
    description = ("bank reconciliation — unmatched statement/GL items, "
                   "out-of-balance differences, and match-rate trends")

    def gather(self, session: Session, start: date, end: date) -> dict:
        from ..models import BankAccount, BankStatement, StatementStatus
        from ..services import recon as recon_svc

        stmts = session.execute(
            select(BankStatement).order_by(BankStatement.period_end.desc())
        ).scalars().all()
        # Latest statement per bank account.
        latest: dict[int, BankStatement] = {}
        for s in stmts:
            latest.setdefault(s.bank_account_id, s)

        out = []
        for bank_id, stmt in latest.items():
            if stmt.status == StatementStatus.LOCKED:
                continue
            bank = session.get(BankAccount, bank_id)
            name = (getattr(bank, "name", None) or getattr(bank, "account_name", None)
                    or f"Bank #{bank_id}")
            try:
                summ = recon_svc.reconciliation_summary(session, stmt.id)
            except Exception:
                continue
            out.append({"bank_id": bank_id, "bank_name": name,
                        "statement_id": stmt.id, "summary": summ})
        return {"statements": out}

    def analyze(self, session: Session, context: dict, memory: Memory) -> list[Finding]:
        items = context["statements"]
        findings: list[Finding] = []
        if not items:
            findings.append(Finding(
                kind="no_statements", severity="info",
                title="No bank statements imported to reconcile",
                detail="Import a bank statement under Bank Reconciliation to let "
                       "the RECON Agent tick-and-tie it against the ledger.",
                signature="recon:no_statements"))
            return findings

        for it in items:
            s = it["summary"]
            name = it["bank_name"]
            bid = it["bank_id"]
            diff = abs(s["computed_diff"])
            if diff >= 1.0:
                findings.append(Finding(
                    kind="out_of_balance", severity="critical",
                    title=f"{name}: reconciliation out by ₦{diff:,.2f}",
                    detail=f"Statement movement and matched ledger entries differ "
                           f"by ₦{diff:,.2f}. A missing or mis-posted entry is "
                           f"likely.",
                    metric_value=diff, signature=f"recon:bank:{bid}:out_of_balance"))
            us_n = s["unreconciled_statement_count"]
            if us_n:
                findings.append(Finding(
                    kind="unmatched_statement", severity="warn",
                    title=f"{name}: {us_n} statement line(s) unmatched "
                          f"(₦{s['unreconciled_statement_total']:,.2f})",
                    detail="Bank lines with no matching ledger entry — likely "
                           "bank charges, transfers, or unposted transactions.",
                    metric_value=float(us_n),
                    signature=f"recon:bank:{bid}:unmatched_statement"))
            ug_n = s["unreconciled_gl_count"]
            if ug_n:
                findings.append(Finding(
                    kind="unmatched_gl", severity="warn",
                    title=f"{name}: {ug_n} ledger entry(ies) not on the statement "
                          f"(₦{s['unreconciled_gl_total']:,.2f})",
                    detail="Posted bank-side entries the statement doesn't show — "
                           "uncleared cheques or entries posted to the wrong bank.",
                    metric_value=float(ug_n),
                    signature=f"recon:bank:{bid}:unmatched_gl"))

            # Match-rate vs the company's own history (learned baseline).
            matched = s["matched_count"]
            total = matched + us_n
            if total:
                rate = matched / total
                base = memory.baseline(f"recon:bank:{bid}:match_rate")
                if base and base[2] >= 2 and rate < base[0] - 2 * max(base[1], 0.05):
                    findings.append(Finding(
                        kind="match_rate_drop", severity="warn",
                        title=f"{name}: match rate {rate:.0%} is below its usual "
                              f"{base[0]:.0%}",
                        detail="This reconciliation matched a smaller share of "
                               "lines than this account normally does.",
                        metric_value=rate, baseline_value=base[0],
                        signature=f"recon:bank:{bid}:match_rate_drop"))
        return findings

    def update_baselines(self, session: Session, context: dict, memory: Memory) -> None:
        for it in context["statements"]:
            s = it["summary"]
            bid = it["bank_id"]
            total = s["matched_count"] + s["unreconciled_statement_count"]
            if not total:
                continue
            rate = s["matched_count"] / total
            base = memory.baseline(f"recon:bank:{bid}:match_rate")
            if base is None:
                mean, var, n = rate, 0.0, 1
            else:
                # Online mean/variance (Welford-lite) — sharpens each run.
                pm, pstd, pn = base
                n = pn + 1
                mean = pm + (rate - pm) / n
                var = ((pstd ** 2) * pn + (rate - pm) * (rate - mean)) / n
            upsert_baseline(session, self.key, f"recon:bank:{bid}:match_rate",
                            mean, var ** 0.5, n)


register(ReconAgent())
