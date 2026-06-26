"""Exception Agent — anomaly detection on the ledger.

For each account it learns the company's own distribution of posting sizes
(mean + stddev, persisted as baselines) and flags entries that are statistical
outliers for THAT account — so "unusual" means unusual for this company, and the
detector sharpens as more history accrues. Also flags suspiciously round large
postings. This is the most self-improving agent: the baselines it writes each
run are exactly what the next run scores against.
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .base import Agent, Finding, Memory, register, upsert_baseline

_WINDOW_DAYS = 180
_MIN_SAMPLE = 8          # need this many postings to trust a distribution
_Z_THRESHOLD = 3.0
_FLOOR = 50_000.0        # ignore small-naira noise


class ExceptionAgent(Agent):
    key = "exception"
    label = "Exception Agent"
    icon = "🚨"
    description = ("ledger anomaly detection — postings that are statistical "
                   "outliers for their account, learned from the company's own "
                   "history, plus suspicious round-number entries")

    def gather(self, session: Session, start: date, end: date) -> dict:
        from ..models import Account, DocStatus, JournalEntry, JournalLine
        cutoff = end - timedelta(days=_WINDOW_DAYS)
        rows = session.execute(
            select(JournalLine, JournalEntry, Account)
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .join(Account, Account.id == JournalLine.account_id)
            .where(JournalEntry.status == DocStatus.POSTED,
                   JournalEntry.entry_date >= cutoff,
                   JournalEntry.entry_date <= end)
            .order_by(JournalEntry.entry_date)
        ).all()
        # Group amounts per account; keep line detail for flagging.
        by_acct: dict[int, dict] = {}
        for jl, je, acct in rows:
            amt = round(abs((jl.debit or 0.0) - (jl.credit or 0.0)), 2)
            if amt <= 0:
                continue
            d = by_acct.setdefault(acct.id, {"name": acct.name, "amounts": [],
                                             "lines": []})
            d["amounts"].append(amt)
            d["lines"].append({"je_id": je.id, "jl_id": jl.id, "amt": amt,
                               "date": je.entry_date.isoformat(),
                               "memo": (je.memo or "")[:120]})
        return {"by_acct": by_acct}

    def analyze(self, session: Session, context: dict, memory: Memory) -> list[Finding]:
        by_acct = context["by_acct"]
        findings: list[Finding] = []
        for acct_id, d in by_acct.items():
            amounts = d["amounts"]
            name = d["name"]
            # Prefer the learned baseline; fall back to this window's distribution.
            base = memory.baseline(f"exception:acct:{acct_id}")
            if base and base[2] >= _MIN_SAMPLE and base[1] > 0:
                mean, std = base[0], base[1]
            elif len(amounts) >= _MIN_SAMPLE:
                mean = statistics.mean(amounts)
                std = statistics.pstdev(amounts)
            else:
                mean = std = None

            for ln in d["lines"]:
                amt = ln["amt"]
                # Statistical outlier for this account.
                if mean is not None and std and std > 0:
                    z = (amt - mean) / std
                    if z >= _Z_THRESHOLD and amt >= max(_FLOOR, mean):
                        findings.append(Finding(
                            kind="outlier_posting", severity="warn",
                            title=f"Unusual ₦{amt:,.0f} to {name} "
                                  f"({z:.1f}σ above its norm)",
                            detail=f"Entry {ln['je_id']} on {ln['date']} is far "
                                   f"larger than this account's typical posting "
                                   f"(~₦{mean:,.0f}). Memo: {ln['memo'] or '—'}",
                            metric_value=amt, baseline_value=mean,
                            evidence={"je_id": ln["je_id"], "z": round(z, 2)},
                            signature=f"exception:line:{ln['je_id']}:{ln['jl_id']}"))
                # Suspiciously round large posting.
                if amt >= 1_000_000 and amt % 1_000_000 == 0:
                    findings.append(Finding(
                        kind="round_number", severity="info",
                        title=f"Round-number ₦{amt:,.0f} posting to {name}",
                        detail=f"Exact round-million entry ({ln['date']}) — often "
                               f"an estimate or accrual worth verifying. "
                               f"Memo: {ln['memo'] or '—'}",
                        metric_value=amt,
                        evidence={"je_id": ln["je_id"]},
                        signature=f"exception:round:{ln['je_id']}:{ln['jl_id']}"))

        if not findings:
            findings.append(Finding(
                kind="exception_none", severity="info",
                title="No ledger anomalies detected",
                detail="No postings stood out as statistical outliers for their "
                       "account in the review window.",
                signature="exception:none"))
        # Cap the noisiest runs.
        return findings[:50]

    def update_baselines(self, session: Session, context: dict, memory: Memory) -> None:
        for acct_id, d in context["by_acct"].items():
            amounts = d["amounts"]
            if len(amounts) < _MIN_SAMPLE:
                continue
            mean = statistics.mean(amounts)
            std = statistics.pstdev(amounts)
            upsert_baseline(session, self.key, f"exception:acct:{acct_id}",
                            mean, std, len(amounts))


register(ExceptionAgent())
