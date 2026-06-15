"""Bulk customer/supplier import: template + upload."""
from __future__ import annotations

import io

import pandas as pd
import pytest


def test_template_is_a_valid_xlsx_with_headers():
    from bizclinik_erp.services import contact_import
    for kind, sheet, cols in [
        ("customer", "Customers",
         ["code", "name", "email", "phone", "address", "credit_limit"]),
        ("supplier", "Suppliers", ["code", "name", "email", "phone", "address"]),
    ]:
        data = contact_import.template_bytes(kind)
        assert data[:2] == b"PK"          # xlsx is a zip
        xl = pd.ExcelFile(io.BytesIO(data))
        assert sheet in xl.sheet_names and "Instructions" in xl.sheet_names
        df = xl.parse(sheet)
        assert list(df.columns) == cols
        assert len(df) == 0               # data sheet ships empty (no accidental rows)


def test_import_creates_rows_and_autogenerates_codes(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import contact_import
    from bizclinik_erp.models import Customer
    df = pd.DataFrame([
        {"code": "C001", "name": "Sunrise Ltd", "email": "a@x.ng",
         "phone": "0803", "address": "Ikeja", "credit_limit": 500000},
        {"code": "", "name": "Mama Tobi", "email": None, "phone": "0701",
         "address": "", "credit_limit": ""},          # blank code -> auto
        {"code": "", "name": "", "email": "", "phone": "", "address": "",
         "credit_limit": ""},                           # blank row -> ignored
    ])
    with get_session() as s:
        res = contact_import.import_rows(s, "customer", df)
        assert res["created"] == 2 and res["skipped"] == 0
        custs = {c.code: c for c in s.query(Customer).all()}
        assert "C001" in custs and custs["C001"].credit_limit == 500000
        auto = [c for c in custs if c != "C001"]
        assert auto and auto[0].startswith("C")        # auto-generated code
        assert custs["C001"].name == "Sunrise Ltd"


def test_import_skips_duplicate_codes(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import contact_import
    from bizclinik_erp.models import Supplier
    df = pd.DataFrame([{"code": "S1", "name": "Acme"}])
    with get_session() as s:
        contact_import.import_rows(s, "supplier", df)
    with get_session() as s:
        res = contact_import.import_rows(s, "supplier", df)   # same file again
        assert res["created"] == 0 and res["skipped"] == 1
        assert s.query(Supplier).count() == 1                 # no duplicate


def test_import_round_trip_from_downloaded_template(fresh_db):
    """Download the template, fill it, and import — the realistic flow."""
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import contact_import
    from bizclinik_erp.models import Customer
    data = contact_import.template_bytes("customer")
    df = pd.read_excel(io.BytesIO(data))                      # empty headers
    df = pd.concat([df, pd.DataFrame([
        {"name": "Walk-in Customer"},
        {"name": "Global Imports LLC", "email": "ap@global.com"},
    ])], ignore_index=True)
    with get_session() as s:
        res = contact_import.import_rows(s, "customer", df)
        assert res["created"] == 2
        assert s.query(Customer).count() == 2


def test_import_rejects_file_without_name_column(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import contact_import
    df = pd.DataFrame([{"wrong": "x"}])
    with get_session() as s:
        with pytest.raises(ValueError, match="name"):
            contact_import.import_rows(s, "customer", df)
