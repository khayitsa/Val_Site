"""Plain-text email notifications (new orders, contact messages).

Optional by design: with no MAIL_* settings in .env nothing is sent and the
site behaves exactly as before. A failure to send is logged and swallowed -
an email problem must never stop a customer from placing an order.
"""
import logging
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app

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

def _money(value):
    return f"${float(value):,.2f}"


def _item_lines(order):
    return "\n".join(
        f"  - {i.product_name} ({i.shade}) x {i.quantity}  {_money(i.unit_price * i.quantity)}"
        for i in order.items
    )


def _delivery_line(order):
    if order.delivery_method == "collection":
        return "Delivery: collection ($0.00)"
    if order.delivery_fee and order.delivery_fee > 0:
        return f"Delivery: {_money(order.delivery_fee)}"
    return "Delivery: fee to be confirmed"


def notify_owner_new_order(order, admin_url):
    """Tell the shop owner a website order has come in."""
    to = notify_address()
    method = "Yappy" if order.payment_method == "yappy" else "bank transfer"
    where = "Collection" if order.delivery_method == "collection" else f"{order.shipping_address}, {order.shipping_city}"
    body = (
        f"New website order #{order.id}\n\n"
        f"Customer: {order.customer_name}\n"
        f"Email:    {order.customer_email or '-'}\n"
        f"Phone:    {order.customer_phone or '-'}\n"
        f"Deliver:  {where}\n"
        f"Payment:  {method} (not yet paid)\n\n"
        f"Items:\n{_item_lines(order)}\n\n"
        f"{_delivery_line(order)}\n"
        f"Total so far: {_money(order.total())}\n"
        + (f"\nCustomer note: {order.notes}\n" if order.notes else "")
        + f"\nOpen the order: {admin_url}\n"
    )
    return send(to, f"New order #{order.id} - {_money(order.total())}", body,
                reply_to=order.customer_email or None)


def confirm_to_customer(order, order_url, site):
    """Send the customer a copy of what they ordered and how to pay."""
    if not order.customer_email:
        return False
    if order.payment_method == "yappy" and site.get("yappy"):
        pay = (f"How to pay: send {_money(order.total())} by Yappy to {site['yappy']}, "
               f"using order #{order.id} as the reference.")
    elif order.payment_method == "bank_transfer" and site.get("bank_details"):
        pay = (f"How to pay: transfer {_money(order.total())} with reference order #{order.id}:\n"
               f"{site['bank_details']}")
    else:
        pay = ("How to pay: we will send you the payment details shortly, "
               "by email and on WhatsApp.")
    contact = site.get("whatsapp") and f"WhatsApp https://wa.me/{site['whatsapp']}" or f"phone {site.get('phone', '')}"
    first = (order.customer_name or "").split(" ")[0] or "there"
    body = (
        f"Hi {first},\n\n"
        f"Thank you for your order with Verayah. Your pieces are reserved for you; "
        f"your order is confirmed once payment is received.\n\n"
        f"Order #{order.id}\n{_item_lines(order)}\n\n"
        f"{_delivery_line(order)}\n"
        f"Total: {_money(order.total())}\n\n"
        f"{pay}\n"
        f"Then send your payment proof to us on {contact}.\n\n"
        f"You can check the status of your order any time here:\n{order_url}\n\n"
        f"With love,\nVerayah\n"
    )
    return send(order.customer_email, f"Your Verayah order #{order.id}", body)


def notify_owner_new_message(msg_obj):
    """Tell the shop owner someone used the contact form."""
    to = notify_address()
    body = (
        f"New message from the Verayah website\n\n"
        f"From:    {msg_obj.name} <{msg_obj.email}>\n"
        f"Topic:   {msg_obj.inquiry_type}\n\n"
        f"{msg_obj.message}\n\n"
        f"Reply to this email to answer them directly.\n"
    )
    return send(to, f"Website message: {msg_obj.inquiry_type}", body, reply_to=msg_obj.email)
