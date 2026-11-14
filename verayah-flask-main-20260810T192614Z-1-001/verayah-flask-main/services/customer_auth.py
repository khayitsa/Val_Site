"""Optional shopper accounts.

Deliberately NOT Flask-Login: that session belongs to the admin portal, and
keeping shoppers on a separate session key means a shopper account can never
be mistaken for an admin one.
"""
import hashlib
import hmac
from functools import wraps
from urllib.parse import urlsplit

from flask import session, redirect, url_for, flash, request, g, current_app

from models import db, Customer


def _stamp(customer):
    """A signed fingerprint of one specific account.

    The session stores the customer's id AND this stamp. SQLite can hand a
    deleted account's id to a brand-new customer, so the id alone is not enough
    to say "same account": the stamp (id + creation time + password hash,
    keyed with the app secret) only matches the account it was issued for.
    """
    raw = f"{customer.id}|{customer.created_at}|{customer.password_hash}".encode()
    key = current_app.secret_key or b""
    if isinstance(key, str):
        key = key.encode()
    return hmac.new(key, raw, hashlib.sha256).hexdigest()[:32]


def current_customer():
    if "customer" in g.__dict__:
        return g.customer
    cid = session.get("customer_id")
    customer = db.session.get(Customer, cid) if cid else None
    if customer is not None:
        stamp = session.get("customer_stamp") or ""
        if not hmac.compare_digest(stamp, _stamp(customer)):
            customer = None  # id reused by a different account, or an old session
    g.customer = customer
    if cid and customer is None:
        session.pop("customer_id", None)
        session.pop("customer_stamp", None)
    return g.customer


def login_customer(customer):
    # Keep the shopper's bag across login, but start a fresh session otherwise
    # (protects against session fixation).
    cart = session.get("cart")
    session.clear()
    if cart:
        session["cart"] = cart
    session["customer_id"] = customer.id
    session["customer_stamp"] = _stamp(customer)
    g.customer = customer


def logout_customer():
    session.pop("customer_id", None)
    session.pop("customer_stamp", None)
    g.customer = None


def customer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_customer():
            flash("Please sign in to use your account. You never need an account to buy.", "info")
            return redirect(url_for("account.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def safe_next(target):
    """Only allow redirects to paths on this site.

    Rejects anything with control characters, spaces or backslashes: browsers
    and Werkzeug silently drop tabs/newlines from URLs, so "/<TAB>/evil.com"
    would otherwise turn into the off-site address "//evil.com".
    """
    if not target or not isinstance(target, str):
        return None
    if any(ord(ch) < 0x21 or ord(ch) == 0x7F or ch == "\\" for ch in target):
        return None
    if not target.startswith("/") or target.startswith("//"):
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        return None
    return target
