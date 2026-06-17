"""User Manual — the full illustrated guide, rendered in-app (System)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from bizclinik_erp import auth, manuals
from bizclinik_erp import ui_kit as ui

st.set_page_config(page_title="User Manual · Trakit365 ERP", layout="wide",
                    page_icon="📖")
ui.inject_brand()
auth.require_login()


def _vertical() -> str:
    """The active tenant's vertical — picks the school manual for schools."""
    try:
        from bizclinik_erp.db import get_session
        from bizclinik_erp.models import Company
        with get_session() as s:
            co = s.query(Company).first()
            return (co.vertical or "general") if co else "general"
    except Exception:
        return "general"


spec = manuals.manual_for(_vertical())
ui.hero(spec["title"], spec["subtitle"], badge="UM",
        right_label="Module", right_value="Help")

ROOT = Path(__file__).resolve().parent.parent.parent
DOCS = ROOT / "docs"
MD = spec["md"]
PDF = spec["pdf"]

if not MD.exists():
    st.warning("The user manual file isn't available on this server.")
    auth.render_logout_in_sidebar()
    st.stop()

md_text = MD.read_text(encoding="utf-8")

# ---- download row -----------------------------------------------------------
cols = st.columns([1, 1, 3])
cols[0].download_button(
    "⬇ Download (Markdown)", data=md_text.encode("utf-8"),
    file_name=spec["md_name"], mime="text/markdown",
    width="stretch")
if PDF.exists():
    cols[1].download_button(
        "⬇ Download PDF", data=PDF.read_bytes(),
        file_name=PDF.name, mime="application/pdf",
        width="stretch")
else:
    cols[1].caption("PDF: generate with `scripts/manual_to_pdf.py`")

st.divider()

# ---- render markdown with inline images -------------------------------------
# Split on image tags so local screenshots can be shown via st.image (st.markdown
# can't load local files). Images in the manual sit on their own lines.
IMG = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
parts = re.split(r"(!\[[^\]]*\]\([^)]+\))", md_text)

for part in parts:
    if not part.strip():
        continue
    m = IMG.fullmatch(part.strip())
    if m:
        alt, src = m.group(1), m.group(2)
        img_path = (DOCS / src).resolve()
        if img_path.exists():
            st.image(str(img_path), caption=alt or None,
                     width="stretch")
        else:
            st.caption(f"_(screenshot unavailable: {src})_")
    else:
        st.markdown(part)

auth.render_logout_in_sidebar()
