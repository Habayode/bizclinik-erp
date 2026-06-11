"""Trakit365 ERP — REST API (FastAPI).

A SEPARATE application from the Streamlit UI. It reuses the exact same domain
services and SQLite system-of-record via ``bizclinik_erp.db.get_session`` —
there is no second source of truth. Runs on its own port (8600) as its own
systemd service (deploy/linux/bizclinik-api.service).

Auth: every request under ``/api`` must present a valid ``X-API-Key`` header.
Keys are resolved in this order:
  1. The legacy env var ``BIZCLINIK_API_KEY`` -> the default/legacy database.
  2. A per-tenant key created in the control plane -> that tenant's database.
A matching key sets the active database for the duration of the request, so
every endpoint reads/writes the correct tenant in isolation. No match -> 401.

All DB access goes through ``with get_session() as s:`` so commits/rollbacks
follow the same transactional discipline as the rest of the codebase. Service
``ValueError``s (e.g. unknown customer, unbalanced JE) surface as HTTP 400.
"""
from __future__ import annotations

import hmac
import os
from datetime import date
from typing import Iterator, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from bizclinik_erp import db as _db
from bizclinik_erp import tenancy
from bizclinik_erp.db import get_session
from bizclinik_erp.models import (
    Customer,
    DocStatus,
    Product,
    SalesInvoice,
)
from bizclinik_erp.services import reports as reports_svc
from bizclinik_erp.services import sales as sales_svc
from bizclinik_erp.services.ledger import trial_balance
from bizclinik_erp.services.sales import LineInput

from . import webhooks

try:
    from bizclinik_erp.observability import init_sentry
    init_sentry("api")
except Exception:
    pass

app = FastAPI(
    title="Trakit365 ERP API",
    version="1.1",
    description="REST + webhooks layer over the Trakit365 ERP services "
                "(per-tenant API keys).",
)


# ---- auth (tenant-aware) ----------------------------------------------------


async def require_api_key(x_api_key: Optional[str] = Header(default=None)):
    """Async generator dependency: authenticate the key, bind the request to
    the right tenant database, and reset the binding afterwards.

    Async (and the endpoints are async) so the dependency + endpoint share one
    asyncio task context — that's what makes the active-DB contextvar
    propagate correctly. Yields {"tenant": <slug|None>}.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    tenant_slug: Optional[str] = None
    matched = False

    env_key = os.environ.get("BIZCLINIK_API_KEY")
    if env_key and hmac.compare_digest(x_api_key, env_key):
        matched = True
        tenant_slug = None  # legacy / default DB
    else:
        res = tenancy.resolve_api_key(x_api_key)
        if res:
            matched = True
            tenant_slug = res.get("tenant_slug")

    if not matched:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    db_path = None
    if tenant_slug:
        t = tenancy.get_tenant(tenant_slug)
        if not t or not t["is_active"]:
            raise HTTPException(status_code=403, detail="Tenant inactive")
        db_path = t["db_path"]

        # Plan gate: the REST/webhook API is a Business-tier entitlement.
        from bizclinik_erp.services import billing
        if not billing.allows(tenant_slug, "api"):
            raise HTTPException(
                status_code=402,
                detail="API access requires the Business plan. Upgrade on the "
                       "Billing page to use the REST API.")

    token = _db._active_db_path.set(db_path)
    try:
        yield {"tenant": tenant_slug}
    finally:
        _db._active_db_path.reset(token)


# ---- request / response schemas --------------------------------------------


class CustomerOut(BaseModel):
    code: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    credit_limit: float = 0.0
    is_active: bool = True


class ProductOut(BaseModel):
    sku: str
    name: str
    unit: str = "ea"
    standard_price: float = 0.0
    qty_on_hand: float = 0.0
    is_active: bool = True


class InvoiceLineOut(BaseModel):
    sku: Optional[str] = None
    description: str
    qty: float
    unit_price: float
    tax_rate: float
    subtotal: float
    tax_amount: float


class InvoiceSummaryOut(BaseModel):
    number: str
    customer: str
    invoice_date: str
    total: float
    outstanding: float
    status: str


class InvoiceDetailOut(InvoiceSummaryOut):
    due_date: Optional[str] = None
    subtotal: float
    tax_total: float
    amount_paid: float
    lines: list[InvoiceLineOut]


class InvoiceLineIn(BaseModel):
    sku: Optional[str] = None
    description: Optional[str] = None
    qty: float
    unit_price: float
    tax_rate: float = 0.0


class InvoiceCreateIn(BaseModel):
    customer_code: str
    invoice_date: date
    due_date: Optional[date] = None
    lines: list[InvoiceLineIn] = Field(..., min_length=1)


# ---- serializers ------------------------------------------------------------


def _invoice_summary(inv: SalesInvoice) -> dict:
    return {
        "number": inv.number,
        "customer": inv.customer.name if inv.customer else "",
        "invoice_date": inv.invoice_date.isoformat(),
        "total": inv.grand_total,
        "outstanding": inv.outstanding,
        "status": inv.status.value,
    }


def _invoice_detail(inv: SalesInvoice, session) -> dict:
    # Map product_id -> sku for line output without extra round trips per line.
    sku_by_pid: dict[int, str] = {}
    for line in inv.lines:
        if line.product_id and line.product_id not in sku_by_pid:
            prod = session.get(Product, line.product_id)
            if prod:
                sku_by_pid[line.product_id] = prod.sku
    out = _invoice_summary(inv)
    out.update({
        "due_date": inv.due_date.isoformat() if inv.due_date else None,
        "subtotal": inv.subtotal,
        "tax_total": inv.tax_total,
        "amount_paid": inv.amount_paid,
        "lines": [
            {
                "sku": sku_by_pid.get(line.product_id),
                "description": line.description,
                "qty": line.qty,
                "unit_price": line.unit_price,
                "tax_rate": line.tax_rate,
                "subtotal": line.subtotal,
                "tax_amount": line.tax_amount,
            }
            for line in inv.lines
        ],
    })
    return out


# ---- health (no auth) -------------------------------------------------------


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/whoami")
async def whoami(ctx: dict = Depends(require_api_key)) -> dict:
    """Returns which tenant the presented key is bound to (None = default)."""
    return {"tenant": ctx.get("tenant")}


# ---- master data ------------------------------------------------------------


@app.get("/api/v1/customers", dependencies=[Depends(require_api_key)])
async def list_customers() -> list[CustomerOut]:
    with get_session() as s:
        rows = s.execute(select(Customer).order_by(Customer.code)).scalars().all()
        return [
            CustomerOut(
                code=c.code, name=c.name, email=c.email, phone=c.phone,
                credit_limit=c.credit_limit, is_active=c.is_active,
            )
            for c in rows
        ]


@app.get("/api/v1/products", dependencies=[Depends(require_api_key)])
async def list_products() -> list[ProductOut]:
    with get_session() as s:
        rows = s.execute(select(Product).order_by(Product.sku)).scalars().all()
        return [
            ProductOut(
                sku=p.sku, name=p.name, unit=p.unit,
                standard_price=p.standard_price, qty_on_hand=p.qty_on_hand,
                is_active=p.is_active,
            )
            for p in rows
        ]


# ---- invoices ---------------------------------------------------------------


@app.get("/api/v1/invoices", dependencies=[Depends(require_api_key)])
async def list_invoices() -> list[InvoiceSummaryOut]:
    with get_session() as s:
        rows = s.execute(
            select(SalesInvoice).order_by(SalesInvoice.id)
        ).scalars().all()
        return [InvoiceSummaryOut(**_invoice_summary(inv)) for inv in rows]


@app.get("/api/v1/invoices/{number}", dependencies=[Depends(require_api_key)])
async def get_invoice(number: str) -> InvoiceDetailOut:
    with get_session() as s:
        inv = s.execute(
            select(SalesInvoice).where(SalesInvoice.number == number)
        ).scalar_one_or_none()
        if not inv:
            raise HTTPException(status_code=404, detail=f"Invoice {number} not found")
        return InvoiceDetailOut(**_invoice_detail(inv, s))


@app.post("/api/v1/invoices", status_code=201,
          dependencies=[Depends(require_api_key)])
async def create_invoice(payload: InvoiceCreateIn) -> InvoiceDetailOut:
    with get_session() as s:
        customer = s.execute(
            select(Customer).where(Customer.code == payload.customer_code)
        ).scalar_one_or_none()
        if not customer:
            raise HTTPException(
                status_code=400,
                detail=f"Customer {payload.customer_code} not found",
            )

        line_inputs: list[LineInput] = []
        for line in payload.lines:
            product_id: Optional[int] = None
            description = line.description
            if line.sku:
                prod = s.execute(
                    select(Product).where(Product.sku == line.sku)
                ).scalar_one_or_none()
                if not prod:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Product {line.sku} not found",
                    )
                product_id = prod.id
                if not description:
                    description = prod.name
            if not description:
                raise HTTPException(
                    status_code=400,
                    detail="Each line needs a sku or a description",
                )
            line_inputs.append(LineInput(
                product_id=product_id, description=description,
                qty=line.qty, unit_price=line.unit_price, tax_rate=line.tax_rate,
            ))

        try:
            invoice = sales_svc.issue_invoice(
                s,
                customer_id=customer.id,
                invoice_date=payload.invoice_date,
                lines=line_inputs,
                due_date=payload.due_date,
            )
            detail = _invoice_detail(invoice, s)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Fire AFTER the session commits so subscribers see a persisted invoice.
    webhooks.emit_invoice_created(detail)
    return InvoiceDetailOut(**detail)


# ---- bank feed (bank/aggregator -> ERP) -------------------------------------


class BankStatementLineIn(BaseModel):
    txn_date: date
    description: str = ""
    amount: float = Field(..., description="Signed: +credit / -debit")
    reference: Optional[str] = None


class BankStatementIn(BaseModel):
    bank_account_id: int
    period_start: date
    period_end: date
    opening_balance: float = 0.0
    closing_balance: float = 0.0
    source: str = "bank-feed"
    auto_match: bool = True
    lines: list[BankStatementLineIn] = Field(default_factory=list)
    csv: Optional[str] = Field(
        default=None,
        description="Raw CSV from the bank, parsed server-side. Alternative to 'lines'.",
    )


@app.post("/api/v1/bank/statements", status_code=201,
          dependencies=[Depends(require_api_key)])
async def ingest_bank_statement(payload: BankStatementIn) -> dict:
    """Link a bank statement straight into reconciliation from the bank side.

    A bank, an open-banking aggregator (Mono/Okra), or a Moniepoint export can
    POST a statement here: either structured ``lines`` or a raw ``csv`` blob
    (parsed by the bank-agnostic parser). We create the statement, import the
    lines, optionally auto-match against the GL, and return a reconciliation
    summary. This is the inbound counterpart to manual CSV upload in the UI.
    """
    from bizclinik_erp.services import recon
    from bizclinik_erp.importers.bank_statement import parse_bank_statement

    if payload.csv:
        rows = parse_bank_statement(payload.csv)
    else:
        rows = [{"txn_date": ln.txn_date, "description": ln.description,
                 "amount": ln.amount, "reference": ln.reference}
                for ln in payload.lines]
    if not rows:
        raise HTTPException(status_code=400,
                            detail="Provide a non-empty 'lines' array or a 'csv' blob.")

    with get_session() as s:
        try:
            stmt = recon.create_statement(
                s, bank_account_id=payload.bank_account_id,
                period_start=payload.period_start, period_end=payload.period_end,
                opening_balance=payload.opening_balance,
                closing_balance=payload.closing_balance,
                source_file=payload.source,
            )
            imported = recon.import_statement_lines(s, stmt.id, rows)
            matched = recon.auto_match(s, stmt.id) if payload.auto_match else {}
            summary = recon.reconciliation_summary(s, stmt.id)
            sid = stmt.id
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"statement_id": sid, "lines_imported": imported,
            "auto_match": matched, "summary": summary}


# ---- customer statement email ----------------------------------------------


class StatementEmailIn(BaseModel):
    customer_code: str
    period_start: date
    period_end: date
    to_addr: Optional[str] = None


@app.post("/api/v1/customers/statement/email",
          dependencies=[Depends(require_api_key)])
async def email_customer_statement(payload: StatementEmailIn) -> dict:
    """Render a customer's statement PDF and email it (to the address on file,
    or an override). Returns whether it sent and why not, if applicable."""
    from bizclinik_erp.services.customer_statement import email_statement
    with get_session() as s:
        cust = s.execute(
            select(Customer).where(Customer.code == payload.customer_code)
        ).scalar_one_or_none()
        if not cust:
            raise HTTPException(status_code=404,
                                detail=f"Customer {payload.customer_code} not found")
        res = email_statement(s, cust.id, period_start=payload.period_start,
                              period_end=payload.period_end, to_addr=payload.to_addr)
    return res


# ---- billing / subscriptions ------------------------------------------------


class SubscribeIn(BaseModel):
    tenant_slug: str
    plan_code: str
    email: str
    callback_url: Optional[str] = None


@app.get("/api/v1/billing/plans", dependencies=[Depends(require_api_key)])
async def billing_plans() -> dict:
    from bizclinik_erp.services import billing
    return {"plans": billing.list_plans()}


@app.get("/api/v1/billing/status", dependencies=[Depends(require_api_key)])
async def billing_status(tenant_slug: str) -> dict:
    from bizclinik_erp.services import billing
    sub = billing.current_subscription(tenant_slug)
    return sub or {"tenant_slug": tenant_slug, "status": "none", "is_active": False}


@app.post("/api/v1/billing/subscribe", status_code=201,
          dependencies=[Depends(require_api_key)])
async def billing_subscribe(payload: SubscribeIn) -> dict:
    from bizclinik_erp.services import billing
    try:
        return billing.start_subscription(
            payload.tenant_slug, payload.plan_code, email=payload.email,
            callback_url=payload.callback_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/v1/billing/webhook/{provider}")
async def billing_webhook(provider: str, request: Request) -> dict:
    """Provider payment webhook (no API key — verified by provider signature)."""
    from bizclinik_erp.services import billing
    body = await request.body()
    h = request.headers
    signature = (h.get("x-paystack-signature") or h.get("verif-hash")
                 or h.get("x-moniepoint-signature") or h.get("x-signature") or "")
    out = billing.handle_webhook(provider, body, signature)
    if not out.get("verified"):
        raise HTTPException(status_code=401, detail="Webhook signature invalid")
    return out


# ---- CRM --------------------------------------------------------------------


class LeadIn(BaseModel):
    name: str
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None


@app.get("/api/v1/crm/pipeline", dependencies=[Depends(require_api_key)])
async def crm_pipeline() -> dict:
    from bizclinik_erp.services import crm
    with get_session() as s:
        return crm.pipeline_summary(s)


@app.get("/api/v1/crm/leads", dependencies=[Depends(require_api_key)])
async def crm_list_leads() -> dict:
    from bizclinik_erp.services import crm
    with get_session() as s:
        leads = crm.list_leads(s)
        return {"leads": [{"id": l.id, "name": l.name, "company": l.company,
                           "email": l.email, "status": l.status.value,
                           "customer_id": l.customer_id} for l in leads]}


@app.post("/api/v1/crm/leads", status_code=201,
          dependencies=[Depends(require_api_key)])
async def crm_create_lead(payload: LeadIn) -> dict:
    from bizclinik_erp.services import crm
    with get_session() as s:
        try:
            lead = crm.create_lead(s, name=payload.name, company=payload.company,
                                   email=payload.email, phone=payload.phone,
                                   source=payload.source, notes=payload.notes)
            return {"id": lead.id, "status": lead.status.value}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/crm/leads/{lead_id}/convert",
          dependencies=[Depends(require_api_key)])
async def crm_convert_lead(lead_id: int, create_deal: bool = False,
                           deal_amount: float = 0.0) -> dict:
    from bizclinik_erp.services import crm
    with get_session() as s:
        try:
            return crm.convert_lead(s, lead_id, create_deal=create_deal,
                                    deal_amount=deal_amount)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---- reports ----------------------------------------------------------------


@app.get("/api/v1/reports/trial-balance", dependencies=[Depends(require_api_key)])
async def report_trial_balance(as_of: Optional[date] = None) -> dict:
    with get_session() as s:
        rows = trial_balance(s, as_of=as_of)
    total_debit = round(sum(r["debit"] for r in rows), 2)
    total_credit = round(sum(r["credit"] for r in rows), 2)
    return {
        "as_of": as_of.isoformat() if as_of else None,
        "rows": rows,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "balanced": abs(total_debit - total_credit) < 0.01,
    }


@app.get("/api/v1/reports/pnl", dependencies=[Depends(require_api_key)])
async def report_pnl(
    from_: date = Query(..., alias="from"),
    to: date = Query(...),
) -> dict:
    with get_session() as s:
        try:
            return reports_svc.profit_and_loss(s, period_start=from_, period_end=to)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/reports/balance-sheet", dependencies=[Depends(require_api_key)])
async def report_balance_sheet(as_of: date = Query(...)) -> dict:
    with get_session() as s:
        try:
            return reports_svc.balance_sheet(s, as_of=as_of)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
