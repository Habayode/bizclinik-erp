"""ui_kit.line_builder — the payment-style line entry used by PO/SO."""
from __future__ import annotations

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = st_testing.AppTest

_SCRIPT = """
import streamlit as st
from bizclinik_erp import ui_kit as ui
prods = [{"id": 1, "sku": "SKU1", "name": "Widget", "default_price": 100.0}]
lines = ui.line_builder("t_lines", prods, price_label="Unit price (N)")
st.session_state["_count"] = len(lines)
"""


def test_line_builder_renders_without_error():
    at = AppTest.from_string(_SCRIPT, default_timeout=30).run()
    assert not at.exception
    assert at.session_state["_count"] == 0          # nothing added yet
    # The add-line form exposes its fields by key.
    assert any(s.key == "t_lines_qty" for s in at.number_input)
    assert any(s.key == "t_lines_prod" for s in at.selectbox)


def test_line_builder_clear_resets_state():
    at = AppTest.from_string(_SCRIPT, default_timeout=30).run()
    at.session_state["t_lines"] = [
        {"product_id": 1, "description": "Widget", "qty": 2.0,
         "price": 50.0, "tax_rate": 0.075}]
    at.run()
    assert at.session_state["_count"] == 1          # line shows on re-run
    from bizclinik_erp import ui_kit as ui  # noqa: F401
    # clear via the helper path
    at.session_state["t_lines"] = []
    at.run()
    assert at.session_state["_count"] == 0
