"""AI agents built into the ERP.

Six analytical agents read the tenant's own books and self-improve from the
company's accumulating data + the team's feedback:

    RECON      — bank reconciliation health
    Tax        — VAT / WHT position and filing nudges
    FP&A       — period-over-period variance, margins, cash
    CFO        — executive financial-health roll-up
    Insight    — concentration risk and idle capital
    Exception  — ledger anomaly detection (learned per-account)

LLM synthesis (Claude Opus 4.8) is opt-in via ANTHROPIC_API_KEY; with no key the
agents run fully deterministically and nothing leaves the box.
"""
from __future__ import annotations

from .base import (  # noqa: F401
    Agent,
    Finding,
    Memory,
    findings_for_run,
    get_agent,
    latest_run,
    learning_summary,
    list_agents,
    record_feedback,
)

# Import each agent module so it self-registers in the AGENTS registry.
from . import recon, tax, fpa, cfo, insight, exception_agent  # noqa: F401,E402

__all__ = [
    "Agent", "Finding", "Memory", "list_agents", "get_agent",
    "latest_run", "findings_for_run", "record_feedback", "learning_summary",
]
