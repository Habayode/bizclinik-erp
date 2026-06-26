"""Agent framework: the shared run loop and the self-improvement machinery.

Every agent is a small class with two jobs it must implement —

    gather(session, start, end) -> context      # pull the company's own data
    analyze(session, context, memory) -> [Finding]   # turn it into findings

— and the base class handles everything else: loading the agent's memory
(learned baselines + the team's past feedback), suppressing findings the company
has previously dismissed, optional Claude synthesis (only when the operator has
set ANTHROPIC_API_KEY — otherwise a deterministic narrative, and no data leaves
the box), persisting the run + findings, and recomputing baselines from the
latest data. That last step plus the feedback loop are what make the agents
self-improving: each run learns from the company's accumulating data and the
team's accept/dismiss decisions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import authz
from ..models.agents import AgentBaseline, AgentFinding, AgentRun

_SEV_ORDER = {"critical": 0, "warn": 1, "info": 2}


@dataclass
class Finding:
    kind: str
    severity: str  # info | warn | critical
    title: str
    detail: str
    signature: str
    metric_value: Optional[float] = None
    baseline_value: Optional[float] = None
    evidence: dict = field(default_factory=dict)


class Memory:
    """A snapshot of what the agent has learned, loaded once per run."""

    def __init__(self, baselines: dict, dismissed: set, accepted: list):
        self.baselines = baselines          # metric_key -> (mean, stddev, n)
        self.dismissed = dismissed          # set of dismissed signatures
        self.accepted = accepted            # list of {title, detail, note}

    def baseline(self, metric_key: str):
        """(mean, stddev, sample_n) for a learned metric, or None."""
        return self.baselines.get(metric_key)


def load_memory(session: Session, agent_key: str) -> Memory:
    baselines = {
        b.metric_key: (b.mean_value, b.stddev_value, b.sample_n)
        for b in session.execute(
            select(AgentBaseline).where(AgentBaseline.agent_key == agent_key)
        ).scalars()
    }
    # Latest feedback status per signature (most recent finding wins).
    rows = session.execute(
        select(AgentFinding)
        .where(AgentFinding.agent_key == agent_key)
        .order_by(AgentFinding.created_at.desc(), AgentFinding.id.desc())
    ).scalars().all()
    latest: dict[str, str] = {}
    accepted: list = []
    for f in rows:
        if f.signature not in latest:
            latest[f.signature] = f.status
        if f.status == "accepted" and len(accepted) < 8:
            accepted.append({"title": f.title, "detail": f.detail or "",
                             "note": f.feedback_note or ""})
    dismissed = {sig for sig, st in latest.items() if st == "dismissed"}
    return Memory(baselines, dismissed, accepted)


def upsert_baseline(session: Session, agent_key: str, metric_key: str,
                    mean: float, stddev: float, n: int) -> None:
    row = session.execute(
        select(AgentBaseline).where(
            AgentBaseline.agent_key == agent_key,
            AgentBaseline.metric_key == metric_key)
    ).scalar_one_or_none()
    if row is None:
        row = AgentBaseline(agent_key=agent_key, metric_key=metric_key)
        session.add(row)
    row.mean_value = float(mean)
    row.stddev_value = float(stddev)
    row.sample_n = int(n)
    row.updated_at = datetime.utcnow()


def company_name(session: Session) -> str:
    try:
        from ..models import Company
        c = session.execute(select(Company)).scalars().first()
        if c and getattr(c, "name", None):
            return c.name
    except Exception:
        pass
    return "the company"


class Agent:
    """Base class. Subclasses set key/label/icon/description and implement
    gather() + analyze(); they may override update_baselines()."""

    key: str = ""
    label: str = ""
    icon: str = "🤖"
    description: str = ""

    # ---- to implement -----------------------------------------------------
    def gather(self, session: Session, start: date, end: date) -> dict:
        raise NotImplementedError

    def analyze(self, session: Session, context: dict, memory: Memory) -> list[Finding]:
        raise NotImplementedError

    def update_baselines(self, session: Session, context: dict, memory: Memory) -> None:
        """Recompute and persist learned baselines from the latest data.
        Default: nothing to learn. Agents that learn override this."""
        return None

    # ---- the shared run loop ---------------------------------------------
    def run(self, session: Session, *, period_start: Optional[date] = None,
            period_end: Optional[date] = None, use_llm: bool = True) -> AgentRun:
        authz.require_perm("agents.run")
        start, end = self._period(period_start, period_end)

        context = self.gather(session, start, end)
        memory = load_memory(session, self.key)

        findings = [f for f in self.analyze(session, context, memory)
                    if f.signature not in memory.dismissed]
        findings.sort(key=lambda f: _SEV_ORDER.get(f.severity, 3))

        model_used = "deterministic"
        in_tok = out_tok = 0
        llm_out: Optional[dict] = None
        if use_llm and findings:
            from . import llm
            res = llm.synthesize(
                agent_label=self.label, agent_focus=self.description,
                company=company_name(session),
                findings=[_finding_brief(f) for f in findings],
                accepted_examples=memory.accepted,
                baselines=_baselines_brief(memory),
            )
            if res and not res.get("error"):
                llm_out = res
                model_used = res.get("model") or "claude"
                in_tok = int(res.get("input_tokens") or 0)
                out_tok = int(res.get("output_tokens") or 0)
                order = res.get("priority_signatures") or []
                if order:
                    rank = {sig: i for i, sig in enumerate(order)}
                    findings.sort(key=lambda f: rank.get(f.signature, 10_000))
            elif res and res.get("error"):
                model_used = "deterministic (llm error)"

        headline = (llm_out or {}).get("headline") or self._headline(findings)
        summary = (llm_out or {}).get("narrative") or self._summary(findings)
        recs = (llm_out or {}).get("recommendations") or self._recommendations(findings)

        run = AgentRun(
            agent_key=self.key, run_at=datetime.utcnow(),
            period_start=start, period_end=end, status="ok",
            headline=(headline or "")[:255], summary=summary,
            recommendations=json.dumps(recs or []),
            findings_count=len(findings), model_used=model_used,
            input_tokens=in_tok, output_tokens=out_tok,
        )
        session.add(run)
        session.flush()
        for f in findings:
            session.add(AgentFinding(
                run_id=run.id, agent_key=self.key, kind=f.kind,
                severity=f.severity, title=f.title[:255], detail=f.detail,
                metric_value=f.metric_value, baseline_value=f.baseline_value,
                evidence=json.dumps(f.evidence) if f.evidence else None,
                signature=f.signature[:160], status="open",
                created_at=datetime.utcnow(),
            ))
        # Learn from this run's data for next time.
        self.update_baselines(session, context, memory)
        session.flush()
        return run

    # ---- deterministic fallbacks (used when LLM is off) -------------------
    def _headline(self, findings: list[Finding]) -> str:
        if not findings:
            return f"No issues found by the {self.label}."
        crit = sum(1 for f in findings if f.severity == "critical")
        warn = sum(1 for f in findings if f.severity == "warn")
        bits = []
        if crit:
            bits.append(f"{crit} critical")
        if warn:
            bits.append(f"{warn} to review")
        info = len(findings) - crit - warn
        if info:
            bits.append(f"{info} note{'s' if info != 1 else ''}")
        return f"{self.label}: " + ", ".join(bits) + "."

    def _summary(self, findings: list[Finding]) -> str:
        if not findings:
            return "Nothing notable in this period."
        return "\n".join(f"- [{f.severity.upper()}] {f.title}" for f in findings[:12])

    def _recommendations(self, findings: list[Finding]) -> list[str]:
        return [f.title for f in findings if f.severity in ("critical", "warn")][:5]

    # ---- helpers ----------------------------------------------------------
    def _period(self, start: Optional[date], end: Optional[date]) -> tuple[date, date]:
        if end is None:
            end = date.today()
        if start is None:
            start = date(end.year, 1, 1)
        return start, end


def _finding_brief(f: Finding) -> dict:
    return {"signature": f.signature, "severity": f.severity, "kind": f.kind,
            "title": f.title, "detail": f.detail,
            "metric": f.metric_value, "baseline": f.baseline_value}


def _baselines_brief(memory: Memory) -> dict:
    return {k: {"mean": round(v[0], 4), "stddev": round(v[1], 4), "n": v[2]}
            for k, v in list(memory.baselines.items())[:40]}


# ---- registry --------------------------------------------------------------

AGENTS: dict[str, Agent] = {}


def register(agent: Agent) -> Agent:
    AGENTS[agent.key] = agent
    return agent


def get_agent(key: str) -> Agent:
    if key not in AGENTS:
        raise KeyError(f"Unknown agent: {key}")
    return AGENTS[key]


def list_agents() -> list[Agent]:
    return list(AGENTS.values())


# ---- feedback + retrieval (used by the UI / API) ---------------------------

def latest_run(session: Session, agent_key: str) -> Optional[AgentRun]:
    return session.execute(
        select(AgentRun).where(AgentRun.agent_key == agent_key)
        .order_by(AgentRun.run_at.desc(), AgentRun.id.desc())
    ).scalars().first()


def findings_for_run(session: Session, run_id: int) -> list[AgentFinding]:
    return session.execute(
        select(AgentFinding).where(AgentFinding.run_id == run_id)
        .order_by(AgentFinding.id)
    ).scalars().all()


def record_feedback(session: Session, finding_id: int, *, status: str,
                    rating: Optional[int] = None,
                    note: Optional[str] = None) -> AgentFinding:
    """Accept / dismiss / resolve a finding. This is half the learning loop:
    a dismissed signature is suppressed on future runs."""
    authz.require_perm("agents.run")
    if status not in ("open", "accepted", "dismissed", "resolved"):
        raise ValueError(f"Invalid feedback status: {status}")
    f = session.get(AgentFinding, finding_id)
    if f is None:
        raise ValueError(f"Finding {finding_id} not found.")
    f.status = status
    if rating is not None:
        f.rating = max(1, min(5, int(rating)))
    if note is not None:
        f.feedback_note = note[:2000]
    f.feedback_at = datetime.utcnow()
    session.flush()
    return f


def learning_summary(session: Session, agent_key: str) -> dict:
    """What the agent has learned so far — surfaced in the UI so the team can
    see it adapting."""
    baselines = session.execute(
        select(AgentBaseline).where(AgentBaseline.agent_key == agent_key)
        .order_by(AgentBaseline.metric_key)
    ).scalars().all()
    fb = session.execute(
        select(AgentFinding).where(AgentFinding.agent_key == agent_key)
    ).scalars().all()
    accepted = sum(1 for f in fb if f.status == "accepted")
    dismissed = sum(1 for f in fb if f.status == "dismissed")
    return {
        "baselines": [
            {"metric": b.metric_key, "mean": round(b.mean_value, 4),
             "stddev": round(b.stddev_value, 4), "n": b.sample_n}
            for b in baselines
        ],
        "accepted": accepted,
        "dismissed": dismissed,
        "total_feedback": accepted + dismissed,
    }
