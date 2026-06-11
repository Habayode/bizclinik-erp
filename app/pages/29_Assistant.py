"""Assistant — built-in help + live-data Q&A (native Streamlit chat)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from bizclinik_erp.db import get_session
from bizclinik_erp import assistant
from bizclinik_erp import auth
from bizclinik_erp import ui_kit as ui

st.set_page_config(page_title="Assistant · Trakit365 ERP", layout="centered",
                    page_icon="💬")
ui.inject_brand()
auth.require_login()
ui.hero("Assistant", "Ask how to use the ERP — or about your numbers",
        badge="AI", right_label="Help", right_value="Beta")

# Live data snapshot for the active business (best-effort).
snap: dict = {}
try:
    with get_session() as s:
        snap = assistant.compute_snapshot(s)
except Exception:
    snap = {}

if "asst_msgs" not in st.session_state:
    st.session_state.asst_msgs = [{"role": "assistant", "content": assistant.GREETING}]

# Quick-start suggestions.
st.caption("Try one of these:")
sug_cols = st.columns(3)
for i, sug in enumerate(assistant.SUGGESTIONS):
    if sug_cols[i % 3].button(sug, key=f"asst_sug_{i}", use_container_width=True):
        st.session_state.asst_pending = sug

# History.
for m in st.session_state.asst_msgs:
    with st.chat_message(m["role"], avatar=("💬" if m["role"] == "assistant" else None)):
        st.markdown(m["content"])

typed = st.chat_input("Ask a question…")
question = typed or st.session_state.pop("asst_pending", None)
if question:
    st.session_state.asst_msgs.append({"role": "user", "content": question})
    reply = assistant.answer(question, snap)
    st.session_state.asst_msgs.append({"role": "assistant", "content": reply})
    st.rerun()

c1, c2 = st.columns([3, 1])
c1.caption("Answers cover how-to **and** your live figures (revenue, cash, AR/AP, "
           "pending approvals, counts). Rule-based today; upgradeable to AI later.")
if c2.button("Clear chat", use_container_width=True):
    st.session_state.asst_msgs = [{"role": "assistant", "content": assistant.GREETING}]
    st.rerun()

auth.render_logout_in_sidebar()
