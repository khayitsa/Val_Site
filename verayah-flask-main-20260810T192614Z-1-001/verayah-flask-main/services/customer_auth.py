"""Optional shopper accounts.

Deliberately NOT Flask-Login: that session belongs to the admin portal, and
keeping shoppers on a separate session key means a shopper account can never
be mistaken for an admin one.
"""
from functools import wraps

from flask import session, redirect, url_for, flash, request, g

from models import db, Customer


def current_customer():
    if "customer" in g.__dict__:
        return g.customer
    cid = session.get("customer_id")
    g.customer = db.session.get(Customer, cid) if cid else None
    if cid and g.customer is None:
        session.pop("customer_id", None)
    return g.customer


def login_customer(customer):
    # Keep the shopper's bag across login, but start a fresh session otherwise
    # (protects against session fixation).
    cart = session.get("cart")
    session.clear()
    if cart:
        session["cart"] = cart
    session["customer_id"] = customer.id
    g.customer = customer


def logout_customer():
    session.pop("customer_id", None)
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
    """Only allow redirects to paths on this site."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return None
