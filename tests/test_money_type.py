"""Money columns must be NUMERIC(18,2) (the Money type) so freshly created
databases store money exactly, matching the production decimalize migration.
Quantities, rates and scores must stay Float (they are not 2dp money).

Money = Numeric(18,2, asdecimal=False): NUMERIC storage, float in Python (no
Decimal/float mixing). type(col.type).__name__ distinguishes Money ('Numeric')
from plain Float ('Float')."""
from __future__ import annotations

import bizclinik_erp.models  # noqa: F401  register all tables on Base.metadata
from bizclinik_erp.db import Base


def _coltype(table: str, col: str) -> str:
    return type(Base.metadata.tables[table].columns[col].type).__name__


MONEY = [
    ("journal_line", "debit"), ("journal_line", "credit"),
    ("receipt", "amount"), ("receipt", "applied_amount"),
    ("payment", "amount"), ("payment", "applied_amount"),
    ("sales_invoice", "amount_paid"), ("bill", "amount_paid"),
    ("sales_invoice_line", "unit_price"), ("sales_invoice_line", "unit_cost"),
    ("payroll_payslip", "gross"), ("payroll_payslip", "net_pay"),
    ("product", "standard_price"), ("product", "avg_cost"),
    ("fixed_asset", "cost"), ("bank_account", "opening_balance"),
    ("student_fee_billing", "total_amount"),
]

NON_MONEY = [
    ("sales_invoice_line", "qty"), ("sales_invoice_line", "tax_rate"),
    ("tax_code", "rate"), ("exchange_rate", "rate"),
    ("product", "qty_on_hand"), ("product", "reorder_level"),
    ("employee", "paye_rate"), ("employee", "pension_employer_rate"),
    ("school_result", "total"),
]


def test_money_columns_are_numeric():
    bad = [f"{t}.{c} -> {_coltype(t, c)}" for t, c in MONEY if _coltype(t, c) != "Numeric"]
    assert not bad, "money columns must be NUMERIC (Money), got Float: " + ", ".join(bad)


def test_quantities_and_rates_stay_float():
    bad = [f"{t}.{c} -> {_coltype(t, c)}" for t, c in NON_MONEY if _coltype(t, c) != "Float"]
    assert not bad, "qty/rate/score columns must stay Float, got NUMERIC: " + ", ".join(bad)
