"""Stock and order-status changes that are safe when two things happen at once.

Why this file exists: reading a stock number, changing it in Python and saving it
back can overwrite a sale that happened in between, and two people cancelling the
same order at the same moment could both put the stock back. Everything here is a
single database statement that checks and changes in one step, so that cannot
happen.
"""
from datetime import datetime, timedelta

from sqlalchemy import case, update

from models import db, Order, ProductVariant


def take(variant_id, qty):
    """Remove `qty` pieces, but only if that many are in stock. True if it worked."""
    res = db.session.execute(
        update(ProductVariant)
        .where(ProductVariant.id == variant_id, ProductVariant.stock_quantity >= qty)
        .values(stock_quantity=ProductVariant.stock_quantity - qty)
        .execution_options(synchronize_session=False)
    )
    return res.rowcount == 1


def put_back(variant_id, qty):
    """Add `qty` pieces back to a shade's stock."""
    db.session.execute(
        update(ProductVariant)
        .where(ProductVariant.id == variant_id)
        .values(stock_quantity=ProductVariant.stock_quantity + qty)
        .execution_options(synchronize_session=False)
    )


def take_allow_negative(variant_id, qty):
    """Reactivating a cancelled order: always takes the pieces. Returns True if the
    shade had enough, False if stock went below zero (the caller warns the owner)."""
    enough = take(variant_id, qty)
    if not enough:
        db.session.execute(
            update(ProductVariant)
            .where(ProductVariant.id == variant_id)
            .values(stock_quantity=ProductVariant.stock_quantity - qty)
            .execution_options(synchronize_session=False)
        )
    return enough


def adjust(variant_id, delta):
    """Move a shade's stock by `delta` (positive or negative), never below zero."""
    if not delta:
        return
    if delta > 0:
        put_back(variant_id, delta)
        return
    take_up_to(variant_id, -delta)


def take_up_to(variant_id, qty):
    db.session.execute(
        update(ProductVariant)
        .where(ProductVariant.id == variant_id)
        .values(stock_quantity=case(
            (ProductVariant.stock_quantity > qty, ProductVariant.stock_quantity - qty),
            else_=0))
        .execution_options(synchronize_session=False)
    )


def claim_status(order, from_statuses, to_status, only_unpaid=False):
    """Change an order's status only if it still has one of `from_statuses`.

    Returns True for exactly one caller: whoever moves it first. Anyone arriving
    second gets False and must not put stock back again."""
    cond = [Order.id == order.id, Order.status.in_(tuple(from_statuses))]
    if only_unpaid:
        cond.append(Order.payment_status == "unpaid")
    res = db.session.execute(
        update(Order).where(*cond)
        .values(status=to_status, updated_at=datetime.utcnow())
        .execution_options(synchronize_session=False)
    )
    if res.rowcount == 1:
        db.session.expire(order, ["status", "updated_at"])
        return True
    return False


def release_expired_unpaid(hours):
    """Cancel website orders that were never paid within `hours` and put their
    pieces back on sale. 0 (or less) switches this off. Returns how many orders
    were released."""
    if not hours or hours <= 0:
        return 0
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    ids = [row[0] for row in db.session.query(Order.id).filter(
        Order.source == "website", Order.status == "pending",
        Order.payment_status == "unpaid", Order.created_at < cutoff).all()]
    released = 0
    for oid in ids:
        order = db.session.get(Order, oid)
        if order is None or not claim_status(order, ("pending",), "cancelled", only_unpaid=True):
            continue
        for item in order.items:
            if item.variant_id:
                put_back(item.variant_id, item.quantity)
        note = f"Auto-cancelled: not paid within {hours:g} hours. Stock returned."
        order.notes = f"{order.notes}\n{note}" if order.notes else note
        db.session.commit()
        released += 1
    return released
