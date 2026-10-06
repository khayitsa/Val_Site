"""Session-based shopping bag. Holds only {variant_id: quantity}; prices and
stock are always re-read from the database, never trusted from the browser."""
from decimal import Decimal

from flask import session

from models import db, ProductVariant

MAX_QTY_PER_LINE = 10


def _raw():
    cart = session.get("cart")
    return cart if isinstance(cart, dict) else {}


def add(variant_id, qty):
    cart = dict(_raw())
    key = str(variant_id)
    cart[key] = min(cart.get(key, 0) + qty, MAX_QTY_PER_LINE)
    session["cart"] = cart


def set_qty(variant_id, qty):
    cart = dict(_raw())
    key = str(variant_id)
    if qty <= 0:
        cart.pop(key, None)
    else:
        cart[key] = min(qty, MAX_QTY_PER_LINE)
    session["cart"] = cart


def clear():
    session.pop("cart", None)


def count():
    return sum(int(q) for q in _raw().values() if isinstance(q, int))


def lines():
    """Resolve the bag into purchasable lines. Drops anything that no longer
    exists or is hidden, and flags lines that exceed current stock."""
    result = []
    for key, qty in list(_raw().items()):
        try:
            variant = db.session.get(ProductVariant, int(key))
            qty = int(qty)
        except (TypeError, ValueError):
            continue
        if not variant or not variant.product.is_active or qty <= 0:
            continue
        product = variant.product
        result.append({
            "variant": variant,
            "product": product,
            "qty": qty,
            "unit_price": product.price,
            "line_total": product.price * qty,
            "over_stock": qty > variant.stock_quantity,
        })
    return result


def subtotal(cart_lines):
    return sum((l["line_total"] for l in cart_lines), start=Decimal("0"))
