"""Notifications + daily digest.

Computes operational alerts on the fly from the posted ledger / master data —
no new DB table is required. Surfaces:

  • Overdue receivables (AR)
  • Bills falling due soon (AP)
  • Products below reorder level
  • Cash position across bank accounts

`build_digest` aggregates everything into a single dict that the Streamlit
page, the CLI sender and the email renderers all consume. Render helpers emit
plain-text and branded HTML, and `send_digest_email` ships it over SMTP when
configured.
"""
from __future__ import annotations

import os
import smtplib
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BankAccount, Bill, DocStatus, SalesInvoice
from . import banking as bank_svc
from . import inventory as inv_svc

# Brand navy used by the HTML renderer (matches ui_kit.BRAND["primary"]).
_NAVY = "#1F3864"
_OPEN_STATUSES = [DocStatus.POSTED, DocStatus.PARTIAL]


# ---- individual alert computations ---------------------------------------


def overdue_invoices(session: Session, *, as_of: date) -> list[dict]:
    """POSTED/PARTIAL sales invoices past their due date with money outstanding.

    Returns one row per invoice, most overdue first:
        {number, customer, due_date, days_overdue, outstanding}
    """
    invs = session.execute(
        select(SalesInvoice).where(
            SalesInvoice.status.in_(_OPEN_STATUSES),
            SalesInvoice.due_date.is_not(None),
            SalesInvoice.due_date < as_of,
        )
    ).scalars().all()

    rows: list[dict] = []
    for inv in invs:
        outstanding = inv.outstanding
        if outstanding <= 0:
            continue
        rows.append({
            "number": inv.number,
            "customer": inv.customer.name if inv.customer else "",
            "due_date": inv.due_date,
            "days_overdue": (as_of - inv.due_date).days,
            "outstanding": outstanding,
        })
    rows.sort(key=lambda r: r["days_overdue"], reverse=True)
    return rows


def upcoming_bills(session: Session, *, as_of: date, within_days: int = 7) -> list[dict]:
    """POSTED/PARTIAL bills due between `as_of` and `as_of + within_days`.

    Returns one row per bill, soonest first:
        {number, supplier, due_date, days_until, outstanding}
    """
    horizon = as_of + timedelta(days=within_days)
    bills = session.execute(
        select(Bill).where(
            Bill.status.in_(_OPEN_STATUSES),
            Bill.due_date.is_not(None),
            Bill.due_date >= as_of,
            Bill.due_date <= horizon,
        )
    ).scalars().all()

    rows: list[dict] = []
    for b in bills:
        outstanding = b.outstanding
        if outstanding <= 0:
            continue
        rows.append({
            "number": b.number,
            "supplier": b.supplier.name if b.supplier else "",
            "due_date": b.due_date,
            "days_until": (b.due_date - as_of).days,
            "outstanding": outstanding,
        })
    rows.sort(key=lambda r: r["days_until"])
    return rows


def low_stock(session: Session) -> list[dict]:
    """Stockable products sitting below their reorder level.

    Reuses inventory_valuation (which already flags 'below_reorder') so the
    on-hand / cost numbers stay consistent with the inventory module.
        {sku, name, qty_on_hand, reorder_level, value_at_cost}
    """
    rows: list[dict] = []
    for v in inv_svc.inventory_valuation(session):
        if not v.get("below_reorder"):
            continue
        rows.append({
            "sku": v["sku"],
            "name": v["name"],
            "qty_on_hand": v["qty_on_hand"],
            "avg_cost": v["avg_cost"],
            "value_at_cost": v["value_at_cost"],
        })
    return rows


def cash_position(session: Session, *, as_of: date) -> dict:
    """Total cash across all active bank accounts.

    Reads BIZCLINIK_CASH_ALERT from the environment (default 0 → no alert).
    `below_threshold` is True only when a positive threshold is set and the
    total falls below it.
        {as_of, total, threshold, below_threshold, accounts: [...]}
    """
    try:
        threshold = float(os.environ.get("BIZCLINIK_CASH_ALERT", "0") or "0")
    except (TypeError, ValueError):
        threshold = 0.0

    accounts = session.execute(
        select(BankAccount).where(BankAccount.is_active == True)  # noqa: E712
        .order_by(BankAccount.code)
    ).scalars().all()

    rows: list[dict] = []
    total = 0.0
    for ba in accounts:
        bal = round(bank_svc.bank_balance(session, ba.id, as_of=as_of), 2)
        total += bal
        rows.append({"code": ba.code, "name": ba.name, "balance": bal})

    total = round(total, 2)
    below = bool(threshold > 0 and total < threshold)
    return {
        "as_of": as_of.isoformat(),
        "total": total,
        "threshold": threshold,
        "below_threshold": below,
        "accounts": rows,
    }


# ---- aggregate digest -----------------------------------------------------


def build_digest(session: Session, *, as_of: date) -> dict:
    """Roll the individual alerts up into a single digest dict."""
    overdue = overdue_invoices(session, as_of=as_of)
    upcoming = upcoming_bills(session, as_of=as_of)
    low = low_stock(session)
    cash = cash_position(session, as_of=as_of)

    overdue_total = round(sum(r["outstanding"] for r in overdue), 2)
    upcoming_total = round(sum(r["outstanding"] for r in upcoming), 2)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(),
        "overdue_count": len(overdue),
        "overdue_total": overdue_total,
        "upcoming_count": len(upcoming),
        "upcoming_total": upcoming_total,
        "low_stock_count": len(low),
        "cash_total": cash["total"],
        "cash_below_threshold": cash["below_threshold"],
        "items": {
            "overdue_invoices": overdue,
            "upcoming_bills": upcoming,
            "low_stock": low,
            "cash_position": cash,
        },
    }


# ---- rendering ------------------------------------------------------------


def _money(x: float) -> str:
    return f"NGN {x:,.2f}"


def render_digest_text(digest: dict) -> str:
    """Plain-text summary suitable for email body / console output."""
    items = digest.get("items", {})
    lines: list[str] = []
    lines.append("Trakit365 ERP — Daily Digest")
    lines.append(f"As of {digest.get('as_of', '')}  (generated {digest.get('generated_at', '')})")
    lines.append("=" * 48)
    lines.append("")

    lines.append(f"Overdue invoices: {digest['overdue_count']} "
                 f"totalling {_money(digest['overdue_total'])}")
    for r in items.get("overdue_invoices", []):
        lines.append(f"  - {r['number']}  {r['customer']}  "
                     f"due {r['due_date']}  {r['days_overdue']}d overdue  "
                     f"{_money(r['outstanding'])}")
    lines.append("")

    lines.append(f"Upcoming bills (next 7 days): {digest['upcoming_count']} "
                 f"totalling {_money(digest['upcoming_total'])}")
    for r in items.get("upcoming_bills", []):
        lines.append(f"  - {r['number']}  {r['supplier']}  "
                     f"due {r['due_date']}  in {r['days_until']}d  "
                     f"{_money(r['outstanding'])}")
    lines.append("")

    lines.append(f"Low stock items: {digest['low_stock_count']}")
    for r in items.get("low_stock", []):
        lines.append(f"  - {r['sku']}  {r['name']}  on hand {r['qty_on_hand']}")
    lines.append("")

    cash = items.get("cash_position", {})
    flag = "  [BELOW THRESHOLD]" if digest.get("cash_below_threshold") else ""
    lines.append(f"Cash position: {_money(digest['cash_total'])}{flag}")
    for r in cash.get("accounts", []):
        lines.append(f"  - {r['name']}  {_money(r['balance'])}")
    lines.append("")

    return "\n".join(lines)


def render_digest_html(digest: dict) -> str:
    """Simple branded HTML version (navy header)."""
    items = digest.get("items", {})

    def _rows(records: list[dict], cols: list[tuple[str, str]]) -> str:
        if not records:
            return "<tr><td style='padding:6px 10px;color:#64748B;'>None</td></tr>"
        out = []
        for rec in records:
            cells = "".join(
                f"<td style='padding:6px 10px;border-top:1px solid #E5E7EB;'>{rec.get(key, '')}</td>"
                for key, _ in cols
            )
            out.append(f"<tr>{cells}</tr>")
        return "".join(out)

    def _header(cols: list[tuple[str, str]]) -> str:
        return "".join(
            f"<th style='padding:6px 10px;text-align:left;font-size:12px;"
            f"color:#64748B;text-transform:uppercase;'>{label}</th>"
            for _, label in cols
        )

    overdue_cols = [("number", "Invoice"), ("customer", "Customer"),
                    ("due_date", "Due"), ("days_overdue", "Days"),
                    ("outstanding", "Outstanding")]
    bill_cols = [("number", "Bill"), ("supplier", "Supplier"),
                 ("due_date", "Due"), ("days_until", "In (days)"),
                 ("outstanding", "Outstanding")]
    stock_cols = [("sku", "SKU"), ("name", "Product"),
                  ("qty_on_hand", "On hand")]
    cash = items.get("cash_position", {})
    cash_cols = [("name", "Account"), ("balance", "Balance")]

    cash_flag = (" <span style='color:#DC2626;'>(below threshold)</span>"
                 if digest.get("cash_below_threshold") else "")

    def _table(title: str, cols: list[tuple[str, str]], records: list[dict]) -> str:
        return (
            f"<h3 style='color:{_NAVY};font-family:Arial,sans-serif;"
            f"font-size:15px;margin:18px 0 6px 0;'>{title}</h3>"
            "<table style='border-collapse:collapse;width:100%;"
            "font-family:Arial,sans-serif;font-size:13px;color:#0F172A;'>"
            f"<thead><tr>{_header(cols)}</tr></thead>"
            f"<tbody>{_rows(records, cols)}</tbody></table>"
        )

    return (
        "<div style='max-width:680px;margin:0 auto;font-family:Arial,sans-serif;'>"
        f"<div style='background:{_NAVY};color:#FFFFFF;padding:18px 22px;"
        "border-radius:10px 10px 0 0;'>"
        "<div style='font-size:18px;font-weight:700;'>Trakit365 ERP — Daily Digest</div>"
        f"<div style='font-size:13px;color:#DBEAFE;margin-top:2px;'>"
        f"As of {digest.get('as_of', '')} · generated {digest.get('generated_at', '')}</div>"
        "</div>"
        "<div style='border:1px solid #E5E7EB;border-top:none;"
        "border-radius:0 0 10px 10px;padding:8px 22px 22px 22px;'>"
        f"<p style='font-size:13px;color:#0F172A;'>"
        f"<b>{digest['overdue_count']}</b> overdue ({_money(digest['overdue_total'])}) · "
        f"<b>{digest['upcoming_count']}</b> bills due soon ({_money(digest['upcoming_total'])}) · "
        f"<b>{digest['low_stock_count']}</b> low-stock · "
        f"cash {_money(digest['cash_total'])}{cash_flag}</p>"
        + _table("Overdue invoices", overdue_cols, items.get("overdue_invoices", []))
        + _table("Upcoming bills (next 7 days)", bill_cols, items.get("upcoming_bills", []))
        + _table("Low stock", stock_cols, items.get("low_stock", []))
        + _table("Cash position", cash_cols, cash.get("accounts", []))
        + "</div></div>"
    )


# ---- email delivery -------------------------------------------------------


def _open_smtp(host: str, port: int) -> "smtplib.SMTP":
    """Open an SMTP connection: implicit TLS for port 465 (e.g. Hostinger,
    Gmail SSL) and STARTTLS otherwise. SMTP_SSL=1 forces implicit TLS on any
    port. The caller logs in and sends."""
    force_ssl = os.environ.get("SMTP_SSL", "").strip().lower() in ("1", "true", "yes")
    if port == 465 or force_ssl:
        return smtplib.SMTP_SSL(host, port, timeout=30)
    server = smtplib.SMTP(host, port, timeout=30)
    try:
        server.starttls()
    except smtplib.SMTPException:
        # Server may not support STARTTLS (e.g. local relay) — proceed.
        pass
    return server


def send_digest_email(digest: dict, *, to_addr: str) -> bool:
    """Send the digest over SMTP. Returns True on success, False otherwise.

    Reads SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM from the
    environment. If SMTP_HOST is unset the caller is expected to show the
    plain-text digest instead, so we just return False. All failures are
    swallowed and reported as False.
    """
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        return False

    try:
        port = int(os.environ.get("SMTP_PORT", "587") or "587")
        user = os.environ.get("SMTP_USER", "").strip()
        password = os.environ.get("SMTP_PASS", "")
        from_addr = os.environ.get("SMTP_FROM", user or "bizclinik@localhost").strip()

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Trakit365 ERP — Daily Digest ({digest.get('as_of', '')})"
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.attach(MIMEText(render_digest_text(digest), "plain", "utf-8"))
        msg.attach(MIMEText(render_digest_html(digest), "html", "utf-8"))

        with _open_smtp(host, port) as server:
            if user:
                server.login(user, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Generic SMTP send with a file attachment                                     #
# --------------------------------------------------------------------------- #

def smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST", "").strip())


def send_email_with_attachment(
    *, to_addr: str, subject: str, body_text: str,
    attachment_path: "str | None" = None, attachment_name: "str | None" = None,
    body_html: "str | None" = None, reply_to: "str | None" = None,
) -> bool:
    """Send an email (optionally with one file attachment) over SMTP.

    Reuses SMTP_HOST/PORT/USER/PASS/FROM. Returns True on success, False if SMTP
    is not configured or any error occurs (all failures swallowed).
    """
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host or not to_addr:
        return False
    try:
        from email.mime.base import MIMEBase
        from email import encoders
        from pathlib import Path

        port = int(os.environ.get("SMTP_PORT", "587") or "587")
        user = os.environ.get("SMTP_USER", "").strip()
        password = os.environ.get("SMTP_PASS", "")
        from_addr = os.environ.get("SMTP_FROM", user or "bizclinik@localhost").strip()

        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        if attachment_path:
            p = Path(attachment_path)
            data = p.read_bytes()
            part = MIMEBase("application", "octet-stream")
            part.set_payload(data)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment",
                            filename=attachment_name or p.name)
            msg.attach(part)

        with _open_smtp(host, port) as server:
            if user:
                server.login(user, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Resend HTTP API (works over 443 where outbound SMTP is blocked, e.g. on      #
# DigitalOcean droplets). Preferred transport when RESEND_API_KEY is set.      #
# --------------------------------------------------------------------------- #

def resend_configured() -> bool:
    return bool(os.environ.get("RESEND_API_KEY", "").strip())


def _send_via_resend(*, to_addr: str, subject: str, body_text: str,
                     reply_to: "str | None" = None,
                     body_html: "str | None" = None) -> bool:
    """Send one email through Resend's REST API over HTTPS. Reads RESEND_API_KEY
    and RESEND_FROM (defaults to Resend's shared 'onboarding@resend.dev' sender).
    Returns True on a 2xx response; all failures swallowed."""
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not api_key or not to_addr:
        return False
    import json as _json
    from urllib import request as _req
    from_addr = os.environ.get(
        "RESEND_FROM", "Trakit365 <onboarding@resend.dev>").strip()
    payload = {"from": from_addr, "to": [to_addr],
               "subject": subject, "text": body_text}
    if body_html:
        payload["html"] = body_html
    if reply_to:
        payload["reply_to"] = reply_to
    try:
        req = _req.Request(
            "https://api.resend.com/emails",
            data=_json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json",
                     "Accept": "application/json",
                     # Cloudflare (in front of api.resend.com) returns 403/1010
                     # for the default "Python-urllib" UA; identify ourselves.
                     "User-Agent": "Trakit365/1.0 (+https://trakit365.hagai.online)"})
        with _req.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def email_configured() -> bool:
    """True if any send transport is available (Resend HTTP or SMTP)."""
    return resend_configured() or smtp_configured()


def send_message(*, to_addr: str, subject: str, body_text: str,
                 reply_to: "str | None" = None,
                 body_html: "str | None" = None) -> bool:
    """Send a simple email, preferring the Resend HTTP API (works over 443) and
    falling back to SMTP. Returns True on success."""
    if resend_configured():
        return _send_via_resend(to_addr=to_addr, subject=subject,
                                body_text=body_text, reply_to=reply_to,
                                body_html=body_html)
    return send_email_with_attachment(to_addr=to_addr, subject=subject,
                                      body_text=body_text, reply_to=reply_to,
                                      body_html=body_html)
