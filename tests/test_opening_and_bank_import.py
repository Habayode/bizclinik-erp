"""Bank-account bulk import (GL auto-link/create) + opening-balance trial-
balance import (posts one balanced opening journal)."""
from __future__ import annotations

import io
from datetime import date

import pandas as pd
import pytest


# --------------------------------------------------------------------------- #
# Bank accounts                                                               #
# --------------------------------------------------------------------------- #

def test_bank_import_links_and_autocreates_gl(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import bulk_import
    from bizclinik_erp.models import BankAccount, Account
    df = pd.DataFrame([
        # links to the seeded 1120 Bank account
        {"code": "GTB", "name": "GTBank Operating", "bank": "GTBank",
         "account_number": "0123456789", "gl_account_code": "1120"},
        # blank GL -> auto-create an asset account under 1120
        {"code": "", "name": "Zenith Savings", "bank": "Zenith",
         "account_number": "9988776655", "gl_account_code": ""},
        # bad GL code -> skipped with error
        {"code": "BAD", "name": "Nowhere Bank", "gl_account_code": "9999"},
    ])
    with get_session() as s:
        res = bulk_import.import_rows(s, "bank", df)
        assert res["created"] == 2 and res["skipped"] == 1
        banks = {b.code: b for b in s.query(BankAccount).all()}
        # linked one points at the existing 1120 account
        gtb_gl = s.get(Account, banks["GTB"].gl_account_id)
        assert gtb_gl.code == "1120"
        # auto-created one has a fresh asset GL account named after the bank
        zen = [b for b in banks.values() if b.name == "Zenith Savings"][0]
        zen_gl = s.get(Account, zen.gl_account_id)
        assert zen_gl.type.value == "ASSET" and "Zenith" in zen_gl.name
        assert "BAD" not in banks


def test_bank_template_has_gl_column():
    from bizclinik_erp.services import bulk_import
    df = pd.read_excel(io.BytesIO(bulk_import.template_bytes("bank")),
                       sheet_name="Bank accounts")
    assert "gl_account_code" in df.columns and "name" in df.columns


# --------------------------------------------------------------------------- #
# Opening balances                                                            #
# --------------------------------------------------------------------------- #

def _tb(rows):
    return pd.DataFrame(rows)


def test_opening_balance_posts_balanced_journal(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import opening_balance as ob
    from bizclinik_erp.services.ledger import trial_balance
    df = _tb([
        {"account_code": "1120", "debit": 2_500_000, "credit": ""},   # Bank
        {"account_code": "1130", "debit": 850_000, "credit": ""},     # AR
        {"account_code": "2110", "debit": "", "credit": 1_400_000},   # AP
        {"account_code": "3100", "debit": "", "credit": 1_950_000},   # Share capital
    ])
    with get_session() as s:
        res = ob.import_trial_balance(s, df, as_of=date(2026, 1, 1))
        assert res["je_no"].startswith("JE-")
        assert res["total_debit"] == 3_350_000 == res["total_credit"]
        assert res["balancing_amount"] == 0
    with get_session() as s:
        tb = trial_balance(s)
        assert round(sum(r["debit"] for r in tb), 2) == \
               round(sum(r["credit"] for r in tb), 2)


def test_unbalanced_without_plug_raises(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import opening_balance as ob
    df = _tb([
        {"account_code": "1120", "debit": 1_000_000, "credit": ""},
        {"account_code": "3100", "debit": "", "credit": 900_000},     # off by 100k
    ])
    with get_session() as s:
        with pytest.raises(ValueError, match="out of balance"):
            ob.import_trial_balance(s, df, as_of=date(2026, 1, 1))


def test_unbalanced_with_plug_absorbs_difference(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import opening_balance as ob
    from bizclinik_erp.services.ledger import trial_balance
    df = _tb([
        {"account_code": "1120", "debit": 1_000_000, "credit": ""},
        {"account_code": "3100", "debit": "", "credit": 900_000},
    ])
    with get_session() as s:
        res = ob.import_trial_balance(s, df, as_of=date(2026, 1, 1),
                                     plug_account_code="3200")  # Retained Earnings
        assert res["balancing_amount"] == 100_000
        assert res["balancing_account"] == "3200"
    with get_session() as s:
        tb = trial_balance(s)
        assert round(sum(r["debit"] for r in tb), 2) == \
               round(sum(r["credit"] for r in tb), 2)


def test_missing_account_aborts_whole_import(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import opening_balance as ob
    from bizclinik_erp.models import JournalEntry
    df = _tb([
        {"account_code": "1120", "debit": 500_000, "credit": ""},
        {"account_code": "9999", "debit": "", "credit": 500_000},     # missing
    ])
    with get_session() as s:
        with pytest.raises(ValueError, match="not found"):
            ob.import_trial_balance(s, df, as_of=date(2026, 1, 1))
        assert s.query(JournalEntry).filter_by(source_kind="OPENING").count() == 0


def test_opening_balance_refuses_second_import(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import opening_balance as ob
    df = _tb([
        {"account_code": "1120", "debit": 100_000, "credit": ""},
        {"account_code": "3100", "debit": "", "credit": 100_000},
    ])
    with get_session() as s:
        ob.import_trial_balance(s, df, as_of=date(2026, 1, 1))
    with get_session() as s:
        with pytest.raises(ValueError, match="already posted"):
            ob.import_trial_balance(s, df, as_of=date(2026, 1, 2))


def test_template_is_valid_xlsx():
    from bizclinik_erp.services import opening_balance as ob
    data = ob.template_bytes()
    assert data[:2] == b"PK"
    xl = pd.ExcelFile(io.BytesIO(data))
    assert "Trial Balance" in xl.sheet_names and "Instructions" in xl.sheet_names
    assert list(xl.parse("Trial Balance").columns) == [
        "account_code", "account_name", "debit", "credit"]
