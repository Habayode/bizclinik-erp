"""Fixed Assets master model.

Holds capital items that are depreciated over their useful life rather than
expensed at acquisition. Depreciation runs (services.assets.run_depreciation)
post monthly JEs hitting accumulated depreciation + depreciation expense.
Disposal posts a balanced JE removing the asset from the books.
"""
from __future__ import annotations

import enum
from datetime import date
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class DepreciationMethod(str, enum.Enum):
    """How the per-period depreciation charge is computed.

    Only straight-line is supported for now; the enum exists so that
    declining-balance can be added later without an Alembic migration.
    """
    STRAIGHT_LINE = "STRAIGHT_LINE"


class AssetStatus(str, enum.Enum):
    """Lifecycle state of a fixed asset."""
    ACTIVE = "ACTIVE"
    DISPOSED = "DISPOSED"


class FixedAsset(Base):
    """A single capitalised item with its GL account triplet and depreciation policy."""
    __tablename__ = "fixed_asset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    acquired_date: Mapped[date] = mapped_column(Date, nullable=False)
    cost: Mapped[float] = mapped_column(Float, nullable=False)
    salvage_value: Mapped[float] = mapped_column(Float, default=0.0)
    useful_life_months: Mapped[int] = mapped_column(Integer, nullable=False)
    depreciation_method: Mapped[DepreciationMethod] = mapped_column(
        Enum(DepreciationMethod), default=DepreciationMethod.STRAIGHT_LINE
    )
    gl_asset_account_id: Mapped[int] = mapped_column(
        ForeignKey("account.id"), nullable=False
    )
    gl_accum_dep_account_id: Mapped[int] = mapped_column(
        ForeignKey("account.id"), nullable=False
    )
    gl_dep_expense_account_id: Mapped[int] = mapped_column(
        ForeignKey("account.id"), nullable=False
    )
    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus), default=AssetStatus.ACTIVE
    )
    disposed_date: Mapped[Optional[date]] = mapped_column(Date)
    disposal_proceeds: Mapped[Optional[float]] = mapped_column(Float)
    # Running total of depreciation booked against this asset. Kept in sync
    # by run_depreciation() so the register doesn't need to scan the GL.
    accumulated_depreciation: Mapped[float] = mapped_column(Float, default=0.0)
    last_depreciation_date: Mapped[Optional[date]] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    gl_asset_account = relationship("Account", foreign_keys=[gl_asset_account_id])
    gl_accum_dep_account = relationship("Account", foreign_keys=[gl_accum_dep_account_id])
    gl_dep_expense_account = relationship("Account", foreign_keys=[gl_dep_expense_account_id])

    def __repr__(self) -> str:
        return f"<FixedAsset {self.code} {self.name}>"
