from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Optional


def _iso(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


@dataclass
class CompanyInfo:
    name: Optional[str] = None
    rc_number: Optional[str] = None
    address: Optional[str] = None
    vat_no: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class InventoryItem:
    code: str
    description: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class InventoryMovement:
    code: Optional[str]
    description: Optional[str]
    qty_in: float = 0.0
    qty_out: float = 0.0
    avg_cost: Optional[float] = None
    balance: float = 0.0

    @property
    def net(self) -> float:
        return (self.qty_in or 0) - (self.qty_out or 0)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SupplierEntry:
    date: Optional[datetime]
    reference_no: Optional[str]
    vendor: Optional[str]
    code: Optional[str]
    description: Optional[str]
    qty_in: Optional[float] = None
    rate: Optional[float] = None
    total: Optional[float] = None
    vat: Optional[float] = None
    total_after_vat: Optional[float] = None
    account_name: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = _iso(self.date)
        return d


@dataclass
class CustomerEntry:
    date: Optional[datetime]
    reference_no: Optional[str]
    customer: Optional[str]
    code: Optional[str]
    description: Optional[str]
    qty_out: Optional[float] = None
    rate: Optional[float] = None
    total: Optional[float] = None
    vat: Optional[float] = None
    total_after_vat: Optional[float] = None
    account_name: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = _iso(self.date)
        return d


@dataclass
class OperatingEntry:
    date: Optional[datetime]
    reference_no: Optional[str]
    vendor: Optional[str]
    description: Optional[str]
    qty_in: Optional[float] = None
    rate: Optional[float] = None
    total: Optional[float] = None
    vat: Optional[float] = None
    total_after_vat: Optional[float] = None
    account_name: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = _iso(self.date)
        return d


@dataclass
class Account:
    code: Optional[int]
    name: str
    category: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)
