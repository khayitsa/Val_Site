"""
Database models for Verayah.

- AdminUser: staff accounts that can log into /admin
- Product:   the real product catalog (replaces the old hardcoded list
             in templates/products.html)
- Order / OrderItem: orders placed on the website (guest or account) or
             logged by hand in the admin portal
- Customer:  OPTIONAL shopper account (saved details + wishlist). Shoppers
             can always check out as a guest instead.
- WishlistItem: products a signed-in customer saved
- Subscriber: newsletter / sneak-peek club sign-ups (no account needed;
             marketing consent is stored separately per list)
- ContactMessage: messages sent through the website contact form
"""
import secrets
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class AdminUser(UserMixin, db.Model):
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, raw_password):
        # scrypt (werkzeug's default) - slow-by-design hashing, good against
        # brute force / rainbow tables. Never store plaintext passwords.
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(80), nullable=False)  # Body Chain, Hand Chain, Waist Chain, Anklet, Earring
    price = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    image_filename = db.Column(db.String(255), nullable=False, default="")
    is_active = db.Column(db.Boolean, nullable=False, default=True)  # soft-hide instead of hard delete by default
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    variants = db.relationship("ProductVariant", backref="product", cascade="all, delete-orphan",
                                order_by="ProductVariant.shade")

    def price_display(self):
        return f"${self.price:,.2f}"

    def shades_display(self):
        """e.g. 'Blushed, Seafoam, Oceanic' - only shades currently in stock,
        for the public product page."""
        in_stock = [v.shade for v in self.variants if v.stock_quantity > 0]
        return ", ".join(in_stock) if in_stock else "Currently out of stock"

    def total_stock(self):
        return sum(v.stock_quantity for v in self.variants)

    def in_stock(self):
        return self.total_stock() > 0


class ProductVariant(db.Model):
    """One shade of one product, with its own stock count.

    e.g. Trinity Hand Chain has three variants: Blushed, Seafoam, Oceanic -
    each tracked and sold independently.
    """
    __tablename__ = "product_variants"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    shade = db.Column(db.String(80), nullable=False)
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint("product_id", "shade", name="uq_product_shade"),)


class Order(db.Model):
    __tablename__ = "orders"

    STATUSES = ["pending", "processing", "shipped", "delivered", "cancelled"]

    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(150), nullable=False)
    customer_email = db.Column(db.String(150), nullable=True)
    customer_phone = db.Column(db.String(50), nullable=True)

    shipping_address = db.Column(db.String(255), nullable=False)
    shipping_city = db.Column(db.String(100), nullable=False)
    shipping_country = db.Column(db.String(100), nullable=False)

    # Optional link to a shopper account. NULL for guest orders.
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)

    # Unguessable token so a guest can view their own confirmation page
    # without an account (never expose the sequential order id for that).
    public_token = db.Column(db.String(64), nullable=True, unique=True, index=True,
                             default=lambda: secrets.token_urlsafe(24))

    source = db.Column(db.String(20), nullable=False, default="admin")       # "website" | "admin"
    delivery_method = db.Column(db.String(20), nullable=False, default="courier")  # "courier" | "collection"
    delivery_fee = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    payment_method = db.Column(db.String(20), nullable=True)                 # "yappy" | "bank_transfer"
    payment_status = db.Column(db.String(20), nullable=False, default="unpaid")  # "unpaid" | "paid"

    status = db.Column(db.String(20), nullable=False, default="pending")
    tracking_number = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")

    def subtotal(self):
        return sum((item.unit_price * item.quantity for item in self.items), start=0)

    def total(self):
        return self.subtotal() + (self.delivery_fee or 0)


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)
    variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=True)

    # Snapshot the name/shade/price at time of order so editing/deleting a
    # product or variant later never rewrites order history.
    product_name = db.Column(db.String(150), nullable=False)
    shade = db.Column(db.String(80), nullable=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)

    product = db.relationship("Product")
    variant = db.relationship("ProductVariant")


class Customer(db.Model):
    """Optional shopper account. Stores only what the shopper chose to save."""
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)  # stored lowercase
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    shipping_address = db.Column(db.String(255), nullable=True)
    shipping_city = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    orders = db.relationship("Order", backref="customer")
    wishlist = db.relationship("WishlistItem", backref="customer", cascade="all, delete-orphan")

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)


class WishlistItem(db.Model):
    __tablename__ = "wishlist_items"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship("Product")

    __table_args__ = (db.UniqueConstraint("customer_id", "product_id", name="uq_wishlist_customer_product"),)


class Subscriber(db.Model):
    """Newsletter / sneak-peek club sign-up. No account required.

    Consent is recorded per list, with when and from where it was given, so
    the business can show what each person agreed to.
    """
    __tablename__ = "subscribers"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)  # stored lowercase
    name = db.Column(db.String(150), nullable=True)
    newsletter = db.Column(db.Boolean, nullable=False, default=False)
    sneak_peek = db.Column(db.Boolean, nullable=False, default=False)
    consent_source = db.Column(db.String(50), nullable=True)   # footer | subscribe_page | checkout | account
    consented_at = db.Column(db.DateTime, default=datetime.utcnow)
    unsubscribe_token = db.Column(db.String(64), unique=True, nullable=False,
                                  default=lambda: secrets.token_urlsafe(24))
    unsubscribed_at = db.Column(db.DateTime, nullable=True)

    @property
    def active(self):
        return self.unsubscribed_at is None and (self.newsletter or self.sneak_peek)


class ContactMessage(db.Model):
    __tablename__ = "contact_messages"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    inquiry_type = db.Column(db.String(50), nullable=False, default="General Inquiry")
    message = db.Column(db.Text, nullable=False)
    handled = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
