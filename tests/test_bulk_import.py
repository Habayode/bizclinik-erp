"""Generic bulk import: templates + uploads for customer/supplier/product/
employee/account."""
from __future__ import annotations

import io

import pandas as pd
import pytest


def test_every_spec_produces_a_valid_template():
    from bizclinik_erp.services import bulk_import
    for kind, spec in bulk_import.SPECS.items():
        data = bulk_import.template_bytes(kind)
        assert data[:2] == b"PK"                         # xlsx == zip
        xl = pd.ExcelFile(io.BytesIO(data))
        assert spec.sheet in xl.sheet_names and "Instructions" in xl.sheet_names
        df = xl.parse(spec.sheet)
        assert list(df.columns) == [spec.code_col] + [f.col for f in spec.fields]
        assert len(df) == 0                              # ships empty


def test_customer_import_autocodes_and_credit_limit(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import bulk_import
    from bizclinik_erp.models import Customer
    df = pd.DataFrame([
        {"code": "C001", "name": "Sunrise", "credit_limit": 500000},
        {"code": "", "name": "Mama Tobi"},               # blank -> auto
        {"name": ""},                                    # blank row -> ignored
    ])
    with get_session() as s:
        res = bulk_import.import_rows(s, "customer", df)
        assert res["created"] == 2
        custs = {c.code: c for c in s.query(Customer).all()}
        assert custs["C001"].credit_limit == 500000
        assert any(c.startswith("C") and c != "C001" for c in custs)


def test_product_import_uses_sku_and_bool_and_unit_default(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import bulk_import
    from bizclinik_erp.models import Product
    df = pd.DataFrame([
        {"sku": "RICE50", "name": "Rice 50kg", "unit": "bag",
         "standard_price": 45000, "standard_cost": 38000, "is_stockable": "yes"},
        {"sku": "", "name": "Delivery", "is_stockable": "no"},   # auto sku, unit->ea
    ])
    with get_session() as s:
        res = bulk_import.import_rows(s, "product", df)
        assert res["created"] == 2
        prods = {p.sku: p for p in s.query(Product).all()}
        assert prods["RICE50"].is_stockable is True
        assert prods["RICE50"].standard_price == 45000
        deliv = [p for p in prods.values() if p.name == "Delivery"][0]
        assert deliv.is_stockable is False
        assert deliv.unit == "ea"                        # blank unit -> default


def test_employee_import_pension_defaults(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import bulk_import
    from bizclinik_erp.models import Employee
    df = pd.DataFrame([
        {"code": "EMP001", "name": "Chioma", "monthly_gross": 250000},
        {"name": "Bola", "monthly_gross": 180000, "pension_rate": 0.05},
    ])
    with get_session() as s:
        res = bulk_import.import_rows(s, "employee", df)
        assert res["created"] == 2
        emps = {e.name: e for e in s.query(Employee).all()}
        assert emps["Chioma"].pension_rate == 0.08       # default
        assert emps["Chioma"].pension_employer_rate == 0.10
        assert emps["Bola"].pension_rate == 0.05         # honoured
        assert emps["Bola"].code.startswith("EMP")       # auto


def test_account_import_enum_parent_and_required_code(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import bulk_import
    from bizclinik_erp.models import Account, AccountType
    df = pd.DataFrame([
        {"code": "9500", "name": "Other Income", "type": "income",
         "parent_code": "", "is_postable": "yes"},
        {"code": "9510", "name": "Scrap Sales", "type": "INCOME",
         "parent_code": "9500", "is_postable": "yes"},   # parent resolves
        {"code": "X1", "name": "Bad", "type": "NONSENSE"},   # invalid enum -> skip
        {"code": "", "name": "No code"},                     # code required -> skip
    ])
    with get_session() as s:
        res = bulk_import.import_rows(s, "account", df)
        assert res["created"] == 2 and res["skipped"] == 2
        accts = {a.code: a for a in s.query(Account).all()
                 if a.code in ("9500", "9510")}
        assert accts["9500"].type == AccountType.INCOME
        assert accts["9510"].parent_id == accts["9500"].id   # parent linked


def test_round_trip_from_downloaded_supplier_template(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import bulk_import
    from bizclinik_erp.models import Supplier
    df = pd.read_excel(io.BytesIO(bulk_import.template_bytes("supplier")))
    df = pd.concat([df, pd.DataFrame([{"name": "FreshFarm"},
                                      {"name": "PackRight"}])], ignore_index=True)
    with get_session() as s:
        res = bulk_import.import_rows(s, "supplier", df)
        assert res["created"] == 2
        assert s.query(Supplier).count() == 2


def test_missing_name_column_rejected(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import bulk_import
    with get_session() as s:
        with pytest.raises(ValueError, match="name"):
            bulk_import.import_rows(s, "product", pd.DataFrame([{"sku": "X"}]))
