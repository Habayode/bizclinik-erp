"""CRM: leads, convert→customer, deal pipeline, activities."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select


def test_create_and_list_leads(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import crm
    from bizclinik_erp.models import LeadStatus
    with get_session() as s:
        crm.create_lead(s, name="Jane Doe", company="Acme", email="j@acme.com",
                        source="referral")
        crm.create_lead(s, name="Bob", company="Globex")
    with get_session() as s:
        leads = crm.list_leads(s)
        assert len(leads) == 2
        assert all(l.status == LeadStatus.NEW for l in leads)


def test_convert_lead_creates_customer_and_deal(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import crm
    from bizclinik_erp.models import Customer, LeadStatus, DealStage
    with get_session() as s:
        lead = crm.create_lead(s, name="Jane", company="Acme Ltd",
                               email="j@acme.com", phone="0800")
        lid = lead.id
    with get_session() as s:
        res = crm.convert_lead(s, lid, create_deal=True, deal_amount=250000)
        assert res["customer_id"] and res["deal_id"]
    with get_session() as s:
        cust = s.get(Customer, res["customer_id"])
        assert cust.name == "Acme Ltd" and cust.email == "j@acme.com"
        lead = crm.list_leads(s)[0]
        assert lead.status == LeadStatus.CONVERTED
        assert lead.customer_id == cust.id
        deal = s.get(__import__("bizclinik_erp.models", fromlist=["Deal"]).Deal,
                     res["deal_id"])
        assert deal.stage == DealStage.QUALIFIED and deal.amount == 250000.0


def test_convert_is_idempotent_on_customer(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import crm
    from bizclinik_erp.models import Customer
    with get_session() as s:
        lead = crm.create_lead(s, name="Solo", company="OneCo")
        lid = lead.id
    with get_session() as s:
        c1 = crm.convert_lead(s, lid)["customer_id"]
    with get_session() as s:
        c2 = crm.convert_lead(s, lid)["customer_id"]
        assert c1 == c2
        # Only one customer created.
        assert len(list(s.execute(select(Customer)).scalars())) == 1


def test_deal_pipeline_summary_and_win_rate(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import crm
    from bizclinik_erp.models import DealStage
    with get_session() as s:
        crm.create_deal(s, title="A", amount=100000, stage=DealStage.PROPOSAL)
        crm.create_deal(s, title="B", amount=50000, stage=DealStage.NEGOTIATION)
        d_won = crm.create_deal(s, title="C", amount=300000, stage=DealStage.LEAD)
        d_lost = crm.create_deal(s, title="D", amount=20000, stage=DealStage.LEAD)
        crm.move_stage(s, d_won.id, DealStage.WON)
        crm.move_stage(s, d_lost.id, DealStage.LOST)
    with get_session() as s:
        rep = crm.pipeline_summary(s)
        # Open value = proposal + negotiation = 150,000.
        assert rep["open_value"] == 150000.0
        assert rep["open_count"] == 2
        assert rep["won_value"] == 300000.0
        # 1 won / (1 won + 1 lost) = 0.5
        assert rep["win_rate"] == 0.5


def test_move_stage_sets_closed_at(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import crm
    from bizclinik_erp.models import DealStage
    with get_session() as s:
        d = crm.create_deal(s, title="X", amount=1, stage=DealStage.LEAD)
        did = d.id
        assert d.closed_at is None
    with get_session() as s:
        d = crm.move_stage(s, did, DealStage.WON)
        assert d.closed_at is not None
    with get_session() as s:
        d = crm.move_stage(s, did, DealStage.NEGOTIATION)  # reopen
        assert d.closed_at is None


def test_activities_and_followups_due(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import crm
    from bizclinik_erp.models import ActivityKind
    today = date(2026, 6, 5)
    with get_session() as s:
        crm.log_activity(s, subject="Call back", kind=ActivityKind.CALL,
                         due_date=today - timedelta(days=2))   # overdue
        crm.log_activity(s, subject="Demo", kind=ActivityKind.MEETING,
                         due_date=today)                        # today
        crm.log_activity(s, subject="Proposal", due_date=today + timedelta(days=3))
        done = crm.log_activity(s, subject="Old", due_date=today - timedelta(days=9))
        crm.complete_activity(s, done.id)
    with get_session() as s:
        due = crm.followups_due(s, as_of=today)
        assert due["overdue"] == 1 and due["today"] == 1 and due["upcoming"] == 1
        # The completed one is excluded from open activities.
        assert len(crm.list_activities(s, open_only=True)) == 3
