"""ui.dataframe comma-formats money columns for display without breaking
rendering or mangling non-money numbers (years/ids/counts stay as-is)."""
from __future__ import annotations

import pandas as pd


def test_money_float_cols_selects_only_floats():
    from bizclinik_erp import ui_kit as ui
    df = pd.DataFrame({
        "name": ["Primary Bank"],
        "year": [2025],            # int — must NOT be comma-formatted
        "count": [150],            # int
        "gl_balance": [26043000.0],  # float money
        "rate": [1.5],             # float
        "active": [True],          # bool
    })
    cols = ui._money_float_cols(df)
    assert set(cols) == {"gl_balance", "rate"}


def test_comma_format_produces_separators():
    assert f"{26043000.0:,.2f}" == "26,043,000.00"


def test_ui_dataframe_renders_without_error():
    """Run the helper inside a real Streamlit script context — guards against a
    Styler/kwargs incompatibility that would blank out every table app-wide."""
    from streamlit.testing.v1 import AppTest
    script = (
        "import pandas as pd\n"
        "from bizclinik_erp import ui_kit as ui\n"
        "df = pd.DataFrame({'name': ['Primary Bank Account'],\n"
        "                   'gl_balance': [26043000.0], 'year': [2025]})\n"
        "ui.dataframe(df, hide_index=True, width='stretch')\n"
        "ui.dataframe(pd.DataFrame({'x': [1, 2]}))\n"   # int-only: no styler path
    )
    at = AppTest.from_string(script).run()
    assert not at.exception, at.exception
