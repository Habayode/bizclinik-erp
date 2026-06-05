"""Bank reconciliation tests.

End-to-end: seed → 3 invoices → 3 receipts hitting BANK1 → fabricate a
4-row statement (3 deposits + 1 charge) → auto_match (expect 3/1/0) →
post the missing bank-charge JE → auto_match again (expect 1/0/0) →
finalize.

Also smoke-tests the Moniepoint CSV importer against the bundled fixture.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select


FIXTURE_CSV = Path(__file__).parent / "fixtures" / "moniepoint_sample.csv"


def _bank1(s):
    from bizclinik_erp.models import BankAccount
    return s.execute(
        select(BankAccount).where(BankAccount.code == "BANK1")
    ).scalar_one()


def _seed_customer_and_product(s):
    from bizclinik_erp.models import Customer, Product
    s.add(Customer(code="C001", name="HPL Ltd", email="ops@hpl.ng"))
    s.add(Product(sku="ITEM1", name="Test Item",
                   standard_price=50_000, standard_cost=20_000,
                   is_stockable=False))
    s.flush()


def _three_invoices_and_receipts(fresh_db):
    """Issue 3 invoices on different dates, settle each with a receipt
    against BANK1. Returns the three receipt amounts in order."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import sales as sales_svc

    with get_session() as s:
        _seed_customer_and_product(s)

    plan = [
        (date(2026, 4, 3), 50_000.0),
        (date(2026, 4, 10), 75_000.0),
        (date(2026, 4, 17), 100_000.0),
    ]
    with get_session() as s:
        from bizclinik_erp.models import Customer, Product
        cust = s.execute(select(Customer)).scalar_one()
        prod = s.execute(select(Product)).scalar_one()
        bank = _bank1(s)
        for d, amt in plan:
            inv = sales_svc.issue_invoice(
                s, customer_id=cust.id, invoice_date=d,
                lines=[sales_svc.LineInput(
                    product_id=prod.id, description=prod.name,
                    qty=1, unit_price=amt, tax_rate=0.0,
                )],
            )
            sales_svc.record_receipt(
                s, customer_id=cust.id, receipt_date=d,
                amount=inv.grand_total, bank_account_id=bank.id,
                invoice_id=inv.id,
            )
    return plan


# --------------------------------------------------------------- importer


def test_moniepoint_csv_parses_fixture():
    from bizclinik_erp.importers.moniepoint_csv import parse_moniepoint_csv
    rows = parse_moniepoint_csv(FIXTURE_CSV.read_bytes())
    assert len(rows) == 5
    deposits = [r for r in rows if r["amount"] > 0]
    charges = [r for r in rows if r["amount"] < 0]
    assert len(deposits) == 3
    assert len(charges) == 2
    assert deposits[0]["amount"] == pytest.approx(50_000.0)
    assert charges[0]["amount"] == pytest.approx(-500.0)
    assert deposits[0]["txn_date"] == date(2026, 4, 3)
    assert deposits[0]["reference"] == "TRF/AAA1"


# --------------------------------------------------------------- full flow


def test_full_reconciliation_flow(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import (
        BankStatement, DocStatus, JournalLine, StatementStatus,
    )
    from bizclinik_erp.services import banking as bank_svc
    from bizclinik_erp.services import recon as recon_svc

    # (a) Issue 3 invoices + 3 receipts.
    plan = _three_invoices_and_receipts(fresh_db)

    # Sanity check: BANK1 GL account should now have 3 debit lines (DR Bank
    # from receipts) — one per receipt.
    with get_session() as s:
        bank = _bank1(s)
        bank_gl_id = bank.gl_account_id
        bank_je_lines = s.execute(
            select(JournalLine).where(JournalLine.account_id == bank_gl_id)
        ).scalars().all()
        debit_lines = [l for l in bank_je_lines if l.debit > 0]
        assert len(debit_lines) == 3
        for (_, amt), jl in zip(plan, sorted(debit_lines, key=lambda x: x.id)):
            assert jl.debit == pytest.approx(amt)

    # (b) Build a fake statement: 3 matching deposits + 1 unmatched charge.
    with get_session() as s:
        bank = _bank1(s)
        stmt = recon_svc.create_statement(
            s,
            bank_account_id=bank.id,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
            opening_balance=0.0,
            closing_balance=224_500.0,  # 50k + 75k + 100k − 500 charge
            source_file="april_2026.csv",
        )
        recon_svc.import_statement_lines(s, stmt.id, [
            {"txn_date": date(2026, 4, 3),  "description": "Transfer in",
             "amount":  50_000.0, "reference": "TRF/AAA1"},
            {"txn_date": date(2026, 4, 10), "description": "Transfer in",
             "amount":  75_000.0, "reference": "TRF/BBB2"},
            {"txn_date": date(2026, 4, 17), "description": "Transfer in",
             "amount": 100_000.0, "reference": "TRF/CCC3"},
            {"txn_date": date(2026, 4, 20), "description": "Monthly charge",
             "amount":     -500.0, "reference": "CHG/0420"},
        ])
        stmt_id = stmt.id

    # (c) auto_match — three deposits should land, charge should be left over.
    with get_session() as s:
        res = recon_svc.auto_match(s, stmt_id, day_tolerance=3)
    assert res["matched"] == 3
    assert res["unmatched_statement"] == 1
    assert res["unmatched_gl"] == 0

    # (d) Post the missing bank-charge JE and re-run auto_match.
    with get_session() as s:
        bank = _bank1(s)
        bank_svc.post_bank_charge(
            s, bank_account_id=bank.id,
            on=date(2026, 4, 20), amount=500.0,
            memo="Monthly maintenance charge",
        )
    with get_session() as s:
        res2 = recon_svc.auto_match(s, stmt_id, day_tolerance=3)
    assert res2["matched"] == 1
    assert res2["unmatched_statement"] == 0
    assert res2["unmatched_gl"] == 0

    # Summary should now show zero unreconciled buckets.
    with get_session() as s:
        summary = recon_svc.reconciliation_summary(s, stmt_id)
    assert summary["unreconciled_statement_count"] == 0
    assert summary["unreconciled_gl_count"] == 0
    assert summary["matched_count"] == 4
    assert summary["matched_total"] == pytest.approx(224_500.0)

    # (e) Finalize.
    with get_session() as s:
        stmt = recon_svc.finalize(s, stmt_id)
        assert stmt.status == StatementStatus.RECONCILED

    with get_session() as s:
        stmt = s.get(BankStatement, stmt_id)
        assert stmt.status == StatementStatus.RECONCILED


# --------------------------------------------------------------- guards


def test_manual_match_and_unmatch(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.models import BankStatementLine, JournalLine
    from bizclinik_erp.services import banking as bank_svc
    from bizclinik_erp.services import recon as recon_svc

    with get_session() as s:
        bank = _bank1(s)
        bank_svc.post_bank_charge(
            s, bank_account_id=bank.id,
            on=date(2026, 4, 20), amount=750.0, memo="Card maintenance")
        # Make a 1-line statement that the auto-matcher can't touch
        # (wrong amount), so we exercise manual_match instead.
        stmt = recon_svc.create_statement(
            s, bank_account_id=bank.id,
            period_start=date(2026, 4, 1), period_end=date(2026, 4, 30),
            opening_balance=0.0, closing_balance=-750.0,
            source_file="manual.csv",
        )
        recon_svc.import_statement_lines(s, stmt.id, [
            {"txn_date": date(2026, 4, 20), "description": "Charge",
             "amount": -750.0, "reference": "CHG/0420"},
        ])
        sid = stmt.id

    with get_session() as s:
        sl = s.execute(select(BankStatementLine).where(
            BankStatementLine.statement_id == sid)).scalar_one()
        jl = s.execute(select(JournalLine).where(
            JournalLine.account_id == _bank1(s).gl_account_id,
            JournalLine.credit > 0,
        )).scalar_one()
        recon_svc.manual_match(s, sl.id, jl.id)

    with get_session() as s:
        sl = s.execute(select(BankStatementLine).where(
            BankStatementLine.statement_id == sid)).scalar_one()
        assert sl.matched_je_line_id is not None
        recon_svc.unmatch(s, sl.id)

    with get_session() as s:
        sl = s.execute(select(BankStatementLine).where(
            BankStatementLine.statement_id == sid)).scalar_one()
        assert sl.matched_je_line_id is None
