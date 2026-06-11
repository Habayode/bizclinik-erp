"""Floating in-app assistant — a help chatbot that knows how to use the ERP.

Renders a floating chat bubble (bottom-right) on every page. It answers
"how do I…" questions from a built-in knowledge base (client-side retrieval
over distilled manual/FAQ content) — no API key required.

Architecture for "feed on data later": the widget calls ``answer(q)`` which
first tries ``window.__bzkAskBackend(q)`` if a backend has been registered
(returns a Promise or null). Wire a server endpoint there to return
data-grounded answers (e.g. "revenue this month", "pending approvals") and the
bubble upgrades from a help bot to a data assistant with no UI change.

The widget is injected into the parent document (so it floats over the whole
app and survives Streamlit reruns) and guarded against double-injection.
"""
from __future__ import annotations

import json

import streamlit.components.v1 as components


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


def _css() -> str:
    return """
#bzk-asst-btn{position:fixed;bottom:22px;right:22px;width:58px;height:58px;border:none;
 border-radius:50%;cursor:pointer;z-index:99999;font-size:26px;color:#06241f;
 background:linear-gradient(135deg,#2be2c6,#16b39b);box-shadow:0 8px 24px rgba(0,0,0,.4);
 display:flex;align-items:center;justify-content:center;transition:transform .15s;}
#bzk-asst-btn:hover{transform:scale(1.06);}
#bzk-asst-panel{position:fixed;bottom:92px;right:22px;width:374px;max-height:72vh;
 background:#0d1326;border:1px solid #24304d;border-radius:16px;z-index:99999;
 box-shadow:0 18px 50px rgba(0,0,0,.5);display:none;flex-direction:column;overflow:hidden;
 font-family:'Segoe UI',Calibri,Arial,sans-serif;}
#bzk-asst.bzk-open #bzk-asst-panel{display:flex;}
#bzk-asst-hd{padding:14px 16px;background:#101a30;border-bottom:1px solid #24304d;
 display:flex;align-items:center;justify-content:space-between;}
#bzk-asst-hd b{color:#fff;font-size:15px;}
#bzk-asst-hd span{color:#2be2c6;font-size:12px;}
#bzk-asst-x{cursor:pointer;color:#8aa;background:none;border:none;font-size:18px;}
#bzk-asst-msgs{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;}
.bzk-m{max-width:84%;padding:9px 12px;border-radius:12px;font-size:13.5px;line-height:1.45;
 white-space:pre-wrap;}
.bzk-m.bot{align-self:flex-start;background:#16203a;color:#dfe6f2;border:1px solid #243152;}
.bzk-m.user{align-self:flex-end;background:#15473f;color:#d6fff6;}
#bzk-asst-chips{display:flex;flex-wrap:wrap;gap:6px;padding:0 14px 8px;}
.bzk-chip{font-size:12px;color:#2be2c6;border:1px solid #2be2c6;border-radius:14px;
 padding:4px 10px;cursor:pointer;background:transparent;}
.bzk-chip:hover{background:rgba(43,226,198,.12);}
#bzk-asst-in{display:flex;gap:8px;padding:10px;border-top:1px solid #24304d;}
#bzk-asst-in textarea{flex:1;resize:none;height:38px;background:#0a1120;color:#fff;
 border:1px solid #24304d;border-radius:10px;padding:8px 10px;font-size:13.5px;font-family:inherit;}
#bzk-asst-in button{background:#2be2c6;color:#06241f;border:none;border-radius:10px;
 padding:0 14px;font-weight:700;cursor:pointer;}
"""


def _js() -> str:
    return (
        "var KB=" + json.dumps(KB) + ";\n"
        "var SUG=" + json.dumps(SUGGESTIONS) + ";\n"
        "var GREET=" + json.dumps(GREETING) + ";\n"
        + r"""
var STOP=new Set("how do i to the a an of and or is are my me you your can it on in for with what when".split(" "));
function norm(s){return (s||"").toLowerCase().replace(/[^a-z0-9 ]/g," ").split(/\s+/).filter(Boolean);}
function score(qt,e){var hay=new Set(norm(e.q+" "+(e.tags||"")));var s=0;
  qt.forEach(function(t){if(STOP.has(t))return; if(hay.has(t)){s+=2;return;}
    hay.forEach(function(h){if(t.length>3&&(h.indexOf(t)>=0||t.indexOf(h)>=0))s+=1;});});
  return s;}
function localAnswer(q){var qt=norm(q),best=null,bs=0;
  KB.forEach(function(e){var s=score(qt,e); if(s>bs){bs=s;best=e;}});
  if(best&&bs>=2) return best.a;
  return "I can help with how to use the ERP — try: invoicing, recording a bill, payments & approvals, payroll, employees, leave, recruitment, CRM, bank reconciliation, reports, budgets, FIRS e-invoice, currencies, plans & billing, users & roles, or backups.";}
function fmtN(n){return "₦"+Math.round(n||0).toLocaleString();}
function dataAnswer(q){
  var D=window.__bzkData||{}; if(!D||!D.as_of) return null;
  var s=q.toLowerCase(); var asof=" (as of "+D.as_of+")";
  function has(){for(var i=0;i<arguments.length;i++){if(s.indexOf(arguments[i])>=0)return true;}return false;}
  if(has("pending approval","approvals pending","awaiting approval","to approve","approvals waiting"))
    return "There "+(D.pending_approvals===1?"is ":"are ")+D.pending_approvals+" approval"+(D.pending_approvals===1?"":"s")+" pending. See Finance & Accounting → Approvals.";
  if(has("profit","net income","bottom line","made this year"))
    return "Net profit year-to-date is "+fmtN(D.net_profit_ytd)+asof+".";
  if(has("revenue","sales","turnover","income","earn")){
    if(has("month","mtd")) return "Revenue this month is "+fmtN(D.revenue_mtd)+asof+".";
    return "Revenue year-to-date is "+fmtN(D.revenue_ytd)+" ("+fmtN(D.revenue_mtd)+" this month)"+asof+".";
  }
  if(has("cash","bank balance","in the bank","how much money"))
    return "Cash & bank balance is "+fmtN(D.cash)+asof+".";
  if(has("receivable","owed to me","customers owe","outstanding invoice")|| /\bar\b/.test(s))
    return "Accounts receivable outstanding is "+fmtN(D.ar_outstanding)+asof+".";
  if(has("payable","i owe","we owe","owe supplier","outstanding bill")|| /\bap\b/.test(s))
    return "Accounts payable outstanding is "+fmtN(D.ap_outstanding)+asof+".";
  if(has("inventory","stock value","stock worth"))
    return "Inventory at cost is "+fmtN(D.inventory_value)+asof+".";
  if(has("how many","number of","count of","total ")){
    if(has("customer")) return "You have "+D.customers+" customers.";
    if(has("supplier","vendor")) return "You have "+D.suppliers+" suppliers.";
    if(has("product","item","sku")) return "You have "+D.products+" products.";
    if(has("employee","staff")) return "You have "+D.employees+" employees.";
    if(has("invoice")) return "You have "+D.invoices+" sales invoices.";
    if(has("bill")) return "You have "+D.bills+" bills.";
  }
  return null;
}
function answer(q){
  // 1) Future API: if a backend is registered, prefer it (Promise<string>|null).
  try{ if(window.__bzkAskBackend){ var r=window.__bzkAskBackend(q);
    if(r&&typeof r.then==="function") return r.then(function(a){return a||dataAnswer(q)||localAnswer(q);});
    if(r) return Promise.resolve(r); } }catch(e){}
  // 2) Rule-based data answer from the live snapshot.
  var da=dataAnswer(q); if(da) return Promise.resolve(da);
  // 3) Built-in how-to help.
  return Promise.resolve(localAnswer(q));
}
var KEY="bzkAsstMsgs";
function load(){try{var m=JSON.parse(localStorage.getItem(KEY));if(m&&m.length)return m;}catch(e){}
  return [{r:"bot",t:GREET}];}
function save(m){try{localStorage.setItem(KEY,JSON.stringify(m.slice(-40)));}catch(e){}}
var msgs=load();
var root=document.createElement("div");root.id="bzk-asst";
root.innerHTML=
 '<button id="bzk-asst-btn" title="Assistant">&#128172;</button>'+
 '<div id="bzk-asst-panel">'+
  '<div id="bzk-asst-hd"><div><b>Trakit365 Assistant</b><br><span>How-to help</span></div>'+
   '<button id="bzk-asst-x">&times;</button></div>'+
  '<div id="bzk-asst-msgs"></div>'+
  '<div id="bzk-asst-chips"></div>'+
  '<div id="bzk-asst-in"><textarea placeholder="Ask how to do something..."></textarea>'+
   '<button id="bzk-asst-send">Send</button></div>'+
 '</div>';
document.body.appendChild(root);
var msgsEl=root.querySelector("#bzk-asst-msgs");
var chipsEl=root.querySelector("#bzk-asst-chips");
var ta=root.querySelector("#bzk-asst-in textarea");
function render(){msgsEl.innerHTML="";msgs.forEach(function(m){var d=document.createElement("div");
  d.className="bzk-m "+(m.r==="user"?"user":"bot");d.textContent=m.t;msgsEl.appendChild(d);});
  msgsEl.scrollTop=msgsEl.scrollHeight;}
function add(r,t){msgs.push({r:r,t:t});save(msgs);render();}
function send(q){q=(q||ta.value).trim();if(!q)return;ta.value="";add("user",q);
  add("bot","…");
  answer(q).then(function(a){msgs.pop();add("bot",a);});}
SUG.forEach(function(s){var c=document.createElement("button");c.className="bzk-chip";
  c.textContent=s;c.onclick=function(){send(s);};chipsEl.appendChild(c);});
root.querySelector("#bzk-asst-btn").onclick=function(){root.classList.toggle("bzk-open");render();};
root.querySelector("#bzk-asst-x").onclick=function(){root.classList.remove("bzk-open");};
root.querySelector("#bzk-asst-send").onclick=function(){send();};
ta.addEventListener("keydown",function(e){if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send();}});
render();
"""
    )


def render_floating_widget(snapshot: dict | None = None) -> None:
    """Inject the floating assistant into the parent document.

    The data snapshot is refreshed on every run (so the bot's data answers stay
    current), while the widget DOM + listeners are injected only once.
    """
    boot = (
        "<script>(function(){var w=window.parent,d=w.document;"
        "w.__bzkData=" + json.dumps(snapshot or {}) + ";"   # refresh every run
        "if(w.__bzkAsst)return;w.__bzkAsst=true;"
        "var css=" + json.dumps(_css()) + ";"
        "var js=" + json.dumps(_js()) + ";"
        "var s=d.createElement('style');s.textContent=css;d.head.appendChild(s);"
        "var sc=d.createElement('script');sc.textContent=js;d.body.appendChild(sc);"
        "})();</script>"
    )
    components.html(boot, height=0)
