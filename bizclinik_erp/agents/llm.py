"""Claude synthesis layer for the agents — strictly opt-in.

The deterministic analysers always run and always produce findings; this layer
only adds an executive narrative, prioritisation, and recommendations on top.
It is enabled ONLY when the operator sets ANTHROPIC_API_KEY in the environment.
With no key, `synthesize()` returns None and the agents fall back to a
deterministic narrative — and, importantly, no company data is ever sent off the
box. When the key is set, the company's own findings (not raw ledgers) are sent
to Claude for synthesis.

Uses the official Anthropic SDK with Claude Opus 4.8 + adaptive thinking, and a
structured-output schema so the response is reliably parseable.
"""
from __future__ import annotations

import json
import os
from typing import Optional

MODEL = "claude-opus-4-8"

_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "narrative": {"type": "string"},
        "recommendations": {"type": "array", "items": {"type": "string"}},
        "priority_signatures": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "narrative", "recommendations", "priority_signatures"],
    "additionalProperties": False,
}


def available() -> bool:
    """True when LLM synthesis is enabled (operator set ANTHROPIC_API_KEY)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def synthesize(*, agent_label: str, agent_focus: str, company: str,
               findings: list, accepted_examples: list,
               baselines: dict) -> Optional[dict]:
    """Return {headline, narrative, recommendations, priority_signatures,
    model, input_tokens, output_tokens}, or {"error": ...} on failure, or None
    when LLM synthesis is disabled."""
    if not available():
        return None
    try:
        import anthropic

        client = anthropic.Anthropic()
        system = (
            f"You are the {agent_label} for {company}, a Nigerian SME using the "
            f"Trakit365 accounting ERP. Focus: {agent_focus}\n\n"
            "You are given findings produced deterministically from the company's "
            "OWN books for this period. Do not invent numbers, accounts, or facts "
            "beyond what the findings state — cite the figures you are given. "
            "Produce a crisp executive synthesis a Nigerian SME owner/accountant "
            "can act on, in plain language (₦ for naira).\n\n"
            "The company has previously marked some findings USEFUL (the examples). "
            "Weight similar signal higher and order `priority_signatures` so the "
            "most decision-relevant findings come first (use the exact `signature` "
            "strings given). Keep the narrative under ~180 words. Recommendations "
            "must be concrete next actions (max 5)."
        )
        payload = {
            "findings": findings,
            "previously_useful_examples": accepted_examples,
            "learned_baselines": baselines,
        }
        resp = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        data = json.loads(text)
        return {
            "headline": data.get("headline", ""),
            "narrative": data.get("narrative", ""),
            "recommendations": data.get("recommendations", []),
            "priority_signatures": data.get("priority_signatures", []),
            "model": resp.model,
            "input_tokens": getattr(resp.usage, "input_tokens", 0),
            "output_tokens": getattr(resp.usage, "output_tokens", 0),
        }
    except Exception as exc:  # never let synthesis break a run
        return {"error": str(exc)[:500]}
