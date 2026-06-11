"""Assistant answer logic — rule-based data + how-to KB."""
from __future__ import annotations

SNAP = {
    "as_of": "11 Jun 2026", "revenue_mtd": 1_232_500, "revenue_ytd": 1_232_500,
    "net_profit_ytd": -874_000, "cash": 2_914_425, "ar_outstanding": 522_950,
    "ap_outstanding": 3_102_000, "inventory_value": 1_976_000,
    "pending_approvals": 1, "customers": 4, "suppliers": 3, "products": 4,
    "employees": 4, "invoices": 4, "bills": 5,
}


def test_data_answers_from_snapshot():
    from bizclinik_erp import assistant as a
    assert "1,232,500" in a.answer("What's my revenue this month?", SNAP)
    assert "2,914,425" in a.answer("How much cash do I have?", SNAP)
    assert "522,950" in a.answer("What do customers owe me?", SNAP)
    assert "3,102,000" in a.answer("How much do we owe suppliers?", SNAP)
    assert "874,000" in a.answer("What's my net profit?", SNAP)
    assert "4 employees" in a.answer("How many employees do we have?", SNAP)
    # Pending approvals — phrased as a count question
    ans = a.answer("How many approvals are pending?", SNAP)
    assert "1 approval pending" in ans


def test_howto_answers_from_kb():
    from bizclinik_erp import assistant as a
    assert "Sales" in a.answer("How do I raise an invoice?", {})
    assert "Payroll" in a.answer("run payroll", {})
    # Plural query should still match singular KB terms (stemming)
    assert "ROLE limit" in a.answer("how do approvals work", {})
    assert "Recruitment" in a.answer("how do I post a job opening", {})


def test_unknown_question_falls_back():
    from bizclinik_erp import assistant as a
    out = a.answer("what is the meaning of life", {})
    assert "I can help with how to use the ERP" in out


def test_data_takes_precedence_over_howto():
    from bizclinik_erp import assistant as a
    # "revenue" is a data keyword -> should answer from the snapshot, not KB
    assert "Revenue this month" in a.answer("revenue this month", SNAP)
    # ...but with no snapshot it gracefully answers how-to-ish / fallback
    assert a.answer("revenue this month", {})  # non-empty


def test_launcher_html_is_pure_css_anchor():
    from bizclinik_erp import assistant as a
    html = a.launcher_html("assistant")
    assert 'class="bzk-fab"' in html
    assert 'href="assistant"' in html
    assert "<script" not in html      # no JS — reliable everywhere
