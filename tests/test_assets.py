"""Fixed Assets module tests: straight-line depreciation, trial-balance
invariant after multiple JE postings, and asset disposal lifecycle."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select


def _account_id(s, code: str) -> int:
    from bizclinik_erp.models import Account
    return s.execute(select(Account).where(Account.code == code)).scalar_one().id


def _bank_id(s, code: str = "BANK1") -> int:
    from bizclinik_erp.models import BankAccount
    return s.execute(select(BankAccount).where(BankAccount.code == code)).scalar_one().id


def _add_test_asset(s, *, code="FA-001", cost=1_200_000.0, life=24,
                    acquired=date(2026, 1, 1), salvage=0.0):
    from bizclinik_erp.services import assets as assets_svc
    return assets_svc.add_asset(
        s,
        code=code, name=f"Test Asset {code}",
        category="Equipment",
        acquired_date=acquired,
        cost=cost,
        salvage_value=salvage,
        useful_life_months=life,
        gl_asset_account_id=_account_id(s, "1210"),
        gl_accum_dep_account_id=_account_id(s, "1290"),
        gl_dep_expense_account_id=_account_id(s, "6600"),
    )


def test_straight_line_depreciation_over_24_months(fresh_db):
    """1,200,000 cost / 24 months = 50,000 per month. Running from
    2026-01-01 acquisition through as_of 2027-01-15 should post 12 JEs
    (months Jan..Dec 2026 — Jan 2027 is the as_of month and not complete)."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import assets as assets_svc

    with get_session() as s:
        asset = _add_test_asset(s)
        asset_id = asset.id

    with get_session() as s:
        created = assets_svc.run_depreciation(s, as_of=date(2027, 1, 15))

    assert len(created) == 12, f"Expected 12 monthly JEs, got {len(created)}"

    with get_session() as s:
        from bizclinik_erp.models import FixedAsset
        asset = s.get(FixedAsset, asset_id)
        assert asset.accumulated_depreciation == pytest.approx(600_000.0, abs=0.01)
        assert asset.last_depreciation_date == date(2026, 12, 31)

    # Each JE charged exactly 50,000.
    for je in created:
        assert je.total_debit == pytest.approx(50_000.0, abs=0.01)
        assert je.total_credit == pytest.approx(50_000.0, abs=0.01)


def test_trial_balance_balances_after_depreciation(fresh_db):
    """After posting 12 months of depreciation JEs, sum(debits) == sum(credits)
    across all posted journal lines."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import assets as assets_svc
    from bizclinik_erp.models import DocStatus, JournalEntry, JournalLine

    with get_session() as s:
        _add_test_asset(s)

    with get_session() as s:
        assets_svc.run_depreciation(s, as_of=date(2027, 1, 15))

    with get_session() as s:
        rows = s.execute(
            select(JournalLine.debit, JournalLine.credit)
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .where(JournalEntry.status == DocStatus.POSTED)
        ).all()
        total_dr = round(sum(r.debit for r in rows), 2)
        total_cr = round(sum(r.credit for r in rows), 2)
        assert total_dr == total_cr, f"DR {total_dr} != CR {total_cr}"
        assert total_dr > 0


def test_dispose_asset_status(fresh_db):
    """Dispose mid-life at 2026-07-01 for ₦900k. Status flips to DISPOSED and
    a balanced JE is posted."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import assets as assets_svc
    from bizclinik_erp.models import AssetStatus, FixedAsset

    with get_session() as s:
        asset = _add_test_asset(s)
        asset_id = asset.id
        bank_id = _bank_id(s)

    # Catch up depreciation through June 2026 (run before the disposal date).
    with get_session() as s:
        assets_svc.run_depreciation(s, as_of=date(2026, 7, 1))

    with get_session() as s:
        je = assets_svc.dispose_asset(
            s, asset_id,
            on=date(2026, 7, 1),
            proceeds=900_000.0,
            bank_account_id=bank_id,
        )
        assert je.is_balanced
        assert je.source_kind == "ASSET_DISPOSAL"
        assert je.source_id == asset_id

    with get_session() as s:
        asset = s.get(FixedAsset, asset_id)
        assert asset.status == AssetStatus.DISPOSED
        assert asset.disposed_date == date(2026, 7, 1)
        assert asset.disposal_proceeds == pytest.approx(900_000.0, abs=0.01)
