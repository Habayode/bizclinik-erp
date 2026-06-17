"""Shared UI helpers for the Streamlit pages.

Goal: make the Streamlit pages look like a real ERP product, not a prototype.
Provides a single CSS injection + a set of HTML/Altair helpers that every page
calls so the brand stays consistent.

IMPORTANT: every helper emits HTML on a SINGLE line with no leading whitespace.
Streamlit's markdown renderer treats lines starting with 4+ spaces as a code
block — so multi-line HTML templates (even when passed with
unsafe_allow_html=True) get escaped and shown as text. Use _h() to collapse.
"""
from __future__ import annotations

import re
from typing import Optional

import altair as alt
import pandas as pd
import streamlit as st


def _h(html: str) -> str:
    """Collapse all interior whitespace runs to single spaces. Stops Streamlit
    markdown from interpreting indented HTML as a code block."""
    return re.sub(r"\s+", " ", html).strip()


# ---- brand palette ---------------------------------------------------------

BRAND = {
    "primary":   "#1F3864",   # deep navy — header / accents
    "accent":    "#0EA5A4",   # teal — primary CTA / chart hi
    "ink":       "#0F172A",
    "muted":     "#64748B",
    "surface":   "#FFFFFF",
    "bg":        "#F4F6FB",
    "border":    "#E5E7EB",
    "success":   "#16A34A",
    "warning":   "#F59E0B",
    "danger":    "#DC2626",
    "info":      "#2563EB",
    "chart_a":   "#1F3864",
    "chart_b":   "#0EA5A4",
    "chart_c":   "#F59E0B",
    "chart_d":   "#DC2626",
}


# ---- CSS -------------------------------------------------------------------


_CSS = """
<style>
/* Base typography + background */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                 'Helvetica Neue', Arial, sans-serif;
    color: __INK__;
}
[data-testid="stAppViewContainer"] { background: __BG__; }
[data-testid="stHeader"] { background: transparent; }

/* Push main content down so our hero clears Streamlit's chrome */
.block-container { padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1400px; }

/* Sidebar — branded gradient */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, __PRIMARY__ 0%, #16284F 100%);
}
[data-testid="stSidebar"] * { color: #F1F5F9 !important; }
[data-testid="stSidebar"] a { color: #BAE6FD !important; }
[data-testid="stSidebar"] .stRadio label,
[data-testid="stSidebar"] .stSelectbox label { color: #CBD5E1 !important; }
[data-testid="stSidebar"] [data-testid="stSidebarNav"] li a {
    border-radius: 8px;
    padding: 6px 10px;
    margin: 2px 6px;
}
[data-testid="stSidebar"] [data-testid="stSidebarNav"] li a:hover {
    background: rgba(255,255,255,0.07);
}

/* Brand hero bar at the top of every page */
.brand-hero {
    background: linear-gradient(120deg, __PRIMARY__ 0%, #2E4F8C 60%, __ACCENT__ 140%);
    border-radius: 14px;
    padding: 18px 22px;
    color: white;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 4px 18px rgba(31,56,100,0.18);
    margin-bottom: 18px;
}
.brand-hero .brand-left { display: flex; gap: 14px; align-items: center; }
.brand-hero.compact { padding: 8px 16px; margin-bottom: 10px; border-radius: 10px; }
.brand-hero.compact .logo { width: 30px; height: 30px; font-size: 0.8rem; }
.brand-hero.compact h1 { font-size: 1.05rem; }
.brand-hero.compact .sub { font-size: 0.75rem; margin-top: 0; }
.brand-hero .logo {
    width: 44px; height: 44px; border-radius: 10px;
    background: rgba(255,255,255,0.18);
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 20px; letter-spacing: -0.5px;
}
.brand-hero h1 { color: white; margin: 0; font-size: 1.35rem; font-weight: 700; }
.brand-hero .sub { color: #DBEAFE; font-size: 0.85rem; margin-top: 2px; }
.brand-hero .right { text-align: right; font-size: 0.85rem; opacity: 0.92; }
.brand-hero .right b { display: block; font-size: 1rem; }

/* Section header */
.section-header {
    display: flex; align-items: center; justify-content: space-between;
    margin: 22px 0 10px 0;
}
.section-header .title { font-size: 1.05rem; font-weight: 700; color: __INK__; }
.section-header .subtitle { font-size: 0.85rem; color: __MUTED__; }

/* KPI cards */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 14px;
    margin-bottom: 6px;
}
.kpi-card {
    background: __SURFACE__;
    border: 1px solid __BORDER__;
    border-radius: 12px;
    padding: 14px 16px;
    position: relative;
    transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.kpi-card:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(15,23,42,0.06); }
.kpi-card .label {
    font-size: 0.78rem; font-weight: 500; color: __MUTED__;
    text-transform: uppercase; letter-spacing: 0.06em;
}
.kpi-card .value {
    font-size: 1.45rem; font-weight: 700; color: __INK__;
    margin: 6px 0 2px 0; letter-spacing: -0.4px;
}
.kpi-card .delta { font-size: 0.78rem; font-weight: 600; }
.kpi-card .delta.up    { color: __SUCCESS__; }
.kpi-card .delta.down  { color: __DANGER__; }
.kpi-card .delta.neutral { color: __MUTED__; }
.kpi-card .icon {
    position: absolute; top: 12px; right: 12px;
    width: 30px; height: 30px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 14px; font-weight: 700;
}
.kpi-card .accent-bar {
    position: absolute; left: 0; top: 14px; bottom: 14px; width: 3px;
    border-radius: 2px;
}

/* Pills */
.pill { display: inline-block; padding: 2px 9px; border-radius: 999px;
        font-size: 0.72rem; font-weight: 600; letter-spacing: 0.02em; }
.pill-ok      { background: #DCFCE7; color: #166534; }
.pill-warn    { background: #FEF3C7; color: #92400E; }
.pill-error   { background: #FEE2E2; color: #991B1B; }
.pill-info    { background: #DBEAFE; color: #1E40AF; }
.pill-neutral { background: #E2E8F0; color: __MUTED__; }

/* Cards */
.surface {
    background: __SURFACE__;
    border: 1px solid __BORDER__;
    border-radius: 12px;
    padding: 18px 20px;
    margin-bottom: 14px;
}
.surface h3 { margin-top: 0; color: __INK__; font-weight: 700; font-size: 1rem; }

/* Tables (Streamlit dataframe) — restyle the header */
[data-testid="stDataFrame"] {
    border: 1px solid __BORDER__;
    border-radius: 10px;
    overflow: hidden;
}

/* Buttons */
.stButton > button[kind="primary"] {
    background: __PRIMARY__;
    border: 1px solid __PRIMARY__;
    color: white; font-weight: 600;
    border-radius: 8px;
}
.stButton > button[kind="primary"]:hover { background: #16284F; border-color: #16284F; }
.stButton > button { border-radius: 8px; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid __BORDER__; }
.stTabs [data-baseweb="tab"] {
    background: transparent; border-radius: 8px 8px 0 0;
    padding: 8px 14px; font-weight: 500;
}
.stTabs [aria-selected="true"] { color: __PRIMARY__ !important; font-weight: 700; }
.stTabs [aria-selected="true"]::after {
    content: ""; display: block; height: 3px; background: __ACCENT__;
    margin-top: 6px; border-radius: 2px;
}

/* Metric labels lowercase looks weird — Streamlit's default has muted color, keep */

/* Hide Streamlit's default footer/menu chrome */
footer { visibility: hidden; }
#MainMenu { visibility: hidden; }

/* ---- Responsive / mobile ------------------------------------------------ */
/* Wide tables never overflow the viewport — scroll horizontally instead. */
[data-testid="stDataFrame"], [data-testid="stTable"] { overflow-x: auto; }

@media (max-width: 768px) {
    /* Tighter page gutters so content isn't cramped against the edges. */
    .block-container, [data-testid="stAppViewContainer"] .main .block-container {
        padding-left: 0.75rem !important; padding-right: 0.75rem !important;
        padding-top: 1rem !important;
    }
    /* Stack st.columns() vertically instead of squeezing them side-by-side. */
    [data-testid="stHorizontalBlock"] {
        flex-direction: column !important; gap: 0.5rem !important;
    }
    [data-testid="stHorizontalBlock"] > [data-testid="column"] {
        width: 100% !important; flex: 1 1 100% !important;
        min-width: 100% !important;
    }
    /* Hero + headings scale down. */
    h1 { font-size: 1.5rem !important; line-height: 1.25 !important; }
    h2 { font-size: 1.2rem !important; }
    .brand-hero { padding: 16px !important; flex-wrap: wrap !important; }
    .brand-hero h1 { font-size: 1.4rem !important; }
    .brand-hero .right { display: none !important; }  /* drop the side badge */
    /* KPI / metric cards full width and comfortable to tap. */
    [data-testid="stMetric"] { padding: 10px 12px !important; }
    /* Buttons span the row so they're easy to hit. */
    .stButton > button, .stDownloadButton > button,
    .stFormSubmitButton > button { width: 100% !important; }
    /* Let the sidebar (nav) take most of the screen when opened. */
    [data-testid="stSidebar"] { min-width: 80vw !important; width: 80vw !important; }
}

/* Tablet: keep two-up columns but allow wrapping rather than overflow. */
@media (min-width: 769px) and (max-width: 1024px) {
    [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
}
</style>
"""


def inject_brand() -> None:
    """Inject the global CSS. Call once per page. Also drains any flash
    message queued by ``flash()`` before the last rerun (as a toast), so
    confirmations survive st.rerun() instead of vanishing."""
    css = _CSS
    for key, val in BRAND.items():
        css = css.replace(f"__{key.upper()}__", val)
    st.markdown(css, unsafe_allow_html=True)
    msg = st.session_state.pop("_ui_flash", None)
    if msg:
        st.toast(msg.get("text", ""), icon=msg.get("icon"))


def flash(text: str, icon: str = "✅") -> None:
    """Queue a toast that shows AFTER the next rerun (st.success + st.rerun
    wipes the message before anyone reads it; this survives)."""
    st.session_state["_ui_flash"] = {"text": text, "icon": icon}


def school_mode() -> bool:
    """True when the active tenant is a school (Company.vertical == 'school').
    Lets shared screens use school-friendly labels. Fails safe to False."""
    try:
        from .db import get_session
        from .models import Company
        with get_session() as s:
            co = s.query(Company).first()
            return bool(co and (co.vertical or "general") == "school")
    except Exception:
        return False


def money_col(label: str):
    """Consistent ₦ column for st.dataframe/data_editor column_config —
    thousands separators via the 'localized' preset, ₦ carried in the label."""
    if "₦" not in label:
        label = f"{label} (₦)"
    return st.column_config.NumberColumn(label, format="localized")


_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def bulk_import_expander(kind: str, label: str, noun: Optional[str] = None) -> None:
    """Reusable '📥 Bulk import from Excel' widget: download template, upload a
    filled file, preview, import. ``kind`` is a key in services.bulk_import.SPECS
    (customer/supplier/product/employee/account). ``noun`` overrides the row
    wording (e.g. 'student / parent') without changing the underlying importer."""
    from .db import get_session
    from .services import bulk_import
    noun = noun or kind
    with st.expander(f"📥 Bulk import {label.lower()} from Excel "
                     "(migrate your existing list at once)"):
        st.markdown(
            f"**Faster than one-by-one:** download the template, fill one row "
            f"per {noun}, then upload it here. The first sheet is where you fill "
            "your data — the **Instructions** sheet explains every column.")
        st.download_button(
            f"⬇ Download {noun} template (.xlsx)",
            data=bulk_import.template_bytes(kind),
            file_name=f"Trakit365_{label.lower().replace(' ', '_')}_template.xlsx",
            mime=_XLSX_MIME, key=f"{kind}_tpl_dl")
        up = st.file_uploader("Upload your filled template", type=["xlsx"],
                              key=f"{kind}_upload")
        if up is not None:
            try:
                df = pd.read_excel(up)
            except Exception as e:   # noqa: BLE001
                st.error(f"Couldn't read that file: {e}")
                return
            valid = int(df["name"].notna().sum()) if "name" in df.columns else 0
            st.caption(f"{valid} row(s) with a name found. Preview:")
            st.dataframe(df.head(20), hide_index=True, width="stretch")
            if valid and st.button(f"Import {valid} {label.lower()}",
                                   type="primary", key=f"{kind}_import_btn"):
                try:
                    with get_session() as s:
                        res = bulk_import.import_rows(s, kind, df)
                except ValueError as e:
                    st.error(str(e)); return
                msg = f"Imported {res['created']} {label.lower()}"
                if res["skipped"]:
                    msg += f" · {res['skipped']} skipped"
                flash(msg + ".")
                for e in res["errors"][:8]:
                    st.caption("• " + e)
                st.rerun()


def pick_row(df, *, key: str, column_config=None, height=None):
    """Render a single-row-selectable dataframe; return the selected row
    (as a pandas Series) or None. Replaces the old 'type the id' pattern."""
    kwargs = {"height": height} if height is not None else {}
    event = st.dataframe(
        df, hide_index=True, width="stretch", key=key,
        on_select="rerun", selection_mode="single-row",
        column_config=column_config, **kwargs)
    rows = event.selection.rows if event and event.selection else []
    if rows:
        return df.iloc[rows[0]]
    return None


def hero(title: str, subtitle: str = "", *,
         badge: Optional[str] = None,
         right_label: Optional[str] = None,
         right_value: Optional[str] = None,
         compact: bool = False) -> None:
    """Branded page hero bar. Title on left, optional summary on right."""
    right_html = ""
    if right_label or right_value:
        right_html = (
            f"<div class='right'>"
            f"<div>{right_label or ''}</div>"
            f"<b>{right_value or ''}</b>"
            "</div>"
        )
    initials = (badge or title)[:2].upper()
    compact_cls = " compact" if compact else ""
    html = _h(f"""
        <div class='brand-hero{compact_cls}'>
            <div class='brand-left'>
                <div class='logo'>{initials}</div>
                <div>
                    <h1>{title}</h1>
                    <div class='sub'>{subtitle}</div>
                </div>
            </div>
            {right_html}
        </div>
    """)
    st.markdown(html, unsafe_allow_html=True)


def section(title: str, subtitle: str = "") -> None:
    html = _h(f"""
        <div class='section-header'>
            <div class='title'>{title}</div>
            <div class='subtitle'>{subtitle}</div>
        </div>
    """)
    st.markdown(html, unsafe_allow_html=True)


def money(x: float, symbol: str = "₦") -> str:
    if x is None:
        return "—"
    return f"{symbol}{x:,.2f}"


def _money_float_cols(df: "pd.DataFrame") -> list:
    """Float columns of a DataFrame — these hold money/amounts/rates and get
    thousands-separated for display. Int columns (ids, years, counts, terms,
    form levels) are left alone so a year like 2025 never becomes '2,025'."""
    return [c for c in df.columns if pd.api.types.is_float_dtype(df[c])]


def dataframe(data, **kwargs):
    """Drop-in for ``st.dataframe`` that comma-formats numeric columns so money
    reads ``26,043,000.00`` instead of ``26043000`` — without changing the
    underlying values (sorting/filtering still work). Only float columns are
    formatted; if a caller passes its own ``column_config`` we defer to it."""
    if isinstance(data, pd.DataFrame) and "column_config" not in kwargs:
        cols = _money_float_cols(data)
        if cols:
            try:
                data = data.style.format({c: "{:,.2f}" for c in cols}, na_rep="—")
            except Exception:   # noqa: BLE001 — never let formatting break a page
                pass
    return st.dataframe(data, **kwargs)


def kpi_grid(items: list[dict]) -> None:
    """Render a row of KPI cards. Each item:
        {label, value, delta?, delta_dir?, icon?, color?}
    color  - primary | accent | success | warning | danger | info  (controls accent bar + icon bg)
    delta_dir - 'up' | 'down' | 'neutral'
    """
    cards = []
    for it in items:
        color = it.get("color", "primary")
        accent = BRAND.get(color, BRAND["primary"])
        icon = it.get("icon", "")
        label = it["label"]
        value = it["value"]
        delta_html = ""
        if "delta" in it:
            cls = it.get("delta_dir", "neutral")
            arrow = {"up": "▲", "down": "▼", "neutral": "■"}.get(cls, "■")
            delta_html = (f"<div class='delta {cls}'>{arrow} {it['delta']}</div>")
        icon_bg = f"rgba(31,56,100,0.10)" if color == "primary" else f"{accent}1A"
        icon_html = (f"<div class='icon' style='background:{icon_bg};color:{accent}'>"
                     f"{icon}</div>") if icon else ""
        cards.append(_h(f"""
            <div class='kpi-card'>
                <div class='accent-bar' style='background:{accent}'></div>
                {icon_html}
                <div class='label'>{label}</div>
                <div class='value'>{value}</div>
                {delta_html}
            </div>
        """))
    html = _h(f"<div class='kpi-grid'>{''.join(cards)}</div>")
    st.markdown(html, unsafe_allow_html=True)


def pill(text: str, kind: str = "neutral") -> str:
    return f"<span class='pill pill-{kind}'>{text}</span>"


# ---- charts ----------------------------------------------------------------


def revenue_vs_expense_chart(df: pd.DataFrame, *,
                              date_col: str = "month",
                              rev_col: str = "revenue",
                              exp_col: str = "expense") -> alt.Chart:
    """Stacked bar of revenue vs expense by period."""
    df_long = df.melt(id_vars=[date_col], value_vars=[rev_col, exp_col],
                       var_name="metric", value_name="amount")
    return (
        alt.Chart(df_long).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X(f"{date_col}:N", title=None,
                     axis=alt.Axis(labelAngle=0, labelColor=BRAND["muted"])),
            y=alt.Y("amount:Q", title="₦",
                     axis=alt.Axis(format=",.0f", labelColor=BRAND["muted"],
                                   gridColor=BRAND["border"])),
            color=alt.Color("metric:N",
                             scale=alt.Scale(domain=[rev_col, exp_col],
                                              range=[BRAND["accent"], BRAND["primary"]]),
                             legend=alt.Legend(title=None, orient="top",
                                               labelColor=BRAND["muted"])),
            tooltip=[date_col, "metric", alt.Tooltip("amount:Q", format=",.2f")],
            xOffset="metric:N",
        )
        .properties(height=240)
        .configure_view(strokeWidth=0)
    )


def expense_breakdown_chart(df: pd.DataFrame, *,
                             name_col: str = "name",
                             amount_col: str = "amount") -> alt.Chart:
    """Horizontal bar of expense by account."""
    return (
        alt.Chart(df).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4,
                                color=BRAND["primary"])
        .encode(
            y=alt.Y(f"{name_col}:N", sort="-x", title=None,
                     axis=alt.Axis(labelColor=BRAND["muted"])),
            x=alt.X(f"{amount_col}:Q", title="₦",
                     axis=alt.Axis(format=",.0f", labelColor=BRAND["muted"],
                                   gridColor=BRAND["border"])),
            tooltip=[name_col, alt.Tooltip(f"{amount_col}:Q", format=",.2f")],
        )
        .properties(height=max(180, 28 * len(df)))
        .configure_view(strokeWidth=0)
    )


def aging_bar_chart(df: pd.DataFrame, partner_col: str = "customer_name") -> alt.Chart:
    """Stacked aging buckets per partner."""
    buckets = ["0-30", "31-60", "61-90", "90+"]
    df_long = df.melt(id_vars=[partner_col], value_vars=buckets,
                       var_name="bucket", value_name="amount")
    return (
        alt.Chart(df_long).mark_bar()
        .encode(
            y=alt.Y(f"{partner_col}:N", sort="-x", title=None,
                     axis=alt.Axis(labelColor=BRAND["muted"])),
            x=alt.X("sum(amount):Q", title="₦",
                     axis=alt.Axis(format=",.0f", labelColor=BRAND["muted"])),
            color=alt.Color(
                "bucket:N",
                scale=alt.Scale(domain=buckets,
                                 range=[BRAND["success"], BRAND["info"],
                                        BRAND["warning"], BRAND["danger"]]),
                legend=alt.Legend(title="Bucket", orient="top",
                                  labelColor=BRAND["muted"]),
            ),
            tooltip=[partner_col, "bucket",
                      alt.Tooltip("amount:Q", format=",.2f")],
        )
        .properties(height=max(180, 30 * df[partner_col].nunique()))
        .configure_view(strokeWidth=0)
    )


def cash_position_chart(rows: list[dict]) -> alt.Chart:
    """Single-bar per bank account showing GL balance."""
    df = pd.DataFrame(rows)
    return (
        alt.Chart(df).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4,
                                color=BRAND["accent"])
        .encode(
            y=alt.Y("name:N", sort="-x", title=None,
                     axis=alt.Axis(labelColor=BRAND["muted"])),
            x=alt.X("balance:Q", title="₦",
                     axis=alt.Axis(format=",.0f", labelColor=BRAND["muted"])),
            tooltip=["name", alt.Tooltip("balance:Q", format=",.2f")],
        )
        .properties(height=max(160, 32 * len(df)))
        .configure_view(strokeWidth=0)
    )
