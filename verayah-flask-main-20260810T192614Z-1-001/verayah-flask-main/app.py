import os
import click
from flask import Flask, render_template, session, request, abort, flash, redirect, url_for
from flask_login import LoginManager, current_user
from flask_wtf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

try:  # load .env so SECRET_KEY etc. work without setting host variables
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from models import db, AdminUser, Product, WishlistItem, JournalPost
from models.schema import upgrade_schema
from services import cart as bag
from services.journal import render_body
from services.customer_auth import current_customer

app = Flask(__name__)

# Behind a hosting proxy (PythonAnywhere etc.) trust ONE proxy hop for the real
# visitor IP and https scheme. Set TRUST_PROXY=0 if you run without a proxy.
if os.environ.get("TRUST_PROXY", "1") != "0":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0)

# --- Core security config ---------------------------------------------
# SECRET_KEY signs session cookies and CSRF tokens - it must come from the
# environment in production. We only fall back to a random one-off key so
# the app doesn't crash locally; that fallback changes every restart, which
# means it can never be used to forge a session, but it also logs everyone
# out on restart - set a real SECRET_KEY env var for real deployments.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or os.urandom(32).hex()
if not os.environ.get("SECRET_KEY"):
    # A random per-process key logs everyone out on restart and breaks CSRF
    # tokens when several workers run. Set SECRET_KEY in the host's environment.
    print("WARNING: SECRET_KEY is not set - using a temporary random key.", flush=True)

basedir = os.path.abspath(os.path.dirname(__file__))
# "or" (not a get-default) so a blank DATABASE_URL= line copied from
# .env.example falls back to the local SQLite file instead of crashing.
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL") or (
    f"sqlite:///{os.path.join(basedir, 'instance', 'verayah.db')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Cookie hardening
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Only send cookies over HTTPS once deployed behind TLS. Locally (http://)
# this must stay False or the login cookie will silently never be set.
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"

# 25 MB cap on a single upload request, so a full-size phone photo is fine but
# no one can fill the disk via the admin image upload field. Accepted photos
# are shrunk before saving (see services/images.py).
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024

# --- Shop / business settings (all optional, set in .env) -------------
# Nothing here is a secret. Anything left blank is shown to shoppers as
# "to be confirmed" rather than guessed.
# Most pieces one website order may contain. Stock is reserved the moment an order
# is placed (before payment), so this stops one order tying up the whole shop.
# Larger orders are placed by contacting the shop. Blank/invalid = 6.
try:
    app.config["MAX_UNITS_PER_ORDER"] = max(1, int(os.environ.get("MAX_UNITS_PER_ORDER") or 6))
except ValueError:
    app.config["MAX_UNITS_PER_ORDER"] = 6
# The public address of the shop, e.g. https://verayah.example. When set, links in
# emails use it instead of whatever Host header the request arrived with.
_base = (os.environ.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
app.config["PUBLIC_BASE_URL"] = _base if _base.startswith(("http://", "https://")) else ""
app.config["DELIVERY_FEE"] = os.environ.get("DELIVERY_FEE", "")          # e.g. 5.00 - courier fee within Panama
app.config["SITE"] = {
    "name": "Verayah",
    "operator": os.environ.get("BUSINESS_OPERATOR", "Valentina Garcia"),
    "email": os.environ.get("BUSINESS_EMAIL", ""),
    "phone": os.environ.get("BUSINESS_PHONE", "+507 6904-0901"),
    "whatsapp": os.environ.get("WHATSAPP_NUMBER", ""),                    # digits only, e.g. 50769040901
    "address": os.environ.get("BUSINESS_ADDRESS", "Panama City, Panama"),
    "returns_address": os.environ.get("RETURNS_ADDRESS", ""),
    "yappy": os.environ.get("YAPPY_NUMBER", ""),
    "bank_details": os.environ.get("BANK_DETAILS", ""),
    "instagram": os.environ.get("INSTAGRAM_URL", ""),
    "pinterest": os.environ.get("PINTEREST_URL", ""),
    "tiktok": os.environ.get("TIKTOK_URL", ""),
    # Show a "draft wording" banner on the policy pages until the final copy is in.
    "legal_draft": os.environ.get("LEGAL_DRAFT", "1") != "0",
}

# --- Email notifications (optional) -------------------------------------
# Leave MAIL_* blank to send nothing. For Gmail use host smtp.gmail.com,
# port 587, your address as the user, and an "app password" (not your login).
try:
    _mail_port = int(os.environ.get("MAIL_PORT") or 587)
except ValueError:
    _mail_port = 587
_mail_user = os.environ.get("MAIL_USER", "").strip()
app.config["MAIL"] = {
    "host": os.environ.get("MAIL_HOST", "").strip(),
    "port": _mail_port,
    "user": _mail_user,
    "password": os.environ.get("MAIL_PASSWORD", ""),
    "from": os.environ.get("MAIL_FROM", "").strip() or _mail_user,
    # Where new-order and contact-form alerts go (defaults to the business email).
    "notify": (os.environ.get("NOTIFY_EMAIL", "") or os.environ.get("BUSINESS_EMAIL", "")).strip(),
}

db.init_app(app)
csrf = CSRFProtect(app)

login_manager = LoginManager(app)
login_manager.login_view = "admin.login"
login_manager.login_message = "Please log in to access the admin portal."


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(AdminUser, int(user_id))


from routes.admin_routes import admin_bp
from routes.main_routes import main_bp
from routes.shop_routes import shop_bp
from routes.account_routes import account_bp
app.register_blueprint(admin_bp)
app.register_blueprint(main_bp)
app.register_blueprint(shop_bp)
app.register_blueprint(account_bp)


@app.context_processor
def inject_site():
    customer = current_customer()
    wishlist_ids = set()
    if customer:
        wishlist_ids = {w.product_id for w in WishlistItem.query.filter_by(customer_id=customer.id)}
    return {
        "site": app.config["SITE"],
        "cart_count": bag.count(),
        "customer": customer,
        "wishlist_ids": wishlist_ids,
        "delivery_fee": app.config["DELIVERY_FEE"],
    }


@app.errorhandler(404)
def not_found(_err):
    return render_template("404.html"), 404


@app.errorhandler(413)
def too_large(_err):
    """A photo bigger than the upload limit: explain it instead of showing a raw error page."""
    flash("That file is too big (the limit is 60 MB per upload). Please pick fewer or smaller photos and try again.", "error")
    ref = request.referrer or ""
    if ref.startswith(request.host_url):       # only ever go back to a page on this site
        return redirect(ref)
    return redirect(url_for("admin.dashboard"))


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.is_secure:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    # Pages with a personal bag/account/order must never be cached by shared proxies.
    if resp.mimetype == "text/html":
        resp.headers.setdefault("Cache-Control", "private, no-cache")
    return resp


# --- Public site routes -------------------------------------------------

@app.route('/')
def home():
    featured_products = Product.query.filter_by(is_active=True).order_by(Product.sort_order).limit(4).all()
    return render_template('index.html', featured_products=featured_products)

@app.route('/products')
def products():
    products = Product.query.filter_by(is_active=True).order_by(Product.sort_order, Product.name).all()
    return render_template('products.html', products=products)

app.jinja_env.filters["journal_body"] = render_body


@app.route('/journal')
def journal():
    posts = (JournalPost.query.filter_by(is_published=True)
             .order_by(JournalPost.published_at.desc()).all())
    return render_template('journal.html', posts=posts)


@app.route('/journal/<slug>')
def journal_post(slug):
    post = JournalPost.query.filter_by(slug=slug).first_or_404()
    # Drafts are only visible to a logged-in admin (as a preview).
    if not post.is_published and not current_user.is_authenticated:
        abort(404)
    return render_template('journal_post.html', post=post)


# --- CLI: create/reset the admin account --------------------------------
# Run with: flask create-admin
# Never hardcode admin credentials in source - this prompts for them and
# hashes the password before it ever touches the database.
@app.cli.command("create-admin")
@click.option("--username", prompt=True)
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
def create_admin(username, password):
    """Create (or update the password of) an admin user."""
    username = username.strip()
    if len(password) < 8:
        click.echo("Password must be at least 8 characters.")
        return
    user = AdminUser.query.filter_by(username=username).first()
    if user:
        user.set_password(password)
        click.echo(f"Password updated for existing admin '{username}'.")
    else:
        user = AdminUser(username=username)
        user.set_password(password)
        db.session.add(user)
        click.echo(f"Admin '{username}' created.")
    db.session.commit()


with app.app_context():
    os.makedirs(os.path.join(basedir, "instance"), exist_ok=True)
    db.create_all()
    upgrade_schema(db)   # adds new order columns to an existing database, never drops data

if __name__ == '__main__':
    app.run(debug=True, port=5001)