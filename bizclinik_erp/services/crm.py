"""CRM service — leads, deals (pipeline), activities, and lead→customer convert.

Sits in front of the ledger: capture leads, push deals through pipeline stages,
log follow-up activities, and convert a won/qualified lead into a real Customer
so invoicing + statements take over. All numbers/states are plain rows in the
tenant DB; nothing here touches the GL.
"""
from __future__ import annotations
from ..money import msum

from datetime import date, datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import authz
from ..models import (
    Activity, ActivityKind, Customer, Deal, DealStage, Lead, LeadStatus,
)
from ..models.crm import CLOSED_STAGES, OPEN_STAGES


def _now() -> datetime:
    return datetime.utcnow()


# --------------------------------------------------------------------------- #
# Leads                                                                        #
# --------------------------------------------------------------------------- #

def create_lead(session: Session, *, name: str, company: Optional[str] = None,
                email: Optional[str] = None, phone: Optional[str] = None,
                source: Optional[str] = None, owner_user_id: Optional[int] = None,
                notes: Optional[str] = None) -> Lead:
    authz.require_perm("manage.customers")
    if not (name or "").strip():
        raise ValueError("Lead name is required.")
    lead = Lead(name=name.strip(), company=(company or None), email=(email or None),
                phone=(phone or None), source=(source or None),
                owner_user_id=owner_user_id, notes=(notes or None),
                status=LeadStatus.NEW)
    session.add(lead)
    session.flush()
    return lead


def list_leads(session: Session, *, status: Optional[LeadStatus] = None) -> list[Lead]:
    q = select(Lead).order_by(Lead.created_at.desc())
    if status is not None:
        q = q.where(Lead.status == status)
    return list(session.execute(q).scalars())


def set_lead_status(session: Session, lead_id: int, status: LeadStatus) -> Lead:
    lead = session.get(Lead, lead_id)
    if not lead:
        raise ValueError(f"Lead {lead_id} not found.")
    lead.status = status
    lead.updated_at = _now()
    session.flush()
    return lead


def _unique_customer_code(session: Session, name: str) -> str:
    base = "".join(ch for ch in (name or "C").upper() if ch.isalnum())[:6] or "CUST"
    code, i = base, 1
    while session.execute(select(Customer).where(Customer.code == code)
                          ).scalar_one_or_none() is not None:
        i += 1
        code = f"{base}{i}"
    return code


def convert_lead(session: Session, lead_id: int, *,
                 create_deal: bool = False, deal_amount: float = 0.0) -> dict:
    """Turn a lead into a real Customer (idempotent on the lead's link).

    Optionally opens a Deal for the new customer. Returns
    ``{"customer_id", "lead_id", "deal_id"|None}``.
    """
    authz.require_perm("manage.customers")
    lead = session.get(Lead, lead_id)
    if not lead:
        raise ValueError(f"Lead {lead_id} not found.")

    if lead.customer_id:
        customer = session.get(Customer, lead.customer_id)
    else:
        customer = Customer(
            code=_unique_customer_code(session, lead.company or lead.name),
            name=lead.company or lead.name, email=lead.email, phone=lead.phone)
        session.add(customer)
        session.flush()
        lead.customer_id = customer.id

    lead.status = LeadStatus.CONVERTED
    lead.updated_at = _now()

    deal_id = None
    if create_deal:
        deal = Deal(title=f"{customer.name} — opportunity", lead_id=lead.id,
                    customer_id=customer.id, stage=DealStage.QUALIFIED,
                    amount=round(float(deal_amount or 0.0), 2),
                    owner_user_id=lead.owner_user_id)
        session.add(deal)
        session.flush()
        deal_id = deal.id

    session.flush()
    return {"customer_id": customer.id, "lead_id": lead.id, "deal_id": deal_id}


# --------------------------------------------------------------------------- #
# Deals / pipeline                                                             #
# --------------------------------------------------------------------------- #

def create_deal(session: Session, *, title: str, amount: float = 0.0,
                customer_id: Optional[int] = None, lead_id: Optional[int] = None,
                stage: DealStage = DealStage.LEAD, currency_code: str = "NGN",
                expected_close: Optional[date] = None,
                owner_user_id: Optional[int] = None,
                notes: Optional[str] = None) -> Deal:
    if not (title or "").strip():
        raise ValueError("Deal title is required.")
    deal = Deal(title=title.strip(), amount=round(float(amount or 0.0), 2),
                customer_id=customer_id, lead_id=lead_id, stage=stage,
                currency_code=(currency_code or "NGN").upper(),
                expected_close=expected_close, owner_user_id=owner_user_id,
                notes=(notes or None))
    if stage in CLOSED_STAGES:
        deal.closed_at = _now()
    session.add(deal)
    session.flush()
    return deal


def move_stage(session: Session, deal_id: int, stage: DealStage) -> Deal:
    deal = session.get(Deal, deal_id)
    if not deal:
        raise ValueError(f"Deal {deal_id} not found.")
    deal.stage = stage
    deal.updated_at = _now()
    deal.closed_at = _now() if stage in CLOSED_STAGES else None
    session.flush()
    return deal


def list_deals(session: Session, *, open_only: bool = False) -> list[Deal]:
    q = select(Deal).order_by(Deal.updated_at.desc())
    if open_only:
        q = q.where(Deal.stage.in_(OPEN_STAGES))
    return list(session.execute(q).scalars())


def pipeline_summary(session: Session) -> dict:
    """Per-stage count + value, plus open pipeline value and win rate."""
    rows = session.execute(
        select(Deal.stage, func.count(Deal.id), func.coalesce(func.sum(Deal.amount), 0.0))
        .group_by(Deal.stage)
    ).all()
    by_stage = {st.value: {"count": 0, "value": 0.0} for st in DealStage}
    for stage, count, value in rows:
        key = stage.value if hasattr(stage, "value") else str(stage)
        by_stage[key] = {"count": int(count), "value": round(float(value), 2)}

    open_value = msum(by_stage[s.value]["value"] for s in OPEN_STAGES)
    won = by_stage[DealStage.WON.value]["count"]
    lost = by_stage[DealStage.LOST.value]["count"]
    closed = won + lost
    win_rate = round(won / closed, 4) if closed else 0.0
    return {
        "by_stage": by_stage,
        "open_value": open_value,
        "won_value": by_stage[DealStage.WON.value]["value"],
        "win_rate": win_rate,
        "open_count": sum(by_stage[s.value]["count"] for s in OPEN_STAGES),
    }


# --------------------------------------------------------------------------- #
# Activities / follow-ups                                                      #
# --------------------------------------------------------------------------- #

def log_activity(session: Session, *, subject: str,
                 kind: ActivityKind = ActivityKind.TASK,
                 due_date: Optional[date] = None,
                 lead_id: Optional[int] = None, deal_id: Optional[int] = None,
                 customer_id: Optional[int] = None,
                 owner_user_id: Optional[int] = None,
                 notes: Optional[str] = None) -> Activity:
    if not (subject or "").strip():
        raise ValueError("Activity subject is required.")
    act = Activity(subject=subject.strip(), kind=kind, due_date=due_date,
                   lead_id=lead_id, deal_id=deal_id, customer_id=customer_id,
                   owner_user_id=owner_user_id, notes=(notes or None))
    session.add(act)
    session.flush()
    return act


def complete_activity(session: Session, activity_id: int) -> Activity:
    act = session.get(Activity, activity_id)
    if not act:
        raise ValueError(f"Activity {activity_id} not found.")
    act.done = True
    act.done_at = _now()
    session.flush()
    return act


def list_activities(session: Session, *, open_only: bool = True,
                    as_of: Optional[date] = None) -> list[Activity]:
    q = select(Activity).order_by(Activity.due_date.is_(None),
                                  Activity.due_date.asc(), Activity.id.desc())
    if open_only:
        q = q.where(Activity.done == False)  # noqa: E712
    return list(session.execute(q).scalars())


def followups_due(session: Session, *, as_of: Optional[date] = None) -> dict:
    """Counts of open follow-ups that are overdue / due today / upcoming."""
    as_of = as_of or date.today()
    overdue = today = upcoming = undated = 0
    for a in list_activities(session, open_only=True):
        if a.due_date is None:
            undated += 1
        elif a.due_date < as_of:
            overdue += 1
        elif a.due_date == as_of:
            today += 1
        else:
            upcoming += 1
    return {"overdue": overdue, "today": today, "upcoming": upcoming,
            "undated": undated}
