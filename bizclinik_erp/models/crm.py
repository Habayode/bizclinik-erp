"""CRM models — leads, deals (pipeline), and follow-up activities.

Lightweight CRM that sits in front of the ledger: capture a Lead, work it
through a Deal pipeline, and convert a won lead into a real Customer so the
rest of the ERP (invoices, statements) takes over. Activities are follow-up
tasks/notes attached to a lead, deal, or customer.
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class LeadStatus(str, enum.Enum):
    NEW = "NEW"
    WORKING = "WORKING"
    QUALIFIED = "QUALIFIED"
    UNQUALIFIED = "UNQUALIFIED"
    CONVERTED = "CONVERTED"


class DealStage(str, enum.Enum):
    LEAD = "LEAD"
    QUALIFIED = "QUALIFIED"
    PROPOSAL = "PROPOSAL"
    NEGOTIATION = "NEGOTIATION"
    WON = "WON"
    LOST = "LOST"


# Open stages (still in the pipeline) vs closed.
OPEN_STAGES = (DealStage.LEAD, DealStage.QUALIFIED, DealStage.PROPOSAL,
               DealStage.NEGOTIATION)
CLOSED_STAGES = (DealStage.WON, DealStage.LOST)


class ActivityKind(str, enum.Enum):
    CALL = "CALL"
    EMAIL = "EMAIL"
    MEETING = "MEETING"
    TASK = "TASK"
    NOTE = "NOTE"


class Lead(Base):
    __tablename__ = "crm_lead"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[Optional[str]] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(64))
    source: Mapped[Optional[str]] = mapped_column(String(64))   # referral, web, ad, …
    status: Mapped[LeadStatus] = mapped_column(Enum(LeadStatus), default=LeadStatus.NEW)
    owner_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id"))
    # Set when the lead is converted into a real Customer.
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customer.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Deal(Base):
    __tablename__ = "crm_deal"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    lead_id: Mapped[Optional[int]] = mapped_column(ForeignKey("crm_lead.id"))
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customer.id"))
    stage: Mapped[DealStage] = mapped_column(Enum(DealStage), default=DealStage.LEAD)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency_code: Mapped[str] = mapped_column(String(3), default="NGN")
    expected_close: Mapped[Optional[date]] = mapped_column(Date)
    owner_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    lead: Mapped[Optional["Lead"]] = relationship()


class Activity(Base):
    __tablename__ = "crm_activity"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[ActivityKind] = mapped_column(Enum(ActivityKind), default=ActivityKind.TASK)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(default=False)
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # Attach to any of these (all optional).
    lead_id: Mapped[Optional[int]] = mapped_column(ForeignKey("crm_lead.id"))
    deal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("crm_deal.id"))
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customer.id"))
    owner_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
