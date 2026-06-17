"""Tests for COA industry templates (onboarding)."""
from __future__ import annotations


def test_list_templates(fresh_db):
    from bizclinik_erp.services import coa_templates
    keys = {t["key"] for t in coa_templates.list_templates()}
    assert {"retail", "services", "hospitality", "manufacturing", "education"} <= keys


def test_apply_education_template(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import coa_templates
    from bizclinik_erp.models import Account
    from sqlalchemy import select
    with get_session() as s:
        n = coa_templates.apply_template(s, "education")
        assert n == 13
    with get_session() as s:
        tuition = s.execute(select(Account).where(Account.code == "4400")).scalar_one_or_none()
        assert tuition is not None and "Tuition" in tuition.name
        # Parent income header exists, so it attaches correctly.
        assert tuition.parent_id is not None


def test_apply_template_adds_accounts(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import coa_templates
    from bizclinik_erp.models import Account
    from sqlalchemy import select

    with get_session() as s:
        n = coa_templates.apply_template(s, "retail")
        assert n == 6
    with get_session() as s:
        mdr = s.execute(select(Account).where(Account.code == "6520")).scalar_one_or_none()
        assert mdr is not None
        assert "MDR" in mdr.name or "Card" in mdr.name


def test_apply_template_idempotent(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import coa_templates
    from bizclinik_erp.models import Account

    with get_session() as s:
        coa_templates.apply_template(s, "manufacturing")
    with get_session() as s:
        coa_templates.apply_template(s, "manufacturing")
    with get_session() as s:
        cnt = s.query(Account).filter(Account.code == "1142").count()
        assert cnt == 1  # Work In Progress not duplicated


def test_unknown_template_raises(fresh_db):
    import pytest
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import coa_templates
    with get_session() as s:
        with pytest.raises(ValueError):
            coa_templates.apply_template(s, "nonsense")
