"""The bank-agnostic parser handles varied NG bank CSV header styles."""
from __future__ import annotations

from datetime import date


def _rows(csv_text):
    from bizclinik_erp.importers.bank_statement import parse_bank_statement
    return parse_bank_statement(csv_text)


def test_gtbank_style_headers():
    csv = (
        "Trans Date,Narration,Reference,Debit,Credit,Balance\n"
        "01/05/2026,POS Purchase,REF1,5000,,95000\n"
        "03/05/2026,Inflow from client,REF2,,20000,115000\n"
    )
    rows = _rows(csv)
    assert len(rows) == 2
    assert rows[0]["txn_date"] == date(2026, 5, 1)
    assert rows[0]["amount"] == -5000.0       # debit -> negative
    assert rows[1]["amount"] == 20000.0       # credit -> positive
    assert rows[1]["reference"] == "REF2"


def test_zenith_particulars_and_value_date():
    csv = (
        "Value Date,Particulars,Withdrawals,Deposits\n"
        "2026-05-10,Bank charge,150.50,\n"
        "2026-05-11,Transfer in,,3000\n"
    )
    rows = _rows(csv)
    assert rows[0]["amount"] == -150.50
    assert rows[0]["description"] == "Bank charge"
    assert rows[1]["amount"] == 3000.0


def test_single_signed_amount_column():
    csv = (
        "Tran Date,Memo,Amount\n"
        "12/05/2026,Refund,(1200.00)\n"     # bracketed negative
        "13/05/2026,Deposit,4500\n"
    )
    rows = _rows(csv)
    assert rows[0]["amount"] == -1200.0
    assert rows[1]["amount"] == 4500.0


def test_naira_symbol_and_commas_stripped():
    csv = "Date,Description,Credit\n2026-05-01,Big sale,\"₦1,250,000.00\"\n"
    rows = _rows(csv)
    assert rows[0]["amount"] == 1250000.0


def test_totals_and_blank_rows_skipped():
    csv = (
        "Date,Description,Debit,Credit\n"
        "2026-05-01,Item,100,\n"
        ",TOTAL,100,\n"           # no date -> skipped
        "2026-05-02,,,0\n"        # zero amount -> skipped
    )
    rows = _rows(csv)
    assert len(rows) == 1
