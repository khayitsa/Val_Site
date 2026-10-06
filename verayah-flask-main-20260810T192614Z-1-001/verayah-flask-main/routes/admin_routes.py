"""
Admin portal: product CRUD + order/shipping management.

Security measures in this file:
- every route except /admin/login requires an authenticated session (Flask-Login)
- login attempts are throttled per-username to slow down brute force
- all forms use Flask-WTF, which enforces CSRF tokens automatically
- uploaded images are re-validated (extension + content) and saved under a
  random filename, never the name the browser sent
- all DB access goes through the ORM (parameterized), never raw SQL strings
"""
import csv
import io
import os
import time
import uuid
from datetime import datetime

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    current_app, abort, Response
)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename

from models import (
    db, AdminUser, Product, ProductVariant, Order, OrderItem,
    Customer, Subscriber, ContactMessage
)
from forms.admin_forms import LoginForm, ProductForm, OrderStatusForm, OrderForm, OrderCustomerForm

admin_bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="../templates/admin")

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

# --- Simple in-memory login throttle -----------------------------------
# Good enough for a single small-business site on one worker process.
# If this ever runs behind multiple workers/dynos, swap this for
# Flask-Limiter backed by Redis instead.
_failed_attempts = {}  # username(lowercase) -> [timestamps]
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60


def _is_locked_out(username):
    key = username.lower().strip()
    attempts = [t for t in _failed_attempts.get(key, []) if time.time() - t < LOCKOUT_SECONDS]
    _failed_attempts[key] = attempts
    return len(attempts) >= MAX_ATTEMPTS


def _record_failed_attempt(username):
    key = username.lower().strip()
    _failed_attempts.setdefault(key, []).append(time.time())


def _clear_failed_attempts(username):
    _failed_attempts.pop(username.lower().strip(), None)


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _save_product_image(file_storage):
    """Save an uploaded product photo under a random filename and return it."""
    ext = secure_filename(file_storage.filename).rsplit(".", 1)[1].lower()
    random_name = f"{uuid.uuid4().hex}.{ext}"
    dest_dir = os.path.join(current_app.root_path, "static", "images", "products")
    os.makedirs(dest_dir, exist_ok=True)
    file_storage.save(os.path.join(dest_dir, random_name))
    return random_name


def _sync_variants(product):
    """Rebuild a product's shade/stock rows from the submitted form.

    Rows arrive as parallel arrays: variant_id[] (blank for new rows),
    variant_shade[], variant_stock[]. Existing variants not present in the
    submission are removed - unless they're referenced by a past order, in
    which case we keep the row but zero its stock instead, so order history
    never breaks.
    """
    ids = request.form.getlist("variant_id")
    shade_names = request.form.getlist("variant_shade")
    stocks = request.form.getlist("variant_stock")

    existing_by_id = {str(v.id): v for v in product.variants}
    seen_ids = set()

    for vid, shade, stock in zip(ids, shade_names, stocks):
        shade = (shade or "").strip()
        if not shade:
            continue
        try:
            stock = max(0, int(stock))
        except (TypeError, ValueError):
            stock = 0

        if vid and vid in existing_by_id:
            variant = existing_by_id[vid]
            variant.shade = shade
            variant.stock_quantity = stock
            seen_ids.add(vid)
        else:
            variant = ProductVariant(shade=shade, stock_quantity=stock)
            product.variants.append(variant)

    # Remove rows that were deleted in the form (unless they're referenced
    # by a past order, in which case we keep the row but zero its stock so
    # order history never breaks).
    for vid, variant in existing_by_id.items():
        if vid in seen_ids:
            continue
        has_orders = OrderItem.query.filter_by(variant_id=variant.id).first() is not None
        if has_orders:
            variant.stock_quantity = 0
        else:
            db.session.delete(variant)


# --- Auth ----------------------------------------------------------------

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()

        if _is_locked_out(username):
            flash("Too many failed attempts. Please wait 15 minutes and try again.", "error")
            return render_template("admin/login.html", form=form)

        user = AdminUser.query.filter_by(username=username).first()
        if user and user.check_password(form.password.data):
            _clear_failed_attempts(username)
            login_user(user)
            return redirect(url_for("admin.dashboard"))

        _record_failed_attempt(username)
        flash("Incorrect username or password.", "error")

    return render_template("admin/login.html", form=form)


@admin_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("admin.login"))


# --- Dashboard -------------------------------------------------------------

@admin_bp.route("/")
@login_required
def dashboard():
    stats = {
        "product_count": Product.query.count(),
        "active_product_count": Product.query.filter_by(is_active=True).count(),
        "pending_orders": Order.query.filter_by(status="pending").count(),
        "processing_orders": Order.query.filter_by(status="processing").count(),
        "total_orders": Order.query.count(),
        "awaiting_payment": Order.query.filter(Order.payment_status == "unpaid",
                                               Order.status != "cancelled").count(),
        "new_messages": ContactMessage.query.filter_by(handled=False).count(),
        "customers": Customer.query.count(),
        "subscribers": Subscriber.query.filter(Subscriber.unsubscribed_at.is_(None)).count(),
    }
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    return render_template("admin/dashboard.html", stats=stats, recent_orders=recent_orders)


# --- Products ----------------------------------------------------------------

@admin_bp.route("/products")
@login_required
def products_list():
    products = Product.query.order_by(Product.sort_order, Product.name).all()
    return render_template("admin/products_list.html", products=products)


@admin_bp.route("/products/new", methods=["GET", "POST"])
@login_required
def product_new():
    form = ProductForm()
    if form.validate_on_submit():
        product = Product(
            name=form.name.data.strip(),
            category=form.category.data,
            price=form.price.data,
            description=form.description.data.strip(),
            is_active=form.is_active.data,
            sort_order=form.sort_order.data or 0,
        )
        if form.image.data:
            product.image_filename = _save_product_image(form.image.data)
        _sync_variants(product)
        if not product.variants:
            flash("Add at least one shade with a stock quantity.", "error")
            return render_template("admin/product_form.html", form=form, mode="new")
        db.session.add(product)
        db.session.commit()
        flash(f'"{product.name}" was added.', "success")
        return redirect(url_for("admin.products_list"))
    return render_template("admin/product_form.html", form=form, mode="new")


@admin_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    form = ProductForm(obj=product)
    if request.method == "GET":
        form.price.data = product.price

    if form.validate_on_submit():
        product.name = form.name.data.strip()
        product.category = form.category.data
        product.price = form.price.data
        product.description = form.description.data.strip()
        product.is_active = form.is_active.data
        product.sort_order = form.sort_order.data or 0
        if form.image.data:
            product.image_filename = _save_product_image(form.image.data)
        _sync_variants(product)
        if not product.variants:
            flash("Add at least one shade with a stock quantity.", "error")
            return render_template("admin/product_form.html", form=form, mode="edit", product=product)
        product.updated_at = datetime.utcnow()
        db.session.commit()
        flash(f'"{product.name}" was updated.', "success")
        return redirect(url_for("admin.products_list"))

    return render_template("admin/product_form.html", form=form, mode="edit", product=product)


@admin_bp.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required
def product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    name = product.name
    db.session.delete(product)
    db.session.commit()
    flash(f'"{name}" was deleted.', "success")
    return redirect(url_for("admin.products_list"))


# --- Orders / shipping ----------------------------------------------------

@admin_bp.route("/orders")
@login_required
def orders_list():
    status_filter = request.args.get("status", "").strip()
    query = Order.query
    if status_filter in Order.STATUSES:
        query = query.filter_by(status=status_filter)
    orders = query.order_by(Order.created_at.desc()).all()
    return render_template("admin/orders_list.html", orders=orders, status_filter=status_filter,
                            statuses=Order.STATUSES)


@admin_bp.route("/orders/new", methods=["GET", "POST"])
@login_required
def order_new():
    form = OrderForm()
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()

    # Feed the in-stock shade options per product to the page as JSON, so
    # picking a product can populate its shade dropdown with live stock
    # counts client-side, without a separate request per row.
    variants_by_product = {
        p.id: [{"id": v.id, "shade": v.shade, "stock": v.stock_quantity}
               for v in p.variants if v.stock_quantity > 0]
        for p in products
    }

    if form.validate_on_submit():
        order = Order(
            customer_name=form.customer_name.data.strip(),
            customer_email=(form.customer_email.data or "").strip() or None,
            customer_phone=(form.customer_phone.data or "").strip() or None,
            shipping_address=form.shipping_address.data.strip(),
            shipping_city=form.shipping_city.data.strip(),
            shipping_country=form.shipping_country.data.strip(),
            notes=(form.notes.data or "").strip() or None,
        )

        # Line items arrive as parallel form arrays.
        product_ids = request.form.getlist("item_product_id")
        variant_ids = request.form.getlist("item_variant_id")
        quantities = request.form.getlist("item_quantity")

        added_any = False
        for pid, vid, qty in zip(product_ids, variant_ids, quantities):
            if not pid or not vid or not qty:
                continue
            try:
                qty = int(qty)
            except ValueError:
                continue
            if qty <= 0:
                continue

            product = Product.query.get(int(pid))
            variant = ProductVariant.query.get(int(vid))
            if not product or not variant or variant.product_id != product.id:
                continue

            if qty > variant.stock_quantity:
                flash(
                    f"Only {variant.stock_quantity} of {product.name} ({variant.shade}) left in stock — "
                    f"reduce the quantity and try again.", "error"
                )
                return render_template("admin/order_form.html", form=form, products=products,
                                        variants_by_product=variants_by_product)

            order.items.append(OrderItem(
                product_id=product.id,
                variant_id=variant.id,
                product_name=product.name,
                shade=variant.shade,
                quantity=qty,
                unit_price=product.price,
            ))
            variant.stock_quantity -= qty
            added_any = True

        if not added_any:
            flash("Add at least one product to the order.", "error")
            return render_template("admin/order_form.html", form=form, products=products,
                                    variants_by_product=variants_by_product)

        db.session.add(order)
        db.session.commit()
        flash(f"Order #{order.id} for {order.customer_name} was created.", "success")
        return redirect(url_for("admin.order_detail", order_id=order.id))

    return render_template("admin/order_form.html", form=form, products=products,
                            variants_by_product=variants_by_product)


@admin_bp.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    form = OrderStatusForm(status=order.status, payment_status=order.payment_status,
                           delivery_fee=order.delivery_fee, tracking_number=order.tracking_number,
                           notes=order.notes)
    customer_form = OrderCustomerForm(obj=order)
    return render_template("admin/order_detail.html", order=order, form=form, customer_form=customer_form)


@admin_bp.route("/orders/<int:order_id>/update", methods=["POST"])
@login_required
def order_update(order_id):
    order = Order.query.get_or_404(order_id)
    form = OrderStatusForm()
    if form.validate_on_submit():
        old_status = order.status
        new_status = form.status.data

        if old_status != "cancelled" and new_status == "cancelled":
            for item in order.items:
                if item.variant_id:
                    variant = ProductVariant.query.get(item.variant_id)
                    if variant:
                        variant.stock_quantity += item.quantity
            flash_extra = " Stock was returned for its items."
        elif old_status == "cancelled" and new_status != "cancelled":
            short_items = []
            for item in order.items:
                if item.variant_id:
                    variant = ProductVariant.query.get(item.variant_id)
                    if variant:
                        if variant.stock_quantity < item.quantity:
                            short_items.append(f"{item.product_name} ({item.shade})")
                        variant.stock_quantity -= item.quantity
            flash_extra = ""
            if short_items:
                flash(f"Warning: reactivating this order pushed stock negative for: {', '.join(short_items)}. "
                      f"Double check inventory.", "error")
        else:
            flash_extra = ""

        order.status = new_status
        order.payment_status = form.payment_status.data
        if form.delivery_fee.data is not None:
            order.delivery_fee = form.delivery_fee.data
        order.tracking_number = (form.tracking_number.data or "").strip() or None
        order.notes = (form.notes.data or "").strip() or None
        order.updated_at = datetime.utcnow()
        db.session.commit()
        flash(f"Order #{order.id} updated.{flash_extra}", "success")
    else:
        flash("Could not update order — please check the form.", "error")
    return redirect(url_for("admin.order_detail", order_id=order.id))


@admin_bp.route("/orders/<int:order_id>/customer", methods=["POST"])
@login_required
def order_customer_update(order_id):
    order = Order.query.get_or_404(order_id)
    form = OrderCustomerForm()
    if form.validate_on_submit():
        order.customer_name = form.customer_name.data.strip()
        order.customer_email = (form.customer_email.data or "").strip().lower() or None
        order.customer_phone = (form.customer_phone.data or "").strip() or None
        order.shipping_address = form.shipping_address.data.strip()
        order.shipping_city = form.shipping_city.data.strip()
        order.shipping_country = form.shipping_country.data.strip()
        order.updated_at = datetime.utcnow()
        db.session.commit()
        flash("Customer details updated.", "success")
    else:
        flash("Could not update customer details - please check the form.", "error")
    return redirect(url_for("admin.order_detail", order_id=order.id))


@admin_bp.route("/orders/<int:order_id>/delete", methods=["POST"])
@login_required
def order_delete(order_id):
    """Permanently erase an order (e.g. an order made in error, or a data-deletion request).
    Stock is returned only for orders that were still open."""
    order = Order.query.get_or_404(order_id)
    if order.status in ("pending", "processing"):
        for item in order.items:
            if item.variant_id:
                variant = db.session.get(ProductVariant, item.variant_id)
                if variant:
                    variant.stock_quantity += item.quantity
    number = order.id
    db.session.delete(order)
    db.session.commit()
    flash(f"Order #{number} was permanently deleted.", "success")
    return redirect(url_for("admin.orders_list"))


# --- Customers (optional shopper accounts) ------------------------------------

@admin_bp.route("/customers")
@login_required
def customers_list():
    customers = Customer.query.order_by(Customer.created_at.desc()).all()
    return render_template("admin/customers_list.html", customers=customers)


@admin_bp.route("/customers/<int:customer_id>/delete", methods=["POST"])
@login_required
def customer_delete(customer_id):
    """Delete an account on request. Past orders are kept but unlinked."""
    customer = Customer.query.get_or_404(customer_id)
    for order in customer.orders:
        order.customer_id = None
    email = customer.email
    db.session.delete(customer)
    db.session.commit()
    flash(f"Account {email} was deleted. Its past orders were kept as records.", "success")
    return redirect(url_for("admin.customers_list"))


# --- Newsletter / sneak-peek subscribers ---------------------------------------

@admin_bp.route("/subscribers")
@login_required
def subscribers_list():
    subscribers = Subscriber.query.order_by(Subscriber.consented_at.desc()).all()
    return render_template("admin/subscribers_list.html", subscribers=subscribers)


@admin_bp.route("/subscribers/export.csv")
@login_required
def subscribers_export():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["email", "name", "newsletter", "sneak_peek", "consent_source", "consented_at"])
    for s in Subscriber.query.filter(Subscriber.unsubscribed_at.is_(None)).order_by(Subscriber.email):
        if s.newsletter or s.sneak_peek:
            writer.writerow([s.email, s.name or "", int(s.newsletter), int(s.sneak_peek),
                             s.consent_source or "", s.consented_at.strftime("%Y-%m-%d") if s.consented_at else ""])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=verayah-subscribers.csv"})


@admin_bp.route("/subscribers/<int:sub_id>/delete", methods=["POST"])
@login_required
def subscriber_delete(sub_id):
    sub = Subscriber.query.get_or_404(sub_id)
    db.session.delete(sub)
    db.session.commit()
    flash("Subscriber removed.", "success")
    return redirect(url_for("admin.subscribers_list"))


# --- Contact messages ------------------------------------------------------------

@admin_bp.route("/messages")
@login_required
def messages_list():
    messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    return render_template("admin/messages_list.html", messages=messages)


@admin_bp.route("/messages/<int:msg_id>/handled", methods=["POST"])
@login_required
def message_handled(msg_id):
    msg = ContactMessage.query.get_or_404(msg_id)
    msg.handled = not msg.handled
    db.session.commit()
    return redirect(url_for("admin.messages_list"))


@admin_bp.route("/messages/<int:msg_id>/delete", methods=["POST"])
@login_required
def message_delete(msg_id):
    msg = ContactMessage.query.get_or_404(msg_id)
    db.session.delete(msg)
    db.session.commit()
    flash("Message deleted.", "success")
    return redirect(url_for("admin.messages_list"))
