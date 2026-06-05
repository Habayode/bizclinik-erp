"""Industry-specific chart-of-accounts add-ons.

The base `seed_chart_of_accounts` lays down a universal Nigerian SME COA.
These templates layer industry-relevant accounts on top so a retailer,
a services firm, a restaurant or a small manufacturer each gets a COA that
matches how they actually book costs — without the user hand-building it.

Each template is a list of (code, name, type, parent_code, postable) tuples
appended via the same idempotent `_get_or_create_account` helper used by the
base seed.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AccountType
from .seed import _get_or_create_account


# (code, name, type, parent_code, postable)
_Row = tuple


TEMPLATES: dict[str, dict] = {
    "retail": {
        "label": "Retail / Trading",
        "description": "Shops, supermarkets, distributors. Stock-heavy, MDR on card sales.",
        "accounts": [
            ("5110", "Purchases - Resale Goods", AccountType.EXPENSE, "5000", True),
            ("5120", "Freight Inwards", AccountType.EXPENSE, "5000", True),
            ("5130", "Stock Shrinkage / Write-off", AccountType.EXPENSE, "5000", True),
            ("6520", "POS / Card Processing Fees (MDR)", AccountType.EXPENSE, "6000", True),
            ("6700", "Shop Rent", AccountType.EXPENSE, "6000", True),
            ("4240", "Discounts Allowed (contra)", AccountType.INCOME, "4000", True),
        ],
    },
    "services": {
        "label": "Professional Services",
        "description": "Consultancies, agencies, IT. Labour + WHT heavy, little stock.",
        "accounts": [
            ("4150", "Service Revenue", AccountType.INCOME, "4000", True),
            ("4160", "Retainer Income", AccountType.INCOME, "4000", True),
            ("6120", "Contract / Freelance Staff", AccountType.EXPENSE, "6000", True),
            ("6130", "Professional Subscriptions", AccountType.EXPENSE, "6000", True),
            ("6210", "Office Internet & Telephone", AccountType.EXPENSE, "6000", True),
            ("6710", "Software & SaaS Tools", AccountType.EXPENSE, "6000", True),
        ],
    },
    "hospitality": {
        "label": "Hospitality / Food",
        "description": "Restaurants, lounges, hotels. Food cost + many small SKUs.",
        "accounts": [
            ("4170", "Food Sales", AccountType.INCOME, "4000", True),
            ("4180", "Beverage Sales", AccountType.INCOME, "4000", True),
            ("5140", "Food Cost", AccountType.EXPENSE, "5000", True),
            ("5150", "Beverage Cost", AccountType.EXPENSE, "5000", True),
            ("6140", "Kitchen & Waiting Staff", AccountType.EXPENSE, "6000", True),
            ("6310", "Cooking Gas", AccountType.EXPENSE, "6000", True),
            ("6720", "Cutlery & Consumables", AccountType.EXPENSE, "6000", True),
        ],
    },
    "manufacturing": {
        "label": "Light Manufacturing",
        "description": "Producers, packagers, fabricators. Raw materials + WIP.",
        "accounts": [
            ("1141", "Raw Materials", AccountType.ASSET, "1100", True),
            ("1142", "Work In Progress", AccountType.ASSET, "1100", True),
            ("1143", "Finished Goods", AccountType.ASSET, "1100", True),
            ("5160", "Direct Materials Consumed", AccountType.EXPENSE, "5000", True),
            ("5170", "Direct Labour", AccountType.EXPENSE, "5000", True),
            ("5180", "Factory Overhead", AccountType.EXPENSE, "5000", True),
            ("6320", "Plant Power / Diesel", AccountType.EXPENSE, "6000", True),
        ],
    },
}


def list_templates() -> list[dict]:
    return [
        {"key": k, "label": v["label"], "description": v["description"],
         "account_count": len(v["accounts"])}
        for k, v in TEMPLATES.items()
    ]


def apply_template(session: Session, key: str) -> int:
    """Idempotently add the industry accounts. Returns count added (or
    re-confirmed)."""
    tpl = TEMPLATES.get(key)
    if not tpl:
        raise ValueError(f"Unknown COA template: {key!r}")
    for row in tpl["accounts"]:
        _get_or_create_account(session, *row)
    return len(tpl["accounts"])
