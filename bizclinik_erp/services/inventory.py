"""Inventory: weighted-average costing, stock movements, valuation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import Account, Product, StockMovement


def record_stock_in(
    session: Session, product: Product, *, qty: float, unit_cost: float,
    on: date, source_kind: Optional[str] = None,
    source_id: Optional[int] = None, memo: Optional[str] = None,
    warehouse_id: Optional[int] = None,
) -> StockMovement:
    """Record stock receipt. Updates the product's weighted-avg cost.

    new_avg = (existing_qty * existing_avg + qty * unit_cost) / (existing_qty + qty)
    Falls back to unit_cost when no prior on-hand.
    """
    if qty <= 0:
        raise ValueError("Stock-in qty must be positive.")
    on_hand = product.qty_on_hand or 0.0
    avg = product.avg_cost or 0.0
    if on_hand + qty <= 0:
        new_avg = unit_cost
    else:
        new_avg = (on_hand * avg + qty * unit_cost) / (on_hand + qty)
    product.qty_on_hand = round(on_hand + qty, 4)
    product.avg_cost = round(new_avg, 4)

    mov = StockMovement(
        movement_date=on, product_id=product.id, warehouse_id=warehouse_id,
        qty_in=qty, qty_out=0.0, unit_cost=unit_cost,
        avg_cost_after=product.avg_cost,
        qty_on_hand_after=product.qty_on_hand,
        source_kind=source_kind, source_id=source_id, memo=memo,
    )
    session.add(mov)
    session.flush()
    return mov


def record_stock_out(
    session: Session, product: Product, *, qty: float, on: date,
    unit_cost: Optional[float] = None,
    source_kind: Optional[str] = None, source_id: Optional[int] = None,
    memo: Optional[str] = None, warehouse_id: Optional[int] = None,
) -> StockMovement:
    """Record stock issue (sale / adjustment-out). Avg cost is unchanged."""
    if qty <= 0:
        raise ValueError("Stock-out qty must be positive.")
    if unit_cost is None:
        unit_cost = product.avg_cost or 0.0
    product.qty_on_hand = round((product.qty_on_hand or 0.0) - qty, 4)
    mov = StockMovement(
        movement_date=on, product_id=product.id, warehouse_id=warehouse_id,
        qty_in=0.0, qty_out=qty, unit_cost=unit_cost,
        avg_cost_after=product.avg_cost,
        qty_on_hand_after=product.qty_on_hand,
        source_kind=source_kind, source_id=source_id, memo=memo,
    )
    session.add(mov)
    session.flush()
    return mov


def stock_card(session: Session, product_id: int) -> list[dict]:
    """Chronological movement history for a product."""
    rows = session.execute(
        select(StockMovement)
        .where(StockMovement.product_id == product_id)
        .order_by(StockMovement.movement_date, StockMovement.id)
    ).scalars().all()
    return [{
        "date": m.movement_date,
        "qty_in": m.qty_in,
        "qty_out": m.qty_out,
        "unit_cost": m.unit_cost,
        "avg_cost_after": m.avg_cost_after,
        "qty_on_hand_after": m.qty_on_hand_after,
        "source": f"{m.source_kind or ''}#{m.source_id}" if m.source_id else "",
        "memo": m.memo,
    } for m in rows]


def inventory_valuation(session: Session) -> list[dict]:
    """Snapshot: every stockable product with qty × avg_cost."""
    rows = session.execute(
        select(Product).where(Product.is_stockable == True, Product.is_active == True)  # noqa: E712
        .order_by(Product.sku)
    ).scalars().all()
    out = []
    for p in rows:
        value = round((p.qty_on_hand or 0) * (p.avg_cost or 0), 2)
        out.append({
            "sku": p.sku, "name": p.name,
            "qty_on_hand": p.qty_on_hand,
            "avg_cost": p.avg_cost,
            "value_at_cost": value,
            "below_reorder": (p.qty_on_hand or 0) < (p.reorder_level or 0),
        })
    return out


def adjust_stock(
    session: Session, product_id: int, *, on: date, qty_delta: float,
    unit_cost: Optional[float] = None, memo: Optional[str] = None,
) -> StockMovement:
    """Manual stock adjustment (positive or negative). Posts no JE on its own —
    callers should post a corresponding inventory-vs-shrinkage JE if needed."""
    product = session.get(Product, product_id)
    if not product:
        raise ValueError(f"Product {product_id} not found.")
    if qty_delta > 0:
        return record_stock_in(session, product, qty=qty_delta,
                               unit_cost=unit_cost or product.avg_cost,
                               on=on, source_kind="ADJUSTMENT", memo=memo)
    return record_stock_out(session, product, qty=-qty_delta, on=on,
                            unit_cost=unit_cost, source_kind="ADJUSTMENT",
                            memo=memo)
