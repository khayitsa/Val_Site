"""
Admin portal: product CRUD + order/shipping management.

Security measures in this file:
- every route except /admin/login requires an authenticated session (Flask-Login)
- login attempts are throttled per-username to slow down brute force
- all forms use Flask-WTF, which enforces CSRF tokens automatically
- uploaded images are validated (extension + file signature, see forms/admin_forms.py)
  and saved under a random filename, never the name the browser sent
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
    db, AdminUser, Product, ProductVariant, ProductImage, Order, OrderItem,
    Customer, Subscriber, ContactMessage, JournalPost, WishlistItem
)
from services.journal import unique_slug
from services import stock
from services.security import admin_login_throttle, client_ip
from services.i18n import t
from forms.admin_forms import check_upload, LoginForm, ProductForm, OrderStatusForm, OrderForm, OrderCustomerForm, JournalForm

admin_bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="../templates/admin")

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

# Login throttling lives in services/security.py (keyed on username + address,
# so a stranger cannot lock the real admin out from another connection).


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _save_product_image(file_storage, subdir="products"):
    """Shrink an uploaded photo to web size, save it under a random filename and return it."""
    from services.images import optimise
    data, ext = optimise(file_storage.stream)
    random_name = f"{uuid.uuid4().hex}.{ext}"
    dest_dir = os.path.join(current_app.root_path, "static", "images", subdir)
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, random_name), "wb") as fh:
        fh.write(data.read())
    return random_name


MAX_EXTRA_PHOTOS = 7   # plus the main photo = 8 photos per product


def _delete_product_file(filename):
    """Remove an uploaded product photo from disk (ignore if it is already gone)."""
    if not filename:
        return
    path = os.path.join(current_app.root_path, "static", "images", "products", os.path.basename(filename))
    try:
        os.remove(path)
    except OSError:
        pass


def _extra_photo_problem(product):
    """Look at the 'more photos' part of the submitted form BEFORE anything is saved.

    Returns (new_files, ids_to_remove, error_message). If error_message is set,
    nothing should be saved and the form should be shown again.
    """
    from wtforms.validators import ValidationError
    files = [f for f in request.files.getlist("more_images") if f and f.filename]
    remove_ids = set(request.form.getlist("remove_extra"))
    keep = [i for i in (product.extra_images if product else []) if str(i.id) not in remove_ids]
    if len(keep) + len(files) > MAX_EXTRA_PHOTOS:
        return [], remove_ids, t("A product can have up to {total} photos (1 main + {extra} extra). Remove some first.",
                                 total=MAX_EXTRA_PHOTOS + 1, extra=MAX_EXTRA_PHOTOS)
    for f in files:
        if not _allowed_file(f.filename):
            return [], remove_ids, f'"{f.filename}": ' + t("Please use a JPG, PNG or WEBP photo. (iPhone tip: if it is a HEIC photo, share or export it as JPG first.)")
        try:
            check_upload(f)
        except ValidationError as exc:
            return [], remove_ids, f'"{f.filename}": {exc}'
    return files, remove_ids, None


def _apply_extra_photos(product, files, remove_ids):
    """Save the new extra photos and drop the ones that were ticked for removal."""
    for img in list(product.extra_images):
        if str(img.id) in remove_ids:
            _delete_product_file(img.filename)
            product.extra_images.remove(img)
    next_order = max([i.sort_order for i in product.extra_images] + [0]) + 1
    for f in files:
        product.extra_images.append(ProductImage(filename=_save_product_image(f), sort_order=next_order))
        next_order += 1


def _sync_variants(product):
    """Rebuild a product's shade/stock rows from the submitted form.

    Rows arrive as parallel arrays: variant_id[] (blank for new rows),
    variant_shade[], variant_stock[], variant_stock_seen[] (the number the form
    showed when it was opened). Existing variants not present in the
    submission are removed - unless they're referenced by a past order, in
    which case we keep the row but zero its stock instead, so order history
    never breaks.
    """
    ids = request.form.getlist("variant_id")
    shade_names = request.form.getlist("variant_shade")
    stocks = request.form.getlist("variant_stock")
    seen = request.form.getlist("variant_stock_seen")
    seen += [""] * (len(ids) - len(seen))

    existing_by_id = {str(v.id): v for v in product.variants}
    seen_ids = set()
    stock_changes = []

    for vid, shade, stock, was in zip(ids, shade_names, stocks, seen):
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
            seen_ids.add(vid)
            # Change stock by what the owner changed (new minus what the form showed),
            # as one database step. Saving the number outright would erase any sale
            # made while the form was open.
            try:
                was = int(was)
            except (TypeError, ValueError):
                was = None
            if was is None:
                variant.stock_quantity = stock          # older form without the hidden field
            else:
                stock_changes.append((variant.id, stock - max(0, was)))
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

    # Applied by the caller once the product itself is saved.
    return stock_changes


def _apply_stock_changes(changes):
    for variant_id, delta in changes:
        stock.adjust(variant_id, delta)


# --- Auth ----------------------------------------------------------------

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()

        tkey = username.lower() + "|" + client_ip()
        if admin_login_throttle.blocked(tkey):
            flash(t("Too many failed attempts. Please wait 15 minutes and try again."), "error")
            return render_template("admin/login.html", form=form)

        user = AdminUser.query.filter_by(username=username).first()
        if user and user.check_password(form.password.data):
            admin_login_throttle.clear(tkey)
            login_user(user)
            return redirect(url_for("admin.dashboard"))

        admin_login_throttle.record(tkey)
        flash(t("Incorrect username or password."), "error")

    return render_template("admin/login.html", form=form)


@admin_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    # Bump the counter so a copy of the login cookie stops working too.
    current_user.session_epoch = (current_user.session_epoch or 0) + 1
    db.session.commit()
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
            description_es=(form.description_es.data or "").strip() or None,
            is_active=form.is_active.data,
            sort_order=form.sort_order.data or 0,
        )
        extra_files, remove_ids, problem = _extra_photo_problem(None)
        if problem:
            flash(problem, "error")
            return render_template("admin/product_form.html", form=form, mode="new")
        if form.image.data:
            product.image_filename = _save_product_image(form.image.data)
        _sync_variants(product)
        if not product.variants:
            flash(t("Add at least one shade with a stock quantity."), "error")
            return render_template("admin/product_form.html", form=form, mode="new")
        _apply_extra_photos(product, extra_files, remove_ids)
        db.session.add(product)
        db.session.commit()
        flash(t('"{name}" was added.', name=product.name), "success")
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
        product.description_es = (form.description_es.data or "").strip() or None
        product.is_active = form.is_active.data
        product.sort_order = form.sort_order.data or 0
        extra_files, remove_ids, problem = _extra_photo_problem(product)
        if problem:
            db.session.rollback()
            flash(problem, "error")
            return render_template("admin/product_form.html", form=form, mode="edit", product=product)
        if form.image.data:
            product.image_filename = _save_product_image(form.image.data)
        stock_changes = _sync_variants(product)
        if not product.variants:
            flash(t("Add at least one shade with a stock quantity."), "error")
            return render_template("admin/product_form.html", form=form, mode="edit", product=product)
        _apply_extra_photos(product, extra_files, remove_ids)
        product.updated_at = datetime.utcnow()
        db.session.flush()
        _apply_stock_changes(stock_changes)
        db.session.commit()
        flash(t('"{name}" was updated.', name=product.name), "success")
        return redirect(url_for("admin.products_list"))

    return render_template("admin/product_form.html", form=form, mode="edit", product=product)


@admin_bp.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required
def product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    name = product.name
    # A piece that appears on any order is hidden, not erased: the order history
    # (and any cancel / stock return) must keep pointing at the right product.
    on_orders = OrderItem.query.filter(
        (OrderItem.product_id == product.id) |
        OrderItem.variant_id.in_([v.id for v in product.variants] or [-1])).first()
    if on_orders is not None:
        product.is_active = False
        db.session.commit()
        flash(t('"{name}" is on past orders, so it was hidden from the shop instead of deleted.', name=name), "success")
        return redirect(url_for("admin.products_list"))
    extra_files = [i.filename for i in product.extra_images]
    WishlistItem.query.filter_by(product_id=product.id).delete()
    db.session.delete(product)
    db.session.commit()
    for fn in extra_files:
        _delete_product_file(fn)
    flash(t('"{name}" was deleted.', name=name), "success")
    return redirect(url_for("admin.products_list"))


# --- Journal ------------------------------------------------------------------

def _delete_journal_image(filename):
    if filename:
        path = os.path.join(current_app.root_path, "static", "images", "journal", os.path.basename(filename))
        try:
            os.remove(path)
        except OSError:
            pass


@admin_bp.route("/journal")
@login_required
def journal_list():
    posts = JournalPost.query.order_by(JournalPost.created_at.desc()).all()
    return render_template("admin/journal_list.html", posts=posts)


@admin_bp.route("/journal/new", methods=["GET", "POST"])
@login_required
def journal_new():
    form = JournalForm()
    if form.validate_on_submit():
        post = JournalPost(
            title=form.title.data.strip(),
            slug=unique_slug(form.title.data),
            excerpt=(form.excerpt.data or "").strip() or None,
            body=form.body.data.strip(),
            title_es=(form.title_es.data or "").strip() or None,
            excerpt_es=(form.excerpt_es.data or "").strip() or None,
            body_es=(form.body_es.data or "").strip() or None,
            is_published=form.is_published.data,
        )
        if post.is_published:
            post.published_at = datetime.utcnow()
        if form.image.data:
            post.cover_image = _save_product_image(form.image.data, "journal")
        db.session.add(post)
        db.session.commit()
        flash(t('"{name}" was saved and published.', name=post.title) if post.is_published else t('"{name}" was saved as a draft.', name=post.title), "success")
        return redirect(url_for("admin.journal_list"))
    return render_template("admin/journal_form.html", form=form, mode="new")


@admin_bp.route("/journal/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def journal_edit(post_id):
    post = JournalPost.query.get_or_404(post_id)
    form = JournalForm(obj=post)
    if form.validate_on_submit():
        post.title = form.title.data.strip()
        post.excerpt = (form.excerpt.data or "").strip() or None
        post.body = form.body.data.strip()
        post.title_es = (form.title_es.data or "").strip() or None
        post.excerpt_es = (form.excerpt_es.data or "").strip() or None
        post.body_es = (form.body_es.data or "").strip() or None
        if form.is_published.data and not post.is_published and not post.published_at:
            post.published_at = datetime.utcnow()
        post.is_published = form.is_published.data
        if form.image.data:
            _delete_journal_image(post.cover_image)
            post.cover_image = _save_product_image(form.image.data, "journal")
        elif form.remove_image.data and post.cover_image:
            _delete_journal_image(post.cover_image)
            post.cover_image = None
        post.updated_at = datetime.utcnow()
        db.session.commit()
        flash(t('"{name}" was updated.', name=post.title), "success")
        return redirect(url_for("admin.journal_list"))
    return render_template("admin/journal_form.html", form=form, mode="edit", post=post)


@admin_bp.route("/journal/<int:post_id>/delete", methods=["POST"])
@login_required
def journal_delete(post_id):
    post = JournalPost.query.get_or_404(post_id)
    title = post.title
    _delete_journal_image(post.cover_image)
    db.session.delete(post)
    db.session.commit()
    flash(t('"{name}" was deleted.', name=title), "success")
    return redirect(url_for("admin.journal_list"))


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

            if not stock.take(variant.id, qty):
                db.session.rollback()
                db.session.refresh(variant)
                flash(t("Only {n} of {item} left in stock - reduce the quantity and try again.",
                        n=variant.stock_quantity, item=f"{product.name} ({variant.shade})"), "error")
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
            added_any = True

        if not added_any:
            flash(t("Add at least one product to the order."), "error")
            return render_template("admin/order_form.html", form=form, products=products,
                                    variants_by_product=variants_by_product)

        db.session.add(order)
        db.session.commit()
        flash(t("Order #{id} for {name} was created.", id=order.id, name=order.customer_name), "success")
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

        flash_extra = ""
        if new_status != old_status:
            # Claim the change first: if someone else already moved this order (another
            # tab, the automatic unpaid clean-up) we stop instead of moving stock twice.
            if not stock.claim_status(order, (old_status,), new_status):
                db.session.rollback()
                flash(t("This order was changed by someone else just now. Please check it and try again."), "error")
                return redirect(url_for("admin.order_detail", order_id=order.id))
        if old_status != "cancelled" and new_status == "cancelled":
            for item in order.items:
                if item.variant_id:
                    stock.put_back(item.variant_id, item.quantity)
            flash_extra = " " + t("Stock was returned for its items.")
        elif old_status == "cancelled" and new_status != "cancelled":
            short_items = []
            for item in order.items:
                if item.variant_id and db.session.get(ProductVariant, item.variant_id):
                    if not stock.take_allow_negative(item.variant_id, item.quantity):
                        short_items.append(f"{item.product_name} ({item.shade})")
            if short_items:
                flash(t("Warning: reactivating this order pushed stock negative for: {items}. Double check inventory.", items=", ".join(short_items)), "error")
        else:
            flash_extra = ""

        order.payment_status = form.payment_status.data
        if form.delivery_fee.data is not None:
            order.delivery_fee = form.delivery_fee.data
        order.tracking_number = (form.tracking_number.data or "").strip() or None
        order.notes = (form.notes.data or "").strip() or None
        order.updated_at = datetime.utcnow()
        db.session.commit()
        flash(t("Order #{id} updated.", id=order.id) + flash_extra, "success")
    else:
        flash(t("Could not update order - please check the form."), "error")
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
        flash(t("Customer details updated."), "success")
    else:
        flash(t("Could not update customer details - please check the form."), "error")
    return redirect(url_for("admin.order_detail", order_id=order.id))


@admin_bp.route("/orders/<int:order_id>/delete", methods=["POST"])
@login_required
def order_delete(order_id):
    """Permanently erase an order (e.g. an order made in error, or a data-deletion request).
    Stock is returned only for orders that were still open."""
    order = Order.query.get_or_404(order_id)
    # Claim the order first so stock goes back exactly once, even if it is being
    # cancelled somewhere else at the same moment.
    if stock.claim_status(order, ("pending", "processing"), "cancelled"):
        for item in order.items:
            if item.variant_id:
                stock.put_back(item.variant_id, item.quantity)
    number = order.id
    db.session.delete(order)
    db.session.commit()
    flash(t("Order #{id} was permanently deleted.", id=number), "success")
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
    flash(t("Account {email} was deleted. Its past orders were kept as records.", email=email), "success")
    return redirect(url_for("admin.customers_list"))


# --- Newsletter / sneak-peek subscribers ---------------------------------------

@admin_bp.route("/subscribers")
@login_required
def subscribers_list():
    subscribers = Subscriber.query.order_by(Subscriber.consented_at.desc()).all()
    return render_template("admin/subscribers_list.html", subscribers=subscribers)


def _csv_safe(value):
    """Stop spreadsheet formula injection: a subscriber who types a name like
    =HYPERLINK(...) must not get it executed when the owner opens the CSV in Excel."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@admin_bp.route("/subscribers/export.csv")
@login_required
def subscribers_export():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["email", "name", "newsletter", "sneak_peek", "consent_source", "consented_at"])
    for s in Subscriber.query.filter(Subscriber.unsubscribed_at.is_(None)).order_by(Subscriber.email):
        if s.newsletter or s.sneak_peek:
            writer.writerow([_csv_safe(s.email), _csv_safe(s.name), int(s.newsletter), int(s.sneak_peek),
                             _csv_safe(s.consent_source), s.consented_at.strftime("%Y-%m-%d") if s.consented_at else ""])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=verayah-subscribers.csv"})


@admin_bp.route("/subscribers/<int:sub_id>/delete", methods=["POST"])
@login_required
def subscriber_delete(sub_id):
    sub = Subscriber.query.get_or_404(sub_id)
    if sub.unsubscribed_at is not None:
        # Keep the address on the do-not-contact list so nobody can sign them up again
        # by typing it into a form. Everything else about them is erased.
        sub.name = None
        sub.newsletter = sub.sneak_peek = False
        db.session.commit()
        flash(t("Subscriber removed. Their address stays on the unsubscribed list so they are not signed up again."), "success")
        return redirect(url_for("admin.subscribers_list"))
    db.session.delete(sub)
    db.session.commit()
    flash(t("Subscriber removed."), "success")
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
    flash(t("Message marked as handled.") if msg.handled else t("Message marked as new."), "success")
    return redirect(url_for("admin.messages_list"))


@admin_bp.route("/messages/<int:msg_id>/delete", methods=["POST"])
@login_required
def message_delete(msg_id):
    msg = ContactMessage.query.get_or_404(msg_id)
    db.session.delete(msg)
    db.session.commit()
    flash(t("Message deleted."), "success")
    return redirect(url_for("admin.messages_list"))
