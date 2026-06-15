"""Fixed-asset register import — new assets, migration (accumulated depreciation
anchored by a 'depreciation_through' date), GL resolution/auto-create, and the
guards that keep run_depreciation from back-posting the past."""
from __future__ import annotations

import io
from datetime import date

import pandas as pd
import pytest


def _df(rows):
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# New assets                                                                  #
# --------------------------------------------------------------------------- #

def test_new_asset_imports_and_posts_no_journal(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import asset_import as ai
    from bizclinik_erp.models import FixedAsset, JournalEntry
    df = _df([
        {"code": "FA-001", "name": "Dell servers", "category": "Equipment",
         "acquired_date": "2026-06-01", "cost": 1_200_000,
         "useful_life_months": 36},
    ])
    with get_session() as s:
        res = ai.import_assets(s, df)
        assert res["created"] == 1 and res["skipped"] == 0 and not res["errors"]
        a = s.query(FixedAsset).filter_by(code="FA-001").one()
        assert a.accumulated_depreciation == 0
        assert a.last_depreciation_date is None
        assert a.gl_asset_account.code == "1210"          # Equipment default
        assert a.gl_accum_dep_account.code == "1290"
        assert a.gl_dep_expense_account.code == "6600"
        # The register import must NEVER touch the GL.
        assert s.query(JournalEntry).count() == 0


# --------------------------------------------------------------------------- #
# Migration: accumulated depreciation must be anchored                        #
# --------------------------------------------------------------------------- #

def test_migrated_asset_resumes_forward_only(fresh_db):
    """A part-depreciated asset carries accum dep + a through-date; later
    run_depreciation books ONLY the months after that date — never the past."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import asset_import as ai
    from bizclinik_erp.services.assets import run_depreciation
    from bizclinik_erp.models import FixedAsset, JournalEntry
    # 9,000,000 cost, 900,000 salvage, 60 months -> 135,000/mo. 18 months done.
    df = _df([
        {"code": "FA-002", "name": "Toyota Hilux", "category": "Vehicles",
         "acquired_date": "2024-01-15", "cost": 9_000_000,
         "useful_life_months": 60, "salvage_value": 900_000,
         "accumulated_depreciation": 2_430_000,
         "depreciation_through": "2026-05-31"},
    ])
    with get_session() as s:
        res = ai.import_assets(s, df)
        assert res["created"] == 1 and not res["errors"]
        a = s.query(FixedAsset).filter_by(code="FA-002").one()
        assert a.accumulated_depreciation == 2_430_000
        assert a.last_depreciation_date == date(2026, 5, 31)

    # Run through mid-August 2026 -> should book only June + July 2026.
    with get_session() as s:
        created = run_depreciation(s, as_of=date(2026, 8, 15))
        assert len(created) == 2
        # No journal may be dated on/before the migration cut-off.
        assert all(je.entry_date > date(2026, 5, 31) for je in created)
    with get_session() as s:
        a = s.query(FixedAsset).filter_by(code="FA-002").one()
        assert a.accumulated_depreciation == 2_700_000      # 2,430,000 + 2*135,000
        assert a.last_depreciation_date == date(2026, 7, 31)
        # Sanity: only the two forward JEs exist for this asset.
        n = s.query(JournalEntry).filter_by(source_kind="DEPRECIATION").count()
        assert n == 2


def test_migrated_non_multiple_accum_depreciates_fully(fresh_db):
    """A migrated asset whose accumulated depreciation is NOT an exact multiple
    of the monthly charge must still depreciate all the way down to salvage —
    not get stranded one month short. cost 10,000 / salvage 1,000 / 60mo ->
    150/mo; accum 2,505 is 16.7 months (the round-up trap)."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import asset_import as ai
    from bizclinik_erp.services.assets import run_depreciation
    from bizclinik_erp.models import FixedAsset
    df = _df([
        {"code": "FA-NM", "name": "Imported rig", "category": "Equipment",
         "acquired_date": "2020-01-01", "cost": 10_000, "salvage_value": 1_000,
         "useful_life_months": 60, "accumulated_depreciation": 2_505,
         "depreciation_through": "2021-05-31"},
    ])
    with get_session() as s:
        assert ai.import_assets(s, df)["created"] == 1
    with get_session() as s:
        run_depreciation(s, as_of=date(2030, 1, 1))   # plenty of forward months
    with get_session() as s:
        a = s.query(FixedAsset).filter_by(code="FA-NM").one()
        # Fully depreciated to the salvage floor — nothing stranded.
        assert round(a.accumulated_depreciation, 2) == 9_000.0
        assert round(a.cost - a.accumulated_depreciation, 2) == 1_000.0   # NBV == salvage


def test_accumulated_without_through_date_is_rejected(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import asset_import as ai
    from bizclinik_erp.models import FixedAsset
    df = _df([
        {"code": "FA-003", "name": "Generator", "category": "Equipment",
         "acquired_date": "2025-01-01", "cost": 2_000_000,
         "useful_life_months": 48, "accumulated_depreciation": 500_000},
    ])
    with get_session() as s:
        res = ai.import_assets(s, df)
        assert res["created"] == 0 and res["skipped"] == 1
        assert any("depreciation_through" in e for e in res["errors"])
        assert s.query(FixedAsset).count() == 0


def test_through_before_acquired_is_rejected(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import asset_import as ai
    df = _df([
        {"code": "FA-004", "name": "Lathe", "category": "Equipment",
         "acquired_date": "2025-06-01", "cost": 1_000_000,
         "useful_life_months": 24, "accumulated_depreciation": 100_000,
         "depreciation_through": "2025-01-31"},
    ])
    with get_session() as s:
        res = ai.import_assets(s, df)
        assert res["created"] == 0 and any("before acquired" in e for e in res["errors"])


# --------------------------------------------------------------------------- #
# GL resolution / auto-create                                                 #
# --------------------------------------------------------------------------- #

def test_unmapped_category_autocreates_one_account_reused(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import asset_import as ai
    from bizclinik_erp.models import FixedAsset, Account
    df = _df([
        {"code": "M1", "name": "Press", "category": "Machinery",
         "acquired_date": "2026-01-01", "cost": 500_000, "useful_life_months": 60},
        {"code": "M2", "name": "Mixer", "category": "Machinery",
         "acquired_date": "2026-01-01", "cost": 300_000, "useful_life_months": 60},
    ])
    with get_session() as s:
        res = ai.import_assets(s, df)
        assert res["created"] == 2 and not res["errors"]
        m1 = s.query(FixedAsset).filter_by(code="M1").one()
        m2 = s.query(FixedAsset).filter_by(code="M2").one()
        # Both Machinery assets share ONE auto-created account named "Machinery".
        assert m1.gl_asset_account_id == m2.gl_asset_account_id
        acc = s.get(Account, m1.gl_asset_account_id)
        assert acc.name == "Machinery" and acc.type.value == "ASSET" \
            and acc.is_postable and acc.code.startswith("12")
        assert sum(1 for (n,) in s.query(Account.name).all() if n == "Machinery") == 1


def test_asset_account_override(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import asset_import as ai
    from bizclinik_erp.models import FixedAsset
    df = _df([
        {"code": "O1", "name": "Desk", "category": "Equipment",
         "acquired_date": "2026-01-01", "cost": 50_000, "useful_life_months": 24,
         "asset_account_code": "1220"},   # force Furniture account
    ])
    with get_session() as s:
        res = ai.import_assets(s, df)
        assert res["created"] == 1 and not res["errors"]
        assert s.query(FixedAsset).filter_by(code="O1").one().gl_asset_account.code == "1220"


def test_bad_override_and_invalid_rows_skipped(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import asset_import as ai
    from bizclinik_erp.models import FixedAsset
    df = _df([
        {"code": "B1", "name": "x", "category": "Equipment",
         "acquired_date": "2026-01-01", "cost": 0, "useful_life_months": 12},        # cost<=0
        {"code": "B2", "name": "y", "category": "Equipment",
         "acquired_date": "2026-01-01", "cost": 100, "useful_life_months": 0},       # life<=0
        {"code": "B3", "name": "z", "category": "Equipment",
         "acquired_date": "2026-01-01", "cost": 100, "useful_life_months": 12,
         "salvage_value": 100},                                                      # salvage>=cost
        {"code": "B4", "name": "w", "category": "Equipment",
         "acquired_date": "2026-01-01", "cost": 100, "useful_life_months": 12,
         "asset_account_code": "9999"},                                              # bad GL
    ])
    with get_session() as s:
        res = ai.import_assets(s, df)
        assert res["created"] == 0 and res["skipped"] == 4 and len(res["errors"]) == 4
        assert s.query(FixedAsset).count() == 0


def test_duplicate_code_skipped(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import asset_import as ai
    base = {"name": "n", "category": "Equipment", "acquired_date": "2026-01-01",
            "cost": 100_000, "useful_life_months": 24}
    with get_session() as s:
        ai.import_assets(s, _df([{"code": "DUP", **base}]))
    with get_session() as s:
        res = ai.import_assets(s, _df([{"code": "DUP", **base}]))
        assert res["created"] == 0 and res["skipped"] == 1


def test_template_is_valid_xlsx():
    from bizclinik_erp.services import asset_import as ai
    data = ai.template_bytes()
    assert data[:2] == b"PK"
    xl = pd.ExcelFile(io.BytesIO(data))
    assert "Fixed Assets" in xl.sheet_names and "Instructions" in xl.sheet_names
    cols = list(xl.parse("Fixed Assets").columns)
    assert "code" in cols and "accumulated_depreciation" in cols \
        and "depreciation_through" in cols
