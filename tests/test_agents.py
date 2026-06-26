"""AI-agent subsystem: registry, runs on real data, the self-improvement loop
(learned baselines + dismiss-to-suppress feedback), and anomaly detection.

These run fully deterministically — no ANTHROPIC_API_KEY, so llm.available() is
False and nothing is sent off-box; model_used must be 'deterministic'."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select


def _accounts(s):
    # Postable leaf accounts from the seeded COA: 6000 expense, 4100 sales
    # revenue, 1000 cash. (4000 'Income' is a header the P&L excludes.)
    from bizclinik_erp.models import Account

    def by_code(c):
        return s.execute(select(Account).where(Account.code == c)).scalar_one()

    return by_code("6000"), by_code("4100"), by_code("1000")


def _seed_activity(s):
    """A little revenue + expense so the P&L / TB are non-empty."""
    from bizclinik_erp.services.ledger import JELine, post_journal
    exp, inc, asset = _accounts(s)
    today = date.today()
    post_journal(s, today - timedelta(days=10), "Revenue",
                 [JELine(account_id=asset.id, debit=500_000),
                  JELine(account_id=inc.id, credit=500_000)], source_kind="TEST")
    post_journal(s, today - timedelta(days=5), "Expense",
                 [JELine(account_id=exp.id, debit=200_000),
                  JELine(account_id=asset.id, credit=200_000)], source_kind="TEST")
    s.flush()
    return exp, inc, asset


def test_all_six_agents_registered(fresh_db):
    from bizclinik_erp import agents
    keys = {a.key for a in agents.list_agents()}
    assert keys == {"recon", "tax", "fpa", "cfo", "insight", "exception"}


def test_every_agent_runs_deterministically(fresh_db):
    from bizclinik_erp import agents
    from bizclinik_erp.agents import llm
    from bizclinik_erp.db import get_session

    assert llm.available() is False  # no API key in the test environment
    with get_session() as s:
        _seed_activity(s)
    for agent in agents.list_agents():
        with get_session() as s:
            run = agent.run(s, use_llm=True)  # use_llm True but no key -> deterministic
            assert run.id is not None
            assert run.status == "ok"
            assert run.model_used == "deterministic"
            assert run.findings_count >= 1
            assert run.headline


def test_dismiss_feedback_suppresses_signature(fresh_db):
    """Dismissing a finding stops the agent resurfacing that signature."""
    from bizclinik_erp import agents
    from bizclinik_erp.db import get_session

    # RECON on an empty book yields the structural 'recon:no_statements' note.
    with get_session() as s:
        run = agents.get_agent("recon").run(s, use_llm=False)
        findings = agents.findings_for_run(s, run.id)
        sigs = {f.signature for f in findings}
        assert "recon:no_statements" in sigs
        target = next(f for f in findings if f.signature == "recon:no_statements")
        agents.record_feedback(s, target.id, status="dismissed")

    with get_session() as s:
        run2 = agents.get_agent("recon").run(s, use_llm=False)
        sigs2 = {f.signature for f in agents.findings_for_run(s, run2.id)}
        assert "recon:no_statements" not in sigs2  # suppressed by feedback


def test_baselines_learned_and_sharpen(fresh_db):
    from bizclinik_erp import agents
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import AgentBaseline

    with get_session() as s:
        _seed_activity(s)
        agents.get_agent("fpa").run(s, use_llm=False)
    with get_session() as s:
        b = s.execute(select(AgentBaseline).where(
            AgentBaseline.agent_key == "fpa",
            AgentBaseline.metric_key == "fpa:gross_margin")).scalar_one()
        assert b.sample_n == 1
    with get_session() as s:
        agents.get_agent("fpa").run(s, use_llm=False)
    with get_session() as s:
        b = s.execute(select(AgentBaseline).where(
            AgentBaseline.agent_key == "fpa",
            AgentBaseline.metric_key == "fpa:gross_margin")).scalar_one()
        assert b.sample_n == 2  # the baseline accumulates across runs


def test_exception_agent_flags_outlier(fresh_db):
    """Post a normal distribution of expense postings plus one huge outlier and
    confirm the Exception Agent flags it as unusual for that account."""
    from bizclinik_erp import agents
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services.ledger import JELine, post_journal

    with get_session() as s:
        exp, inc, asset = _accounts(s)
        base = date.today() - timedelta(days=30)
        for i in range(10):
            amt = 100_000 + i * 1_000  # ~100k cluster
            post_journal(s, base + timedelta(days=i), f"reg {i}",
                         [JELine(account_id=exp.id, debit=amt),
                          JELine(account_id=asset.id, credit=amt)],
                         source_kind="TEST")
        # The outlier: a round 5,000,000 posting.
        post_journal(s, base + timedelta(days=11), "big one",
                     [JELine(account_id=exp.id, debit=5_000_000),
                      JELine(account_id=asset.id, credit=5_000_000)],
                     source_kind="TEST")

    with get_session() as s:
        run = agents.get_agent("exception").run(s, use_llm=False)
        kinds = {f.kind for f in agents.findings_for_run(s, run.id)}
        assert "outlier_posting" in kinds or "round_number" in kinds


def test_record_feedback_updates_learning_summary(fresh_db):
    from bizclinik_erp import agents
    from bizclinik_erp.db import get_session

    with get_session() as s:
        run = agents.get_agent("tax").run(s, use_llm=False)
        f = agents.findings_for_run(s, run.id)[0]
        agents.record_feedback(s, f.id, status="accepted", rating=5, note="useful")
    with get_session() as s:
        summary = agents.learning_summary(s, "tax")
        assert summary["accepted"] == 1
        assert summary["dismissed"] == 0


def test_api_module_imports_with_agent_endpoints(fresh_db):
    """The REST app wires the agent endpoints without import/route errors."""
    import api.main as main
    paths = {r.path for r in main.app.routes}
    assert "/api/v1/agents" in paths
    assert "/api/v1/agents/{key}/run" in paths
