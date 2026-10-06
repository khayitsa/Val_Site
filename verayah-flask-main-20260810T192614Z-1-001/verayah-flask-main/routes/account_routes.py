"""Optional shopper accounts: saved details, wishlist, delete-my-account."""
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request
)

from models import db, Customer, Product, WishlistItem
from forms.public_forms import (
    RegisterForm, CustomerLoginForm, AccountDetailsForm, DeleteAccountForm
)
from services.customer_auth import (
    current_customer, login_customer, logout_customer, customer_required, safe_next
)
from services.newsletter import record_consent
from services.security import customer_login_throttle, signup_throttle

account_bp = Blueprint("account", __name__, url_prefix="/account")


@account_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_customer():
        return redirect(url_for("account.dashboard"))
    form = RegisterForm()
    if request.method == "GET":
        form.email.data = request.args.get("email", "")
        form.name.data = request.args.get("name", "")
    if form.validate_on_submit():
        key = "reg:" + (request.remote_addr or "?")
        if signup_throttle.blocked(key):
            flash("Too many sign-ups in a short time. Please try again later.", "error")
            return render_template("account/register.html", form=form)
        signup_throttle.record(key)
        email = form.email.data.strip().lower()
        if Customer.query.filter_by(email=email).first():
            # Same message whether or not the email exists would need email
            # sending; for now be clear and helpful.
            flash("An account with that email already exists. Please sign in instead.", "error")
            return render_template("account/register.html", form=form)
        customer = Customer(email=email, name=form.name.data.strip(),
                            phone=(form.phone.data or "").strip() or None)
        customer.set_password(form.password.data)
        db.session.add(customer)
        record_consent(email, customer.name, form.marketing.data, form.marketing.data, source="account")
        db.session.commit()
        login_customer(customer)
        flash("Your account is ready.", "success")
        return redirect(url_for("account.dashboard"))
    return render_template("account/register.html", form=form)


@account_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_customer():
        return redirect(url_for("account.dashboard"))
    form = CustomerLoginForm()
    nxt = safe_next(request.args.get("next") or request.form.get("next"))
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        tkey = email + "|" + (request.remote_addr or "?")
        if customer_login_throttle.blocked(tkey):
            flash("Too many failed attempts. Please wait 15 minutes and try again.", "error")
            return render_template("account/login.html", form=form, next=nxt)
        customer = Customer.query.filter_by(email=email).first()
        if customer and customer.check_password(form.password.data):
            customer_login_throttle.clear(tkey)
            login_customer(customer)
            return redirect(nxt or url_for("account.dashboard"))
        customer_login_throttle.record(tkey)
        flash("Incorrect email or password.", "error")
    return render_template("account/login.html", form=form, next=nxt)


@account_bp.route("/logout", methods=["POST"])
def logout():
    logout_customer()
    flash("You have been signed out.", "info")
    return redirect(url_for("home"))


@account_bp.route("/", methods=["GET", "POST"])
@customer_required
def dashboard():
    customer = current_customer()
    form = AccountDetailsForm(obj=customer)
    if form.validate_on_submit():
        customer.name = form.name.data.strip()
        customer.phone = (form.phone.data or "").strip() or None
        customer.shipping_address = (form.shipping_address.data or "").strip() or None
        customer.shipping_city = (form.shipping_city.data or "").strip() or None
        db.session.commit()
        flash("Your details were updated.", "success")
        return redirect(url_for("account.dashboard"))
    orders = sorted(customer.orders, key=lambda o: o.created_at, reverse=True)
    return render_template("account/dashboard.html", form=form, customer=customer, orders=orders,
                           delete_form=DeleteAccountForm())


@account_bp.route("/wishlist")
@customer_required
def wishlist():
    items = (WishlistItem.query.filter_by(customer_id=current_customer().id)
             .order_by(WishlistItem.created_at.desc()).all())
    products = [i.product for i in items if i.product and i.product.is_active]
    return render_template("account/wishlist.html", products=products)


@account_bp.route("/wishlist/toggle/<int:product_id>", methods=["POST"])
def wishlist_toggle(product_id):
    customer = current_customer()
    if not customer:
        flash("Sign in or create a free account to save favourites. You can still buy without one.", "info")
        return redirect(url_for("account.login", next=safe_next(request.form.get("next")) or url_for("products")))
    product = db.session.get(Product, product_id)
    if not product or not product.is_active:
        return redirect(url_for("products"))
    existing = WishlistItem.query.filter_by(customer_id=customer.id, product_id=product_id).first()
    if existing:
        db.session.delete(existing)
        flash(f"Removed {product.name} from your wishlist.", "info")
    else:
        db.session.add(WishlistItem(customer_id=customer.id, product_id=product_id))
        flash(f"Saved {product.name} to your wishlist.", "success")
    db.session.commit()
    return redirect(safe_next(request.form.get("next")) or url_for("products"))


@account_bp.route("/delete", methods=["POST"])
@customer_required
def delete_account():
    customer = current_customer()
    form = DeleteAccountForm()
    if form.validate_on_submit() and customer.check_password(form.password.data):
        # The account, saved details and wishlist are erased. Past orders are
        # kept as business records but are unlinked from the account.
        for order in customer.orders:
            order.customer_id = None
        db.session.delete(customer)
        db.session.commit()
        logout_customer()
        flash("Your account has been deleted.", "info")
        return redirect(url_for("home"))
    flash("Password was incorrect, so your account was not deleted.", "error")
    return redirect(url_for("account.dashboard"))
