"""AI Agents — six analytical agents that read your books and self-improve.

RECON · Tax · FP&A · CFO · Insight · Exception. Each run is graded by you
(useful / not relevant); that feedback plus per-company baselines make the
agents sharper over time.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from bizclinik_erp.db import get_session
from bizclinik_erp import agents as agents_mod
from bizclinik_erp.agents import llm
from bizclinik_erp import ui_kit as ui
from bizclinik_erp import auth

st.set_page_config(page_title="AI Agents · Trakit365 ERP", layout="wide",
                   page_icon="🤖")
ui.inject_brand()
auth.require_login()
auth.require_perm("agents.view")
ui.hero("AI Agents", "Agents that read your books and get smarter with your feedback",
        badge="AI", right_label="Module", right_value="Intelligence", compact=True)

can_run = auth.has_perm("agents.run")
all_agents = agents_mod.list_agents()

# ---- agent picker ----------------------------------------------------------
labels = [f"{a.icon} {a.label}" for a in all_agents]
sel = st.selectbox("Agent", range(len(all_agents)),
                   format_func=lambda i: labels[i], key="agent_sel")
agent = all_agents[sel]
st.caption(agent.description)

if llm.available():
    st.caption("🧠 Claude synthesis is ON — findings are summarised by Claude Opus 4.8.")
else:
    st.caption("⚙️ Deterministic mode. Set ANTHROPIC_API_KEY on the server to add "
               "Claude synthesis. With no key, nothing leaves your server.")

c1, c2, c3 = st.columns([1, 1, 1])
ps = c1.date_input("Period start", value=date(date.today().year, 1, 1), key="ag_ps")
pe = c2.date_input("Period end", value=date.today(), key="ag_pe")
with c3:
    st.write("")
    st.write("")
    run_clicked = st.button("▶ Run analysis", disabled=not can_run,
                            use_container_width=True, type="primary")
if not can_run:
    st.info("Your role can view agent findings but not run them.")

if run_clicked:
    with st.spinner(f"Running {agent.label}…"):
        with get_session() as s:
            run = agent.run(s, period_start=ps, period_end=pe)
            n = run.findings_count
    ui.flash(f"{agent.label} completed — {n} finding(s).")
    st.rerun()

# ---- latest run ------------------------------------------------------------
with get_session() as s:
    run = agents_mod.latest_run(s, agent.key)
    findings = agents_mod.findings_for_run(s, run.id) if run else []
    learn = agents_mod.learning_summary(s, agent.key)

if run is None:
    st.info("No analysis yet — click **Run analysis** to produce findings.")
    st.stop()

st.markdown(f"### {run.headline or agent.label}")
meta = f"Last run {run.run_at:%Y-%m-%d %H:%M} · {run.findings_count} finding(s) · {run.model_used}"
st.caption(meta)
if run.summary:
    st.markdown(run.summary)
try:
    recs = json.loads(run.recommendations or "[]")
except Exception:
    recs = []
if recs:
    st.markdown("**Recommended actions**")
    for r in recs:
        st.markdown(f"- {r}")

# ---- findings table (S/N standard) -----------------------------------------
ui.section("Findings")
if findings:
    rows = [{
        "S/N": i,
        "Severity": f.severity.upper(),
        "Finding": f.title,
        "Detail": f.detail or "",
        "Metric": f.metric_value,
        "Status": f.status,
    } for i, f in enumerate(findings, start=1)]
    ui.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
else:
    st.caption("No findings in the latest run.")

# ---- FP&A forward view: forecast · rolling cash flow · next-year budget -----
if agent.key == "fpa":
    from bizclinik_erp.services import forecast as fc_svc

    ui.section("Forecast · Rolling cash flow · Next-year budget")
    with get_session() as s:
        bundle = fc_svc.forecast_bundle(s, as_of=pe, horizon=12, months_back=12)
    t_fc, t_cf, t_bud = st.tabs(
        ["📈 P&L forecast", "💧 Rolling cash flow", "🗓 Next-year budget"])

    with t_fc:
        act = pd.DataFrame(bundle["monthly_actuals"])
        fcast = pd.DataFrame(bundle["pnl_forecast"])
        frames = []
        if not act.empty:
            frames.append(act[["label", "net"]].assign(series="Actual net"))
        if not fcast.empty:
            frames.append(fcast[["label", "net"]].assign(series="Forecast net"))
        if frames:
            chart = pd.concat(frames).pivot(index="label", columns="series",
                                            values="net")
            st.line_chart(chart)
        if not fcast.empty:
            st.markdown("**Projected P&L — next 12 months**")
            fdf = fcast.rename(columns={"label": "Month", "revenue": "Revenue",
                                        "costs": "Costs", "net": "Net"})
            fdf.insert(0, "S/N", range(1, len(fdf) + 1))
            ui.dataframe(fdf, hide_index=True, width="stretch")
        else:
            st.caption("Not enough posted history yet to project — the forecast "
                       "builds once there are a few months of activity.")

    with t_cf:
        cf = bundle["cash_flow"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Opening cash", ui.money(cf["opening"]))
        c2.metric("Lowest projected", ui.money(cf["min_balance"]))
        c3.metric("Ending (12m)", ui.money(cf["ending"]))
        if cf["first_negative"]:
            st.warning(f"⚠️ Cash is projected to go negative in "
                       f"{cf['first_negative']['label']} "
                       f"({ui.money(cf['first_negative']['shortfall'])}).")
        rows_cf = pd.DataFrame(cf["rows"])
        if not rows_cf.empty:
            st.line_chart(rows_cf.set_index("label")[["balance"]])
            disp = rows_cf.rename(columns={"label": "Month", "inflow": "Inflow",
                                           "outflow": "Outflow", "net": "Net",
                                           "balance": "Balance"})
            disp.insert(0, "S/N", range(1, len(disp) + 1))
            ui.dataframe(disp, hide_index=True, width="stretch")

    with t_bud:
        ann = bundle["annual"]
        c1, c2, c3 = st.columns(3)
        c1.metric(f"FY{ann['year']} revenue", ui.money(ann["revenue"]))
        c2.metric("Costs", ui.money(ann["costs"]))
        c3.metric("Net", ui.money(ann["net"]))
        agg: dict = {}
        for r in bundle["budget_rows"]:
            a = agg.setdefault((r["account_id"], r["account_name"]),
                               {"kind": r["kind"], "amount": 0.0})
            a["amount"] += r["amount"]
        brows = [{"Account": name, "Type": v["kind"],
                  "Annual budget": round(v["amount"], 2)}
                 for (aid, name), v in agg.items()]
        brows.sort(key=lambda x: (x["Type"], -x["Annual budget"]))
        if brows:
            bdf = pd.DataFrame(brows)
            bdf.insert(0, "S/N", range(1, len(bdf) + 1))
            ui.dataframe(bdf, hide_index=True, width="stretch")
            if can_run and st.button(
                    f"💾 Save FY{ann['year']} budget to the Budgets module",
                    key="save_budget", type="primary"):
                with get_session() as s:
                    res = fc_svc.save_as_budget(s, as_of=pe)
                ui.flash(f"Saved '{res['name']}' — {res['lines']} budget lines. "
                         f"Open the Budgets page to review budget-vs-actual.")
                st.rerun()
        else:
            st.caption("Not enough history to build a next-year budget yet.")

    st.caption("Assumptions — " + " ".join(bundle["assumptions"]))

# ---- feedback (the learning loop) ------------------------------------------
if can_run and findings:
    ui.section("Teach the agent", "Grade a finding — the agent prioritises what "
                                   "you mark useful and stops resurfacing what you dismiss.")
    idx = st.selectbox("Finding", range(len(findings)),
                       format_func=lambda i: f"{i + 1}. {findings[i].title}",
                       key="fb_sel")
    target = findings[idx]
    fc1, fc2 = st.columns([1, 2])
    rating = fc1.slider("Usefulness", 1, 5, 3, key="fb_rate")
    note = fc2.text_input("Note (optional)", key="fb_note")
    b1, b2 = st.columns(2)
    if b1.button("✅ Useful (accept)", key="fb_acc", use_container_width=True):
        with get_session() as s:
            agents_mod.record_feedback(s, target.id, status="accepted",
                                       rating=rating, note=note or None)
        ui.flash("Recorded — the agent will prioritise similar findings.")
        st.rerun()
    if b2.button("🚫 Not relevant (dismiss)", key="fb_dis", use_container_width=True):
        with get_session() as s:
            agents_mod.record_feedback(s, target.id, status="dismissed",
                                       rating=rating, note=note or None)
        ui.flash("Dismissed — the agent will stop resurfacing this.")
        st.rerun()

# ---- what the agent has learned --------------------------------------------
with st.expander("📚 What this agent has learned"):
    st.write(f"Feedback so far: **{learn['accepted']}** accepted · "
             f"**{learn['dismissed']}** dismissed")
    if learn["baselines"]:
        brows = [{"S/N": i, "Metric": b["metric"], "Mean": b["mean"],
                  "Std dev": b["stddev"], "Samples": b["n"]}
                 for i, b in enumerate(learn["baselines"], start=1)]
        ui.dataframe(pd.DataFrame(brows), hide_index=True, width="stretch")
    else:
        st.caption("No learned baselines yet — they build up as you run the agent "
                   "across more periods.")
