"""Runtime settings (db location, currency, default VAT rate, etc.)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path
    currency_symbol: str = "₦"
    currency_code: str = "NGN"
    default_vat_rate: float = 0.075       # 7.5% Nigerian VAT
    default_wht_rate: float = 0.05        # 5% withholding tax (services)
    company_name: str = "BizClinik ERP"
    fiscal_year_start_month: int = 1      # January

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings resolved from env vars / defaults.

    Env vars:
        BIZCLINIK_DB_PATH      — sqlite file path
        BIZCLINIK_CURRENCY     — ISO currency code (default NGN)
        BIZCLINIK_VAT_RATE     — decimal (default 0.075)
    """
    default_db = Path(__file__).resolve().parent.parent / "data" / "bizclinik.db"
    db_path = Path(os.environ.get("BIZCLINIK_DB_PATH", default_db))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return Settings(
        db_path=db_path,
        currency_code=os.environ.get("BIZCLINIK_CURRENCY", "NGN"),
        currency_symbol=os.environ.get("BIZCLINIK_CURRENCY_SYMBOL", "₦"),
        default_vat_rate=float(os.environ.get("BIZCLINIK_VAT_RATE", "0.075")),
        default_wht_rate=float(os.environ.get("BIZCLINIK_WHT_RATE", "0.05")),
    )
