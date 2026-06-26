"""AI-agent subsystem: runs, findings, and learned baselines.

These three tables are the agents' MEMORY. The six in-app analytical agents
(RECON, Tax, FP&A, CFO, Insight, Exception) read the tenant's own books, write
their findings here, take user feedback (accept / dismiss / rate), and recompute
per-company baselines from history on every run. That feedback + those baselines
are loaded on the next run, so each agent gets sharper and more relevant as the
company's data and the team's feedback accumulate. Nothing here is GL data —
these are analytical artefacts, so monetary fields are plain Float (they also
hold ratios and z-scores), not the NUMERIC ``Money`` type used for the ledger.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class AgentRun(Base):
    """One execution of an agent over a period. Holds the headline synthesis
    and links to the findings produced."""
    __tablename__ = "agent_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    period_start: Mapped[Optional[date]] = mapped_column(Date)
    period_end: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok | error
    headline: Mapped[Optional[str]] = mapped_column(String(255))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    recommendations: Mapped[Optional[str]] = mapped_column(Text)  # JSON list[str]
    findings_count: Mapped[int] = mapped_column(Integer, default=0)
    # "deterministic", "deterministic (llm error)", or a Claude model id when the
    # operator has enabled LLM synthesis via ANTHROPIC_API_KEY.
    model_used: Mapped[str] = mapped_column(String(64), default="deterministic")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text)

    findings: Mapped[list["AgentFinding"]] = relationship(
        back_populates="run", cascade="all, delete-orphan")


class AgentFinding(Base):
    """A single observation an agent surfaced. `signature` is a stable key for
    the *kind* of issue (same issue across runs shares a signature) so feedback
    can suppress recurring nags the company has dismissed."""
    __tablename__ = "agent_finding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_run.id"), nullable=False, index=True)
    agent_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(12), default="info")  # info|warn|critical
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    metric_value: Mapped[Optional[float]] = mapped_column(Float)
    baseline_value: Mapped[Optional[float]] = mapped_column(Float)
    evidence: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    signature: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|accepted|dismissed|resolved
    rating: Mapped[Optional[int]] = mapped_column(Integer)  # 1..5 usefulness
    feedback_note: Mapped[Optional[str]] = mapped_column(Text)
    feedback_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    run: Mapped[AgentRun] = relationship(back_populates="findings")


class AgentBaseline(Base):
    """A per-company learned metric — the agent recomputes these from the
    tenant's own history each run (mean / stddev / sample size), and the next
    run compares fresh data against them. This is the data-driven half of
    self-improvement; the feedback loop on AgentFinding is the other half."""
    __tablename__ = "agent_baseline"
    __table_args__ = (
        UniqueConstraint("agent_key", "metric_key", name="uq_agent_baseline_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    metric_key: Mapped[str] = mapped_column(String(96), nullable=False)
    mean_value: Mapped[float] = mapped_column(Float, default=0.0)
    stddev_value: Mapped[float] = mapped_column(Float, default=0.0)
    sample_n: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
