"""The OTASCH demo seeder reproduces a fully-operating school: 150 students,
12 teachers, every headline figure positive, <=5% defaulters, balanced books.
Guards the seed so a tenant reset reproduces the demo exactly."""
from __future__ import annotations


def test_seed_otasch_full_operating_school(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import coa_templates
    with get_session() as s:
        coa_templates.apply_template(s, "education")   # 4400-class income, 5300/5310, 68xx

    from scripts.seed_otasch_demo import seed
    r = seed()

    assert r["students"] == 150
    assert r["teachers"] == 12
    assert r["balance_sheet_balanced"] is True
    assert r["defaulter_count"] <= 8                 # 5% of 150 = 7.5
    # every headline tile is positive (the "all metrics positive" mandate)
    for key in ("revenue", "direct_costs", "operating_expenses", "net_profit",
                "inventory_value", "ar_outstanding", "ap_outstanding"):
        assert r[key] > 0, (key, r[key])
    d = r["dashboard"]
    assert d["total_students"] == 150 and d["total_teachers"] == 12
    # idempotent guard: a second run is a no-op
    assert "skipped" in seed()
