# Verayah — Flask site + admin portal

## Setup

```bash
pip install -r requirements.txt --break-system-packages   # or use a venv
```

Copy `.env.example` to `.env` and fill in a real `SECRET_KEY` (see below).

## First-time database setup

The database is created automatically the first time the app runs. To load
your current 10 products into it:

```bash
python scripts/seed_products.py
```

Safe to re-run — it skips any product whose name already exists.

## Create your admin login

Never hardcode admin credentials in the source. Create your account with:

```bash
flask create-admin
```

It will prompt for a username and password (min. 8 characters) and store
the password as a salted hash, never in plain text. Run the same command
again with an existing username to reset that account's password.

## Running the site

```bash
python app.py
```

- Public site: http://127.0.0.1:5001/
- Admin portal: http://127.0.0.1:5001/admin/login

## What the admin portal does

- **Products** (`/admin/products`) — add, edit, delete, and show/hide
  products. Changes appear on the live `/products` page and the homepage
  immediately — there is no separate "publish" step.
- **Orders & shipping** (`/admin/orders`) — log orders taken via WhatsApp/DM/
  in person, track status (pending → processing → shipped → delivered /
  cancelled), and record courier tracking numbers.

## Security notes — read before deploying

- **SECRET_KEY**: set a real, random `SECRET_KEY` environment variable in
  production. Without one, the app falls back to a random key that changes
  every restart (safe, but logs everyone out each time you redeploy).
  Generate one with: `python -c "import secrets; print(secrets.token_hex(32))"`
- **HTTPS**: set `FLASK_ENV=production` once the site is served over HTTPS.
  This flips the session cookie to `Secure` (HTTPS-only). Leave it unset for
  local development over plain `http://`, or login cookies won't be set.
- **`instance/` and `.env` are gitignored** — the database (real customer
  names, addresses, order history) and secrets must never be committed.
  Back up `instance/verayah.db` separately and securely instead.
- **Login throttling** is in-memory (5 failed attempts → 15 min lockout per
  username). This resets on restart and only works correctly with a single
  process. If you ever deploy with multiple worker processes, replace it
  with Flask-Limiter + Redis.
- **Uploads**: product photos are capped at 5 MB, validated to actual image
  files (not just their filename extension), and saved under a random
  filename — the browser's original filename is never trusted or reused.
- **Run behind a real WSGI server** (gunicorn/waitress) and HTTPS in
  production — `python app.py` uses Flask's development server, which is
  not designed for production traffic.

## Shop features (guest checkout, optional accounts, newsletter)

- **Guest checkout** (`/cart`, `/checkout`): nobody needs an account to buy. Orders are
  saved as `source = website`, payment `unpaid`, and appear in the admin under
  *Orders & Shipping*. Payment is by Yappy or bank transfer, arranged after ordering.
  Stock is reserved when the order is placed and returned if the order is cancelled.
- **Optional accounts** (`/account/...`): save delivery details, a wishlist and see past orders.
  Customers can edit their details and delete their own account (past orders are kept as
  business records but unlinked). Shopper sessions are separate from the admin login.
- **Newsletter / sneak-peek club** (`/subscribe`, footer box): no account needed, separate
  from checkout and accounts. Marketing boxes are never pre-ticked. Each subscriber stores
  which list(s), when and where they agreed, and has an unsubscribe link
  (`/unsubscribe/<token>`). Admin: *Newsletter* page with CSV export.
- **Contact form** saves to *Messages* in the admin (it no longer just pretends to send).
- **Policy pages**: `/privacy`, `/terms`, `/shipping-returns`, `/cookies`, `/care`, linked in
  the footer. Their wording lives in `templates/legal/` and is DRAFT text built from the
  owner's answers, with `not decided` markers. Replace it with Leah's final copy, then set
  `LEGAL_DRAFT=0` to hide the draft banner.
- **Cookies**: only one essential `session` cookie (bag, sign-in, CSRF). No analytics or ad
  pixels, so no consent banner is needed. If you add any tracking later, update
  `templates/legal/cookies.html` and add a consent control that matches it.
- **Fonts** are self-hosted in `static/fonts/` (no requests to Google).

### Business settings
Set these in `.env` (see `.env.example`): `DELIVERY_FEE`, `BUSINESS_EMAIL`, `WHATSAPP_NUMBER`,
`YAPPY_NUMBER`, `BANK_DETAILS`, `RETURNS_ADDRESS`, social links. Anything blank shows as
"not decided" / "confirmed with your payment details" instead of being guessed.

### Database upgrade
On startup the app adds the new order columns to your existing SQLite database
(`models/schema.py`) and creates the new tables. It only adds, never deletes. Back up
`instance/verayah.db` before the first run anyway.

### Not built yet
Password-reset emails, order/payment emails (no email service is connected, so the owner sees
new orders in the admin), Instagram/WhatsApp marketing, saved sizes/birthdays, reviews.

