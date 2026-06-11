"""In-app assistant — a help + live-data chatbot that knows how to use the ERP.

Backs the native **Assistant page** (Streamlit chat): ``answer(question,
snapshot)`` resolves a question against a built-in how-to knowledge base and a
live per-business data snapshot (``compute_snapshot``), entirely rule-based — no
API key required. ``launcher_html()`` renders a floating 💬 bubble (pure CSS +
anchor) that opens the page from anywhere.

Future API seam: when an LLM/data endpoint exists, call it inside ``answer`` and
fall back to the rule-based result for offline/cheap answers — no UI change.
"""
from __future__ import annotations

import re
from typing import Optional


# --------------------------------------------------------------------------- #
# Knowledge base — distilled how-to content (extend freely).                   #
# --------------------------------------------------------------------------- #
KB = [
    {"q": "log in sign in password", "tags": "login access account",
     "a": "Open the ERP in your browser and sign in with the username and password "
          "your administrator created. On first login you may be asked to change it."},
    {"q": "dashboard overview home metrics", "tags": "kpi revenue charts",
     "a": "The Dashboard (Overview group) shows revenue, costs, profit, cash, AR/AP "
          "aging and recent journals at a glance, computed live from your books."},
    {"q": "raise create invoice customer sales", "tags": "ar bill customer revenue",
     "a": "Go to Finance & Accounting → Sales, pick the customer, add line items, and "
          "post. It updates the customer balance, recognises revenue and books VAT "
          "automatically."},
    {"q": "record bill supplier purchase expense", "tags": "ap purchases vendor",
     "a": "Finance & Accounting → Purchases → Bills. Choose the supplier, add lines and "
          "Receive bill. It posts to the GL and (for stock items) increases inventory. "
          "If the amount is above your approval limit it's queued for approval first."},
    {"q": "make payment pay supplier money out", "tags": "ap payment bank cash",
     "a": "Purchases → Payments. Pick the supplier, optionally a bill, the bank and "
          "amount. Over-limit payments need approval before they post."},
    {"q": "purchase order po", "tags": "procurement commitment",
     "a": "Purchases → Purchase orders. POs are commitments (no GL impact) and also "
          "respect approval limits when over the threshold."},
    {"q": "approval limit approve reject pending authorise", "tags": "control limit sign-off",
     "a": "Money-out (bills, POs, payments) and payroll above a user's ROLE limit are "
          "blocked and sent to Finance & Accounting → Approvals. An approver whose limit "
          "covers the amount approves it (you can't approve your own). Admins set per-role "
          "limits on the Approvals → Limits tab."},
    {"q": "inventory stock products levels", "tags": "warehouse goods",
     "a": "Finance & Accounting → Inventory tracks stockable products, quantities and "
          "valuation. Buying/selling stock items moves inventory and posts cost of goods."},
    {"q": "banking receipts transfers cash", "tags": "bank money in",
     "a": "Finance & Accounting → Banking records receipts, payments and transfers "
          "against your bank and cash accounts."},
    {"q": "bank reconciliation match statement", "tags": "reconcile moniepoint",
     "a": "Finance & Accounting → Bank Reconciliation imports a statement, auto-matches "
          "what it can and lets you match the rest by hand (incl. a Moniepoint parser)."},
    {"q": "payroll run staff salary paye", "tags": "hr employees pay",
     "a": "HR → Payroll. Set the period, pick the bank, review each employee's gross and "
          "Run payroll — it computes graduated PAYE and pension and posts the entries. "
          "Large runs above your limit go through Approvals first."},
    {"q": "employee add staff directory people", "tags": "hr headcount",
     "a": "HR → Employees. Add staff with department, role, pay and leave entitlement; "
          "activate or deactivate them here."},
    {"q": "recruitment hiring job opening candidate", "tags": "hr ats interview",
     "a": "HR → Recruitment. Post openings, add candidates, move applications through the "
          "pipeline, and Hire — hiring creates an Employee so Payroll takes over."},
    {"q": "leave request approve balance holiday", "tags": "hr time off annual",
     "a": "HR → Leave. Staff request leave, managers approve/reject, and balances show "
          "annual entitlement minus approved annual days taken."},
    {"q": "crm leads pipeline deals follow up", "tags": "sales prospect customer",
     "a": "CRM manages leads, a deal pipeline and follow-up activities. Convert a won "
          "lead into a customer to invoice it from Sales."},
    {"q": "firs e-invoice tax irn qr", "tags": "compliance einvoice",
     "a": "Finance & Accounting → FIRS E-Invoice builds a FIRS-style payload from a sales "
          "invoice. These are drafts for review (CSID/QR are placeholders until FIRS "
          "countersigns). Set your TIN under Settings → Company."},
    {"q": "currency foreign exchange rate fx", "tags": "multi-currency naira",
     "a": "Finance & Accounting → Currencies. NGN is the functional currency; foreign "
          "invoices/bills convert to NGN at the captured rate, with a revaluation report "
          "for open items."},
    {"q": "budget variance plan", "tags": "forecast actual",
     "a": "Finance & Accounting → Budgets. Set budgets and compare to actuals with "
          "variance reporting."},
    {"q": "month end close period accruals", "tags": "closing fiscal",
     "a": "Finance & Accounting → Month-End helps close a period cleanly with accrual "
          "helpers; Admins can lock/reopen fiscal periods."},
    {"q": "reports profit loss balance sheet statements", "tags": "financials p&l bs",
     "a": "Finance & Accounting → Reports gives the Trial Balance, P&L, Balance Sheet, "
          "Cash Flow, agings and VAT — all computed from the journals."},
    {"q": "void reverse correct mistake delete", "tags": "adjust reversal",
     "a": "You don't delete posted documents — void or reverse them, which posts a "
          "reversing entry and keeps a clean audit trail."},
    {"q": "plans billing subscription upgrade free starter business", "tags": "tier pricing",
     "a": "System → Billing shows your plan and what it unlocks. Free = core accounting; "
          "Starter adds bank rec, recurring and FIRS drafts; Business adds multi-currency, "
          "CRM, budgets and the API. Upgrade there to unlock features."},
    {"q": "users roles permissions add user admin", "tags": "access security team",
     "a": "System → Admin manages users, roles and per-module permissions. Your plan caps "
          "the number of active users."},
    {"q": "backup restore recovery data safe", "tags": "disaster offsite",
     "a": "Backups run nightly: the database is dumped, encrypted and stored off-site. "
          "Restores are handled by HAG_Ai as part of operating the platform for you."},
    {"q": "api integration webhook key", "tags": "rest developer",
     "a": "The REST API + webhooks (Business plan) let other systems read/write your ERP "
          "data using a per-business API key issued by an admin."},
    {"q": "multiple businesses tenant switch company", "tags": "multi-tenant",
     "a": "System → Tenants lets you create or switch between businesses; each has its own "
          "isolated data and its own subscription."},
    {"q": "onboarding setup new company start", "tags": "getting started coa",
     "a": "System → Onboarding walks you through company details and loads a ready-made "
          "Chart of Accounts so you can start posting immediately."},
]

SUGGESTIONS = ["What's my revenue this month?", "How much cash do I have?",
               "How many pending approvals?", "How do I raise an invoice?",
               "Record a bill", "Run payroll"]

GREETING = ("Hi! I'm the Trakit365 assistant. Ask me how to use the ERP — e.g. "
            "\"How do I raise an invoice?\" — or about your numbers, like "
            "\"What's my revenue this month?\" or \"How many approvals are "
            "pending?\".")


def compute_snapshot(session) -> dict:
    """A light, live data snapshot for the active business. Embedded into the
    widget each run so the bot can answer data questions with rule-based
    matching. Defensive: any piece that fails is simply omitted/zeroed."""
    from datetime import date

    from sqlalchemy import select
    from .models import (BankAccount, Bill, Company, Customer, Employee,
                         Product, SalesInvoice, Supplier)
    from .services import reports, approvals
    from .services.banking import bank_balance

    def q(fn, default=0):
        try:
            return fn()
        except Exception:
            return default

    if not q(lambda: session.query(Company).first(), None):
        return {}

    today = date.today()
    month_start = today.replace(day=1)
    fy_start = date(today.year, 1, 1)
    pnl_mtd = q(lambda: reports.profit_and_loss(
        session, period_start=month_start, period_end=today), {}) or {}
    pnl_ytd = q(lambda: reports.profit_and_loss(
        session, period_start=fy_start, period_end=today), {}) or {}
    bs = q(lambda: reports.balance_sheet(session, as_of=today), {}) or {}

    cash = 0.0
    try:
        for b in session.execute(select(BankAccount).where(
                BankAccount.is_active == True)).scalars():  # noqa: E712
            cash += bank_balance(session, b.id) or 0.0
    except Exception:
        pass

    return {
        "as_of": today.strftime("%d %b %Y"),
        "revenue_mtd": round(pnl_mtd.get("total_revenue", 0) or 0, 2),
        "revenue_ytd": round(pnl_ytd.get("total_revenue", 0) or 0, 2),
        "net_profit_ytd": round(pnl_ytd.get("net_profit", 0) or 0, 2),
        "inventory_value": round(sum(
            r["amount"] for r in bs.get("assets", []) if r.get("code") == "1140"), 2),
        "cash": round(cash, 2),
        "ar_outstanding": round(sum(
            r["total"] for r in q(lambda: reports.ar_aging(session, as_of=today), [])), 2),
        "ap_outstanding": round(sum(
            r["total"] for r in q(lambda: reports.ap_aging(session, as_of=today), [])), 2),
        "customers": q(lambda: session.query(Customer).count()),
        "suppliers": q(lambda: session.query(Supplier).count()),
        "products": q(lambda: session.query(Product).count()),
        "employees": q(lambda: session.query(Employee).count()),
        "invoices": q(lambda: session.query(SalesInvoice).count()),
        "bills": q(lambda: session.query(Bill).count()),
        "pending_approvals": q(lambda: approvals.pending_count(session)),
    }


# --------------------------------------------------------------------------- #
# Answering (Python — used by the native Assistant page)                       #
# --------------------------------------------------------------------------- #

_STOP = {"how", "do", "i", "to", "the", "a", "an", "of", "and", "or", "is",
         "are", "my", "me", "you", "your", "can", "it", "on", "in", "for",
         "with", "what", "when", "much", "many"}


def _norm(s: str) -> list[str]:
    return [t for t in re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split()
            if t]


def _stem(t: str) -> str:
    return t[:-1] if len(t) > 3 and t.endswith("s") else t


def _kb_answer(q: str) -> str:
    qt = [_stem(t) for t in _norm(q)]
    best, best_score = None, 0
    for e in KB:
        hay = {_stem(t) for t in _norm(e["q"] + " " + e.get("tags", ""))}
        score = 0
        for t in qt:
            if t in _STOP:
                continue
            if t in hay:
                score += 2
            elif len(t) > 3 and any(t in h or h in t
                                    for h in hay if len(h) > 3):
                score += 1
        if score > best_score:
            best_score, best = score, e
    if best and best_score >= 2:
        return best["a"]
    return ("I can help with how to use the ERP — try: invoicing, recording a "
            "bill, payments & approvals, payroll, employees, leave, recruitment, "
            "CRM, bank reconciliation, reports, budgets, FIRS e-invoice, "
            "currencies, plans & billing, users & roles, or backups.")


def _fmt(n) -> str:
    return "₦{:,.0f}".format(round(n or 0))


def _data_answer(q: str, D: dict) -> Optional[str]:
    if not D or not D.get("as_of"):
        return None
    s = (q or "").lower()
    asof = " (as of {})".format(D["as_of"])

    def has(*ws) -> bool:
        return any(w in s for w in ws)

    if "approval" in s and ("pending" in s or "waiting" in s
                            or "awaiting" in s or "how many" in s):
        n = D.get("pending_approvals", 0)
        return ("There {} {} approval{} pending. See Finance & Accounting → "
                "Approvals.".format("is" if n == 1 else "are", n,
                                    "" if n == 1 else "s"))
    if has("profit", "net income", "bottom line"):
        return "Net profit year-to-date is {}{}.".format(
            _fmt(D.get("net_profit_ytd")), asof)
    if has("revenue", "sales", "turnover", "income", "earn"):
        if has("month", "mtd"):
            return "Revenue this month is {}{}.".format(
                _fmt(D.get("revenue_mtd")), asof)
        return "Revenue year-to-date is {} ({} this month){}.".format(
            _fmt(D.get("revenue_ytd")), _fmt(D.get("revenue_mtd")), asof)
    if has("cash", "bank balance", "in the bank", "money"):
        return "Cash & bank balance is {}{}.".format(_fmt(D.get("cash")), asof)
    if has("receivable", "owed to me", "customers owe", "outstanding invoice") \
            or re.search(r"\bar\b", s):
        return "Accounts receivable outstanding is {}{}.".format(
            _fmt(D.get("ar_outstanding")), asof)
    if has("payable", "i owe", "we owe", "owe supplier", "outstanding bill") \
            or re.search(r"\bap\b", s):
        return "Accounts payable outstanding is {}{}.".format(
            _fmt(D.get("ap_outstanding")), asof)
    if has("inventory", "stock value", "stock worth"):
        return "Inventory at cost is {}{}.".format(
            _fmt(D.get("inventory_value")), asof)
    if has("how many", "number of", "count of"):
        if has("customer"):
            return "You have {} customers.".format(D.get("customers", 0))
        if has("supplier", "vendor"):
            return "You have {} suppliers.".format(D.get("suppliers", 0))
        if has("product", "item", "sku"):
            return "You have {} products.".format(D.get("products", 0))
        if has("employee", "staff"):
            return "You have {} employees.".format(D.get("employees", 0))
        if has("invoice"):
            return "You have {} sales invoices.".format(D.get("invoices", 0))
        if has("bill"):
            return "You have {} bills.".format(D.get("bills", 0))
    return None


def answer(question: str, snapshot: Optional[dict] = None) -> str:
    """Rule-based answer: try the live-data snapshot first, then the how-to KB.

    (Future API seam: when an LLM/data endpoint exists, call it here and fall
    back to this for offline/cheap answers.)
    """
    da = _data_answer(question, snapshot or {})
    if da:
        return da
    return _kb_answer(question)


# --------------------------------------------------------------------------- #
# Floating launcher — pure CSS + anchor (no JS/iframe), links to the page       #
# --------------------------------------------------------------------------- #

def launcher_html(url_path: str = "assistant") -> str:
    """A floating 💬 bubble (bottom-right) that opens the Assistant page.

    Rendered via st.markdown(unsafe_allow_html=True) on every page — no
    JavaScript and no component iframe, so it renders reliably everywhere.
    """
    return (
        "<style>"
        ".bzk-fab{position:fixed;bottom:22px;right:22px;width:56px;height:56px;"
        "border-radius:50%;background:linear-gradient(135deg,#2be2c6,#16b39b);"
        "color:#06241f;display:flex;align-items:center;justify-content:center;"
        "font-size:26px;text-decoration:none;box-shadow:0 8px 24px rgba(0,0,0,.4);"
        "z-index:99999;transition:transform .15s;}"
        ".bzk-fab:hover{transform:scale(1.07);}"
        "</style>"
        f'<a class="bzk-fab" href="{url_path}" target="_self" '
        'title="Trakit365 Assistant">&#128172;</a>'
    )

