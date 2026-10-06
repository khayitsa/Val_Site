"""Public pages that are not shopping: legal/policy pages, contact, newsletter."""
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request

from models import db, ContactMessage, Subscriber
from forms.public_forms import ContactForm, SubscribeForm
from services.newsletter import record_consent
from services.security import signup_throttle

main_bp = Blueprint("main", __name__)


# --- Policy pages ----------------------------------------------------------
# Wording is supplied by Leah / the lawyers. Until it lands, the templates in
# templates/legal/ carry clearly-marked DRAFT text built from the owner's answers.

@main_bp.route("/privacy")
def privacy():
    return render_template("legal/privacy.html")


@main_bp.route("/terms")
def terms():
    return render_template("legal/terms.html")


@main_bp.route("/shipping-returns")
def shipping_returns():
    return render_template("legal/shipping_returns.html")


@main_bp.route("/cookies")
def cookies():
    return render_template("legal/cookies.html")


@main_bp.route("/care")
def care():
    return render_template("legal/care.html")


# --- Contact form ----------------------------------------------------------

def _back(anchor=""):
    # Only ever redirect to a page on this site.
    ref = request.referrer or ""
    host = request.host_url
    if ref.startswith(host):
        return redirect(ref.split("#")[0] + anchor)
    return redirect(url_for("home") + anchor)


@main_bp.route("/contact", methods=["GET", "POST"])
def contact():
    form = ContactForm()
    if request.method == "GET":
        return redirect(url_for("home") + "#contact")
    key = request.remote_addr or "?"
    if signup_throttle.blocked("contact:" + key):
        flash("Too many messages in a short time. Please try again later.", "error")
        return _back("#contact")
    if form.validate_on_submit():
        signup_throttle.record("contact:" + key)
        db.session.add(ContactMessage(
            name=form.name.data.strip(),
            email=form.email.data.strip().lower(),
            inquiry_type=form.inquiry_type.data,
            message=form.message.data.strip(),
        ))
        db.session.commit()
        first = form.name.data.strip().split(" ")[0]
        flash(f"Thank you, {first} - your message has been received and we will be in touch.", "success")
        return _back("#contact")
    flash("Please check your name, email and message and try again.", "error")
    return _back("#contact")


# --- Newsletter / sneak-peek club -------------------------------------------

@main_bp.route("/subscribe", methods=["GET", "POST"])
def subscribe():
    form = SubscribeForm()
    if request.method == "POST":
        from_footer = request.form.get("source") == "footer"
        if from_footer:
            # The footer box exists only to join the lists, so joining it is
            # the explicit choice; the full page lets people pick one list.
            form.newsletter.data = True
            form.sneak_peek.data = True
        key = request.remote_addr or "?"
        if signup_throttle.blocked("sub:" + key):
            flash("Too many sign-ups in a short time. Please try again later.", "error")
            return redirect(url_for("main.subscribe"))
        if form.validate_on_submit():
            if not (form.newsletter.data or form.sneak_peek.data):
                flash("Please tick at least one list to join.", "error")
                return render_template("subscribe.html", form=form)
            signup_throttle.record("sub:" + key)
            record_consent(form.email.data, form.name.data,
                           form.newsletter.data, form.sneak_peek.data,
                           source="footer" if from_footer else "subscribe_page")
            db.session.commit()
            flash("You're on the list. You can unsubscribe at any time from any email we send.", "success")
            return redirect(url_for("main.subscribe_thanks"))
        if from_footer:
            flash("Please enter a valid email address.", "error")
            return _back()
    return render_template("subscribe.html", form=form)


@main_bp.route("/subscribe/thanks")
def subscribe_thanks():
    return render_template("subscribe_thanks.html")


@main_bp.route("/unsubscribe/<token>", methods=["GET", "POST"])
def unsubscribe(token):
    sub = Subscriber.query.filter_by(unsubscribe_token=token).first_or_404()
    if request.method == "POST":
        sub.unsubscribed_at = datetime.utcnow()
        sub.newsletter = False
        sub.sneak_peek = False
        db.session.commit()
        return render_template("unsubscribed.html", done=True)
    return render_template("unsubscribed.html", done=False, sub=sub)
