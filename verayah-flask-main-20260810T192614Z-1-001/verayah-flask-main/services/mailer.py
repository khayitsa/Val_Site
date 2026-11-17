"""Plain-text email notifications (new orders, contact messages).

Optional by design: with no MAIL_* settings in .env nothing is sent and the
site behaves exactly as before. A failure to send is logged and swallowed -
an email problem must never stop a customer from placing an order.
"""
import logging
import re
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app

from services.i18n import translate, current_lang

log = logging.getLogger(__name__)

SEND_TIMEOUT = 8  # seconds; keeps checkout quick even if the mail server is slow


def _cfg():
    return current_app.config.get("MAIL") or {}


def is_configured():
    c = _cfg()
    return bool(c.get("host") and c.get("user") and c.get("password") and c.get("from"))


def notify_address():
    return (_cfg().get("notify") or "").strip()


def send(to, subject, body, reply_to=None):
    """Send one plain-text email. Returns True on success, False otherwise. Never raises."""
    if not to or not is_configured():
        return False
    c = _cfg()
    try:
        msg = EmailMessage()
        msg["From"] = c["from"]
        msg["To"] = to
        # EmailMessage refuses newlines in headers, which blocks header injection.
        msg["Subject"] = " ".join(str(subject).split())[:200]
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body)

        port = int(c.get("port") or 587)
        ctx = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(c["host"], port, timeout=SEND_TIMEOUT, context=ctx) as s:
                s.login(c["user"], c["password"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(c["host"], port, timeout=SEND_TIMEOUT) as s:
                s.starttls(context=ctx)
                s.login(c["user"], c["password"])
                s.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see module docstring
        # Log the type only - never the password or message content.
        log.error("Email to %s could not be sent: %s", to, type(exc).__name__)
        return False


# --- Message builders --------------------------------------------------------
# Customer emails follow the language the customer was browsing in. Emails to the
# shop owner use OWNER_LANG (English by default). Spanish wording lives in
# services/translations_es.py like the rest of the site.

def _first_name(full_name, fallback):
    """The word used in "Hi <name>,". The name was typed by whoever placed the order,
    who may not be the person the email goes to, so keep it to plain letters: no links,
    line breaks or long text can ride along in a message that comes from Verayah."""
    for word in (full_name or "").split():
        word = re.sub(r"[^\w'\u2019-]|_", "", word)[:30]
        if word:
            return word
    return fallback


def _money(value):
    return f"${float(value):,.2f}"


def _owner_lang():
    return (current_app.config.get("OWNER_LANG") or "en").lower()


def _item_lines(order, lang=None):
    return "\n".join(
        f"  - {i.product_name} ({i.shade}) x {i.quantity}  {_money(i.unit_price * i.quantity)}"
        for i in order.items
    )


def _delivery_line(order, lang=None):
    if order.delivery_method == "collection":
        return translate("Delivery: collection ($0.00)", lang)
    if order.delivery_fee and order.delivery_fee > 0:
        return translate("Delivery: {fee}", lang, fee=_money(order.delivery_fee))
    return translate("Delivery: fee to be confirmed", lang)


def notify_owner_new_order(order, admin_url):
    """Tell the shop owner a website order has come in."""
    to = notify_address()
    L = _owner_lang()
    method = translate("Yappy", L) if order.payment_method == "yappy" else translate("bank transfer", L)
    where = translate("Collection", L) if order.delivery_method == "collection" else f"{order.shipping_address}, {order.shipping_city}"
    body = (
        translate("New website order #{id}", L, id=order.id) + "\n\n"
        f"{translate('Customer', L)}: {order.customer_name}\n"
        f"{translate('Email', L)}: {order.customer_email or '-'}\n"
        f"{translate('Phone', L)}: {order.customer_phone or '-'}\n"
        f"{translate('Deliver', L)}: {where}\n"
        f"{translate('Payment', L)}: {translate('{method} (not yet paid)', L, method=method)}\n\n"
        f"{translate('Items', L)}:\n{_item_lines(order)}\n\n"
        f"{_delivery_line(order, L)}\n"
        f"{translate('Total so far', L)}: {_money(order.total())}\n"
        + (f"\n{translate('Customer note', L)}: {order.notes}\n" if order.notes else "")
        + f"\n{translate('Open the order', L)}: {admin_url}\n"
    )
    return send(to, translate("New order #{id} - {total}", L, id=order.id, total=_money(order.total())), body,
                reply_to=order.customer_email or None)


def confirm_to_customer(order, order_url, site):
    """Send the customer a copy of what they ordered and how to pay."""
    if not order.customer_email:
        return False
    L = current_lang()
    total = _money(order.total())
    if order.payment_method == "yappy" and site.get("yappy"):
        pay = translate("How to pay: send {total} by Yappy to {number}, using order #{id} as the reference.", L,
                        total=total, number=site["yappy"], id=order.id)
    elif order.payment_method == "bank_transfer" and site.get("bank_details"):
        pay = translate("How to pay: transfer {total} with reference order #{id}:", L,
                        total=total, id=order.id) + f"\n{site['bank_details']}"
    else:
        pay = translate("How to pay: we will send you the payment details shortly, by email and on WhatsApp.", L)
    contact = (translate("WhatsApp {url}", L, url=f"https://wa.me/{site['whatsapp']}") if site.get("whatsapp")
               else translate("phone {phone}", L, phone=site.get("phone", "")))
    insta = (translate(" or by Instagram direct message {url}", L, url=site["instagram"])
             if site.get("instagram") else "")
    first = _first_name(order.customer_name, translate("there", L))
    body = (
        translate("Hi {name},", L, name=first) + "\n\n"
        + translate("Thank you for your order with Verayah. Please pay right away: we do not hold unpaid orders, and if payment does not arrive the order is cancelled and the pieces go back on sale. Your order is confirmed once payment is received.", L) + "\n\n"
        + translate("Order #{id}", L, id=order.id) + f"\n{_item_lines(order)}\n\n"
        f"{_delivery_line(order, L)}\n"
        f"{translate('Total', L)}: {total}\n\n"
        f"{pay}\n"
        + translate("Then send your payment proof to us on {contact}{insta}.", L, contact=contact, insta=insta) + "\n\n"
        + translate("You can check the status of your order any time here:", L) + f"\n{order_url}\n\n"
        + translate("With love,", L) + "\nVerayah\n"
    )
    return send(order.customer_email, translate("Your Verayah order #{id}", L, id=order.id), body)


def notify_owner_new_message(msg_obj):
    """Tell the shop owner someone used the contact form."""
    to = notify_address()
    L = _owner_lang()
    topic = translate(msg_obj.inquiry_type, L)
    body = (
        translate("New message from the Verayah website", L) + "\n\n"
        f"{translate('From', L)}: {msg_obj.name} <{msg_obj.email}>\n"
        f"{translate('Topic', L)}: {topic}\n\n"
        f"{msg_obj.message}\n\n"
        + translate("Reply to this email to answer them directly.", L) + "\n"
    )
    return send(to, translate("Website message: {topic}", L, topic=topic), body, reply_to=msg_obj.email)
