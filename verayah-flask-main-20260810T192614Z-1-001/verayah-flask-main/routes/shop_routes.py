"""Bag and checkout. Guests can always buy; an account is never required."""
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
)

from models import db, Order, OrderItem, ProductVariant
from forms.public_forms import CheckoutForm
from services import cart as bag
from services.customer_auth import current_customer
from services.newsletter import record_consent

shop_bp = Blueprint("shop", __name__)


def _delivery_fee(method):
    """Courier fee comes from the DELIVERY_FEE setting. If it hasn't been
    decided yet it is 0 here and the owner sets the real fee on the order."""
    if method != "courier":
        return Decimal("0")
    try:
        return Decimal(current_app.config.get("DELIVERY_FEE") or "0")
    except InvalidOperation:
        return Decimal("0")


@shop_bp.route("/cart")
def cart():
    return render_template("shop/cart.html", lines=bag.lines(), subtotal=bag.subtotal(bag.lines()))


@shop_bp.route("/cart/add", methods=["POST"])
def cart_add():
    try:
        variant_id = int(request.form.get("variant_id", ""))
        qty = max(1, min(int(request.form.get("quantity", "1") or 1), bag.MAX_QTY_PER_LINE))
    except ValueError:
        flash("Please choose a shade.", "error")
        return redirect(request.referrer or url_for("products"))
    variant = db.session.get(ProductVariant, variant_id)
    if not variant or not variant.product.is_active:
        flash("That piece is no longer available.", "error")
        return redirect(url_for("products"))
    in_bag = int((bag._raw().get(str(variant_id)) or 0))
    if variant.stock_quantity <= 0:
        flash(f"{variant.product.name} ({variant.shade}) is out of stock.", "error")
    elif in_bag + qty > variant.stock_quantity:
        flash(f"Only {variant.stock_quantity} of {variant.product.name} ({variant.shade}) available.", "error")
    else:
        bag.add(variant_id, qty)
        flash(f"Added {variant.product.name} ({variant.shade}) to your bag.", "success")
        return redirect(url_for("shop.cart"))
    return redirect(request.referrer or url_for("products"))


@shop_bp.route("/cart/update", methods=["POST"])
def cart_update():
    try:
        variant_id = int(request.form.get("variant_id", ""))
        qty = int(request.form.get("quantity", "0"))
    except ValueError:
        return redirect(url_for("shop.cart"))
    variant = db.session.get(ProductVariant, variant_id)
    if variant and qty > variant.stock_quantity:
        qty = variant.stock_quantity
        flash(f"Only {variant.stock_quantity} available - quantity adjusted.", "info")
    bag.set_qty(variant_id, qty)
    return redirect(url_for("shop.cart"))


@shop_bp.route("/cart/remove", methods=["POST"])
def cart_remove():
    try:
        bag.set_qty(int(request.form.get("variant_id", "")), 0)
    except ValueError:
        pass
    return redirect(url_for("shop.cart"))


@shop_bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    lines = bag.lines()
    if not lines:
        flash("Your bag is empty.", "info")
        return redirect(url_for("products"))

    customer = current_customer()
    form = CheckoutForm()
    if request.method == "GET" and customer:
        form.name.data = customer.name
        form.email.data = customer.email
        form.phone.data = customer.phone
        form.shipping_address.data = customer.shipping_address
        form.shipping_city.data = customer.shipping_city

    if form.validate_on_submit():
        # Re-check stock at the moment of ordering.
        problems = [f"{l['product'].name} ({l['variant'].shade}): only {l['variant'].stock_quantity} left"
                    for l in lines if l["qty"] > l["variant"].stock_quantity]
        if problems:
            flash("Some items changed while you were shopping - " + "; ".join(problems) +
                  ". Please update your bag.", "error")
            return redirect(url_for("shop.cart"))

        method = form.delivery_method.data
        order = Order(
            customer_id=customer.id if customer else None,
            customer_name=form.name.data.strip(),
            customer_email=form.email.data.strip().lower(),
            customer_phone=form.phone.data.strip(),
            shipping_address=(form.shipping_address.data or "").strip() if method == "courier" else "Collection",
            shipping_city=(form.shipping_city.data or "").strip() if method == "courier" else "-",
            shipping_country="Panama",
            delivery_method=method,
            delivery_fee=_delivery_fee(method),
            payment_method=form.payment_method.data,
            payment_status="unpaid",
            source="website",
            notes=(form.notes.data or "").strip() or None,
        )
        for l in lines:
            order.items.append(OrderItem(
                product_id=l["product"].id,
                variant_id=l["variant"].id,
                product_name=l["product"].name,
                shade=l["variant"].shade,
                quantity=l["qty"],
                unit_price=l["product"].price,
            ))
            l["variant"].stock_quantity -= l["qty"]
        db.session.add(order)

        # Optional extras - each is a separate, explicit choice.
        if customer and form.save_details.data:
            customer.name = order.customer_name
            customer.phone = order.customer_phone
            if method == "courier":
                customer.shipping_address = order.shipping_address
                customer.shipping_city = order.shipping_city
        record_consent(order.customer_email, order.customer_name,
                       form.newsletter.data, form.sneak_peek.data, source="checkout")
        db.session.commit()
        bag.clear()
        return redirect(url_for("shop.order_confirmation", token=order.public_token))

    return render_template("shop/checkout.html", form=form, lines=lines,
                           subtotal=bag.subtotal(lines), customer=customer)


@shop_bp.route("/order/<token>")
def order_confirmation(token):
    order = Order.query.filter_by(public_token=token).first_or_404()
    return render_template("shop/confirmation.html", order=order)
