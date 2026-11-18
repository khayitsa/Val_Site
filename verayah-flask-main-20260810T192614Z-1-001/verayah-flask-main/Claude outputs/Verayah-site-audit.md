# Verayah site audit — bugs and security

Audited 17 Nov 2026. This covers the Flask project in `verayah-flask-main`: the app, routes, models, forms, services, templates, JS, scripts and dependencies.

## How I checked

- Read all Python, templates and JS by hand.
- Ran Bandit, pyflakes and pip-audit.
- Ran the app on a throw-away copy (Python 3.13, latest allowed dependencies) and drove it with about 90 scripted checks:
  - every `/admin` URL as an anonymous visitor;
  - CSRF on every POST;
  - checkout, stock and cancel flows;
  - uploads (SVG disguised as PNG, a fake JPEG, a 20000×20000 decompression bomb);
  - XSS and open-redirect probes;
  - accounts, newsletter, journal and admin actions;
  - 222 page loads in English and Spanish.

**Not covered:** your real host, SMTP, several workers running at once, how pages look in a browser (CSS), and Python 3.14, which your `__pycache__` suggests you use. The `instance/verayah.db` in the folder is an older copy than the code, so your live database may differ.

## Verdict

The core shop logic is sound. Prices come from the database and stock is decremented atomically. Cancelling never returns stock twice, uploads are strictly validated, output is escaped everywhere (no template uses the `|safe` filter), and CSRF is enforced on every POST. Dependencies have no known vulnerabilities.

The real problems are (1) deployment defaults that fail open, (2) a handful of admin-side bugs, and (3) decisions that depend on where you host. Part 1 is fixed in the accompanying patch. Part 2 needs your call.

---

## Part 1 — Fixed in `verayah-audit-fixes.patch` (each one tested)

| # | Severity | Problem | Fix |
|---|---|---|---|
| 1 | **High** | Your `.env` has `SECRET_KEY` and `FLASK_ENV` both blank. The app invented a random key per process, so with 2+ workers every form fails with CSRF errors and logins drop. | Outside `FLASK_ENV=development` the app now refuses to start without `SECRET_KEY`. |
| 2 | **High** | The session cookie was not marked `Secure` unless you remembered `FLASK_ENV=production`. | `Secure` is now the default. Local development opts out with `FLASK_ENV=development`. |
| 3 | Medium | Editing a product and deleting every shade row saved successfully, leaving a product with **zero shades**. The "at least one shade" check looked at the stale in-memory list. | The check now reads the submitted rows. |
| 4 | Medium | Two shades with the same name on one product gave an unhandled **500** (database unique constraint). | Pre-check plus a friendly message. A commit-time fallback catches clashes with a shade kept for order history. |
| 5 | Medium | Forms older than 1 hour died with a bare "400 Bad Request – CSRF token expired". Long product edits lost their data. | Token lifetime is 8 hours, and any CSRF failure now shows "your session expired" and returns to the form. |
| 6 | Medium | Email links (order confirmation, owner alert) are built from the request's `Host` header when `PUBLIC_BASE_URL` is blank, so a forged Host can point them at another site. Only matters once email is on. | New `ALLOWED_HOSTS` setting rejects other hosts. A startup warning appears if mail is on and `PUBLIC_BASE_URL` is blank. |
| 7 | Low | Customer login took 64 ms for a real email versus 3 ms for an unknown one, which reveals who has an account. | A dummy password check is run so both take the same time (75 ms vs 75 ms). Also applied to admin login. |
| 8 | Low | Posting a made-up `variant_id` to `/cart/update` put a phantom line in the bag and inflated the cart badge. | Ignored. |
| 9 | Low | Admin "new order" with a non-numeric product id gave a 500. | Skipped safely. |
| 10 | Low | No custom 500 page. No `Permissions-Policy`. Private pages (`/admin`, `/account`, `/cart`, `/checkout`, `/order/…`) could be indexed. | Friendly `500.html` (with Spanish text), `Permissions-Policy`, `Cross-Origin-Opener-Policy` and `X-Robots-Tag: noindex`. |
| 11 | Low | `python app.py` always ran with `debug=True` (Werkzeug debugger, remote code execution if exposed). | Debug is now only on when `FLASK_ENV=development`. |
| 12 | Low | `scripts/update_stock_2026_09.py` sets stock for 11 shades and **zeroes every other shade**. Run on the live DB by mistake, it wipes your inventory. | Now needs `--i-know-this-overwrites-stock`. |
| 13 | Low | Housekeeping. `static/js/script.js` was a dead leftover from a different (tattoo-style portfolio) template and no page loaded it; had it been loaded it would fake "Message sent" on the first form it finds. `.gitignore` didn't cover the 22 MB `static.zip` or `*.db`. No production server was listed in `requirements.txt`. Hosts that hand out `postgres://` URLs would crash. | Removed `script.js`. Extended `.gitignore`. Added `gunicorn`. `postgres://` is converted automatically. Added `pool_pre_ping`. README and `.env.example` updated to match. |

### Applying the patch

From the project root, with a clean working tree:

```
git apply --check verayah-audit-fixes.patch
git apply verayah-audit-fixes.patch
git diff --stat
```

If Windows line endings make `--check` complain about whitespace, add `--ignore-whitespace`.

**Two things you must do after applying:**

1. For local work add `FLASK_ENV=development` to your `.env`. Otherwise the app now refuses to start, which is intentional.
2. On any real host, set a real `SECRET_KEY`.

I did not commit or push anything. Review the diff and commit it yourself.

---

## Part 2 — Open items that need your decision

**A. The 4-hour auto-cancel of unpaid orders (business risk).**
Payment is by Yappy or bank transfer, and someone has to mark the order "paid" by hand. Any website order still unpaid after `UNPAID_HOLD_HOURS` (default 4) is cancelled and its stock goes back on sale. I confirmed this on a test order. A customer who pays at 10 pm and an owner who confirms next morning will lose the order. Consider 24–48 h, or only cancelling orders with no payment proof. The Terms of Sale text says 4 hours, so change both together.

**B. Login lock-out can be bypassed when there is no proxy in front.**
The app trusts one `X-Forwarded-For` hop (`TRUST_PROXY=1` by default). If visitors reach the app directly, an attacker can send a different fake IP with each attempt. I confirmed 30 wrong passwords never locked out. Set `TRUST_PROXY=0` if there is no reverse proxy, and `1` if there is one. Behind a proxy that appends to `X-Forwarded-For` (every common host does) this is not exploitable. Lock-outs are also in memory and per worker, so several workers multiply the allowed attempts. Use Flask-Limiter with Redis if you scale out.

**C. Hosting must keep your data.**
Orders live in `instance/verayah.db` (SQLite) and uploaded photos in `static/images/products|journal`. On hosts with a throw-away disk (most free tiers, containers) both vanish on every redeploy. You need a persistent volume plus backups, or Postgres for the database plus persistent or object storage for photos. Postgres needs `psycopg[binary]` added to `requirements.txt` (a commented line is ready).

**D. Admin account.**
The `val` admin and one order record (name and address fields) sit in the DB copy that travelled in your zip and Downloads folder. Before launch, start with a fresh DB, create the admin with `flask create-admin`, and use a new strong password. There is no 2FA and no idle timeout: a signed session cookie works for up to 31 days, though logout does invalidate it.

**E. No content-security-policy.**
I found no XSS (names, descriptions, contact messages and journal markup were all escaped), so this is defence-in-depth. Adding a CSP means moving 3 inline `<script>` blocks and 6 inline `onsubmit="confirm(...)"` handlers into `site.js`. I can do that as a follow-up.

**F. Spam and sign-up abuse.**
Contact, subscribe and register have only a per-IP limit of 10 per hour. A CAPTCHA (Cloudflare Turnstile is free) or a honeypot field would stop distributed spam.
- The newsletter has no double opt-in, so anyone can subscribe someone else's address.
- Registering with an existing email says it exists (it's flagged in the code as a known trade-off).

**G. Smaller items.**
- `datetime.utcnow()` is deprecated in Python 3.12+ (warns now, works).
- A few `Query.get()` legacy calls remain.
- Unused imports (`session`, `time`, `abort`, `secure_filename`).
- `admin_routes._sync_variants` has a local variable `stock` that shadows the `stock` module (harmless today).
- A replaced product photo is never deleted from disk, and the main photo isn't removed when a product is deleted.
- Lists in admin load unpaginated.
- Requirements use ranges, not pinned versions. Consider a lock file.

**H. Page weight.**
By my search of templates, scripts and the product table, the 84 `img_NN.jpg` files, the roughly 90-photo `products/new_shoot/` folder and `IMG_0252.jpg` aren't referenced. Some of those files are 1–3.4 MB. `Logo.png` is 2.5 MB and also looks unreferenced. I did not read the CSS, so confirm nothing there uses them before deleting. Keep them out of the deploy either way.

**I. Launch content, not code.**
- The legal pages are still draft: the banner is on until `LEGAL_DRAFT=0`.
- `YAPPY_NUMBER`, `BANK_DETAILS`, `DELIVERY_FEE`, `RETURNS_ADDRESS` and the Instagram URL are blank or placeholders, so checkout shows "to be confirmed".

---

## Before you go live — host-agnostic checklist

1. **Environment variables:**
   - `SECRET_KEY` (32+ random bytes)
   - `FLASK_ENV` blank
   - `ALLOWED_HOSTS=yourdomain,www.yourdomain`
   - `PUBLIC_BASE_URL=https://yourdomain`
   - `TRUST_PROXY` (1 or 0, see B)
   - `DATABASE_URL`, if not using SQLite
   - `MAIL_*`, if you want emails
2. **Run it with a real server:** `gunicorn app:app --workers 1 --threads 4` keeps the in-memory lock-out and stale-hold sweeper coherent. If you use more workers, see B.
3. **HTTPS only,** with http redirected to https at the host or CDN. HSTS is already sent over https.
4. **Persistent storage and backups** (see C).
5. **Serve `/static` from the `static/` folder only.** Never alias the project root, so `.env`, `instance/` and `static.zip` can't be fetched. I confirmed the app itself doesn't expose them.
6. **Fresh DB and new admin password;** leave out `static.zip`, the dev DB and the unused images (see D and H).
7. **Place one test order end to end** with mail on. Decide on A. Then fill in the payment and delivery settings (I).
8. Run `python scripts/check_translations.py` after any wording change.

## Checked and found solid

- Every `/admin` route (GET and POST) refuses an anonymous visitor.
- All 12 POST endpoints I tested (shop, account, newsletter, contact, admin login/logout) reject a missing CSRF token.
- Order totals ignore tampered form prices.
- Stock reduces atomically. Over-ordering is refused. Cancelling twice returns stock once. Reactivating takes it again.
- Order confirmation uses an unguessable token. The sequential order id returns 404.
- Uploads: SVG-as-PNG, a JPEG header with garbage, a `.php` file and a 379 KB 20000×20000 bomb were all rejected. Accepted photos are re-encoded to a random-named JPEG.
- XSS probes in product names, descriptions, contact messages and the journal renderer (`javascript:` links, attribute breakouts) came out escaped.
- Open-redirect probes (`//evil`, `/\evil`, tab tricks, absolute URLs) were all neutralised.
- `.env`, `instance/*.db`, `app.py` and `/static/../` were not reachable over HTTP.
- Copying the admin cookie and then logging out invalidates the copy.
- Unsubscribe needs a POST. Re-subscribing through the form can't undo an opt-out. CSV export guards against spreadsheet formula injection.
- `pip-audit`: no known vulnerabilities in the declared dependencies today.
- Bandit's only real finding was the debug flag (fixed). Its `Markup` warnings are false positives because values are escaped by `Markup.format`.
