"""Bag and checkout. Guests can always buy; an account is never required."""
from decimal import Decimal, InvalidOperation

from sqlalchemy import func
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
)

from models import db, Order, OrderItem, ProductVariant
from services import stock
from forms.public_forms import CheckoutForm
from services import cart as bag
from services.customer_auth import current_customer
from services.newsletter import record_consent
from services.security import order_throttle, client_ip
from services.i18n import t

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


def _email_link(endpoint, **values):
    """Absolute link for an email. Uses PUBLIC_BASE_URL when it is set, so a
    forged Host header can't point the links at another site."""
    base = current_app.config.get("PUBLIC_BASE_URL")
    if base:
        return base + url_for(endpoint, **values)
    return url_for(endpoint, _external=True, **values)


def _send_order_emails(order):
    """Alert the owner and confirm to the customer. Never lets an email problem break an order."""
    try:
        from services import mailer
        if not mailer.is_configured():
            return
        order_url = _email_link("shop.order_confirmation", token=order.public_token)
        admin_url = _email_link("admin.order_detail", order_id=order.id)
        mailer.notify_owner_new_order(order, admin_url)
        mailer.confirm_to_customer(order, order_url, current_app.config["SITE"])
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Order email step failed for order %s", order.id)


@shop_bp.route("/cart")
def cart():
    return render_template("shop/cart.html", lines=bag.lines(), subtotal=bag.subtotal(bag.lines()))


@shop_bp.route("/cart/add", methods=["POST"])
def cart_add():
    try:
        variant_id = int(request.form.get("variant_id", ""))
        qty = max(1, min(int(request.form.get("quantity", "1") or 1), bag.MAX_QTY_PER_LINE))
    except ValueError:
        flash(t("Please choose a shade."), "error")
        return redirect(request.referrer or url_for("products"))
    variant = db.session.get(ProductVariant, variant_id)
    if not variant or not variant.product.is_active:
        flash(t("That piece is no longer available."), "error")
        return redirect(url_for("products"))
    in_bag = int((bag._raw().get(str(variant_id)) or 0))
    if variant.stock_quantity <= 0:
        flash(t("{item} is out of stock.", item=f"{variant.product.name} ({variant.shade})"), "error")
    elif in_bag + qty > variant.stock_quantity:
        flash(t("Only {n} of {item} available.", n=variant.stock_quantity, item=f"{variant.product.name} ({variant.shade})"), "error")
    else:
        bag.add(variant_id, qty)
        flash(t("Added {item} to your bag.", item=f"{variant.product.name} ({variant.shade})"), "success")
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
        flash(t("Only {n} available - quantity adjusted.", n=variant.stock_quantity), "info")
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
        flash(t("Your bag is empty."), "info")
        return redirect(url_for("products"))

    cap = current_app.config.get("MAX_UNITS_PER_ORDER", 6)
    if sum(l["qty"] for l in lines) > cap:
        flash(t("Website orders are limited to {n} pieces at a time. Please remove a few from your bag, or contact us to place a larger order.", n=cap), "error")
        return redirect(url_for("shop.cart"))

    customer = current_customer()
    form = CheckoutForm()
    if request.method == "GET" and customer:
        form.name.data = customer.name
        form.email.data = customer.email
        form.phone.data = customer.phone
        form.shipping_address.data = customer.shipping_address
        form.shipping_city.data = customer.shipping_city

    if form.validate_on_submit():
        okey = "order:" + client_ip()
        if order_throttle.blocked(okey):
            flash(t("Too many orders from this connection in a short time. Please try again later or contact us to place your order."), "error")
            return redirect(url_for("shop.cart"))
        # Unpaid orders hold their pieces, so one email address may only have a
        # limited number of pieces waiting for payment at a time. Counted from the
        # database, so it holds across restarts and several workers.
        email = form.email.data.strip().lower()
        waiting = (db.session.query(func.coalesce(func.sum(OrderItem.quantity), 0))
                   .join(Order, Order.id == OrderItem.order_id)
                   .filter(Order.source == "website", Order.status == "pending",
                           Order.payment_status == "unpaid",
                           func.lower(Order.customer_email) == email).scalar()) or 0
        if waiting + sum(l["qty"] for l in lines) > cap:
            flash(t("You already have orders waiting for payment. Please pay for those first, or contact us to place a larger order."), "error")
            return redirect(url_for("shop.cart"))
        # Re-check stock at the moment of ordering.
        problems = [t("{item}: only {n} left", item=f"{l['product'].name} ({l['variant'].shade})", n=l['variant'].stock_quantity)
                    for l in lines if l["qty"] > l["variant"].stock_quantity]
        if problems:
            flash(t("Some items changed while you were shopping - {problems}. Please update your bag.", problems="; ".join(problems)), "error")
            return redirect(url_for("shop.cart"))

        method = form.delivery_method.data
        order = Order(
            customer_id=customer.id if customer else None,
            customer_name=form.name.data.strip(),
            customer_email=email,
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
            # Atomic decrement: only succeeds while enough stock remains, so two
            # shoppers buying the last piece at once cannot both get it.
            if not stock.take(l["variant"].id, l["qty"]):
                db.session.rollback()
                flash(t("Sorry - {item} just sold out or changed. Please update your bag.", item=f"{l['product'].name} ({l['variant'].shade})"), "error")
                return redirect(url_for("shop.cart"))
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
        order_throttle.record(okey)
        bag.clear()
        _send_order_emails(order)
        return redirect(url_for("shop.order_confirmation", token=order.public_token))

    return render_template("shop/checkout.html", form=form, lines=lines,
                           subtotal=bag.subtotal(lines), customer=customer)


@shop_bp.route("/order/<token>")
def order_confirmation(token):
    order = Order.query.filter_by(public_token=token).first_or_404()
    return render_template("shop/confirmation.html", order=order)
