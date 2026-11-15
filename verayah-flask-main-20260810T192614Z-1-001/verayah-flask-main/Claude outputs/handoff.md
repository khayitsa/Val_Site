# Verayah – Handoff

Last updated: Sat 2026-11-14, evening. For picking the project up in a fresh session. Replaces the earlier handoff of the same day.

## 1. What this is

Flask jewellery e-commerce site for Val/Leah (Stratos), brand **Verayah**, handmade in Panama.
- Repo: `khayitsa/Val_Site` on GitHub
- Live review copy: `khayitsa100.pythonanywhere.com` (the live database lives on PythonAnywhere, not in the repo). Val has the link and no login, so anything deployed there is effectively public.
- Owner/dev: Khayanda, a web developer who runs git herself.
- Stack: Flask, Jinja2, Flask-SQLAlchemy (SQLite), Flask-Login (admin), Flask-WTF CSRF, werkzeug, Pillow. Shopper state is in a signed cookie session (`customer_id` + `customer_stamp`). `db.create_all()` runs on import, so new tables need no migration.
- **Client goal: Val wants to launch on 1 December 2026**, and wants to run a full test order from start to finish first.

Project root on her computer:
`C:\Users\user\Downloads\VAL\verayah-flask-main-20260810T192614Z-1-001-20260914T215303Z-1-001\verayah-flask-main-20260810T192614Z-1-001\verayah-flask-main`

## 2. Working agreements (follow these)

- **Do not commit or push for her.** Give her the git commands to run, with an explicit file list (not `git add .`).
- **Do not list Claude as a contributor** on GitHub (no Co-Authored-By trailers in commands you give her).
- **"Don't approve changes without running them past me."** Show the change (diff or description) and get a clear yes before writing to her project folder.
- **Do not add products** unless she asks again. Current product data (e.g. "Peace in Mind" at $11,100 / stock 55) is test data; she said it doesn't matter until launch.
- Mail is deliberately off for now (she'll add `MAIL_*` later).
- Leah (Stratos) is strict about legal compliance. Nothing that could be a licence or legal problem should reach GitHub or the live site.

## 3. Done

**Earlier rounds:** order and message emails (off until `MAIL_*` set), customer order-status page, auto-shrinking uploads (Pillow 13), lighter logo, ocean-blue hero, multiple photos per product, black logo.

**Security audit fixes:** 7 files (`services/customer_auth.py`, `services/newsletter.py`, `routes/main_routes.py`, `templates/subscribe_thanks.html`, `routes/shop_routes.py`, `app.py`, `.env.example`). Khayanda says she has already run the commit/push and deployed these. Known effects: shoppers were signed out once; the Host-header fix only works once `PUBLIC_BASE_URL` is set. Quick post-deploy check still worth doing: put 7+ pieces in the bag and press Checkout, it should return to the bag with a "limited to 6 pieces" message.

**This session, written to her project folder:**
- `templates/index.html`: the five "Why Verayah / Crafted with Intention" icons redesigned as inline SVG (same 40x40 grid, 1.2 stroke, teal via `.why-icon`, round caps). Handmade in Panama = hand holding a gem, Original Designs = pencil with sparkles, Seasonal Collections = sun over waves, Thoughtful Materials = pearl and gem, Made to Last = two interlocked rings. She approved the design. **Deploy status unconfirmed**; she still needs to commit/push/pull+Reload if she hasn't. Suggested: `git add templates/index.html static/css/fonts.css` then commit and push.
- `static/css/fonts.css`: two `@font-face` rules appended for 'Angel Bandit' (`../fonts/angel-bandit-regular.woff2`) and 'Wiraile' (`../fonts/wiraile-regular.woff2`), with a comment saying they are inactive. The font files do not exist and nothing in `style.css` uses these families, so the site is unchanged. Safe to push, or to leave out.

**Nothing else was written.** `.gitignore`, `style.css` and the font files were all proposed but not changed.

## 4. Brand fonts (paused)

From Val's brand kit (Canva screenshots): **Title = Angel Bandit Demo, 42; Subtitle = Wiraile, 36; Heading = Angel Bandit Demo, 28.** Body font not shown (site uses Jost).

Khayanda dropped this for now ("nevermind"). If it resumes:
- Fonts are stored in `static/fonts/` (8 woff2 files: Cormorant Garamond x5, Jost x3), registered in `static/css/fonts.css`, imported by `style.css` line 6. `--display` (Cormorant Garamond) and `--body` (Jost) are set at the top of `style.css`.
- Proposed mapping (not confirmed): Title -> `.hero-copy h1`, `.products-hero h1`, `.page-section h1`; Heading -> section `h2`s (collections, craft, custom, story, products, about, contact, products page, `.page-section h2`); Subtitle -> card-level h3s (`.collection-card-overlay h3`, `.why-card h3`) and `.footer-tagline`. Keep Cormorant for nav, product names, prices, buttons; Jost for body. Cormorant stays as fallback. Open questions: what "Subtitle" means on the site, and whether body stays Jost.
- **Licence:** these are demo fonts and Val has to buy the real ones (web-use licence). Do not put demo font files on GitHub or the live PythonAnywhere site (public, so it would be redistribution). Proposed guard: add `static/fonts/angel-bandit*` and `static/fonts/wiraile*` to `.gitignore`. Preview option: render screenshots locally for Val, no deploy.
- Demo fonts often lack digits, `$` and punctuation.

## 5. Val's wishes and business rules (from the WhatsApp group, read 2026-11-14)

**Wants:** launch 1 Dec; test order first; several photos per product (model + item) and ability to swap pictures herself in the admin; launch-shoot close-ups (not landscape) and a friend's photos; black logo (done); pretty, not tacky; newsletter, wishlist, "sneak peek club"; Instagram promotions; reviews and customer photos; accounts optional, guest checkout always. Some products were reported missing on 7 Nov.

**Her rules (26 Sept):** Panama only, Uno Express, 2-3 days courier / 4-5 days overall, collection available; Yappy or bank transfer; 18k gold-coated chains, river pearls, natural crystals; "water resistant, NOT waterproof"; waist chains S/M/L; personalised pieces arranged with her, $20 deposit; cancellations get store credit; no change-of-mind returns (each piece unique), sizing adjustments as a courtesy; faulty item = exchange; she said warranty **10 days from shipping**; Verayah pays return shipping; she says she doesn't pay taxes; she has no RUC or aviso de operación ("Non"); she handles all customer queries. Business email: `verayahpty@gmail.com` (given 28 Sept; `BUSINESS_EMAIL` env likely still blank). WhatsApp digits for `WHATSAPP_NUMBER`: `50769040901`.

**Unanswered by Val:** delivery fee; whether 4-5 days includes courier time; balance due date on personalised orders; cancel/change cut-off; lost/damaged parcels ("would need guidance"); international orders; door vs branch delivery by Uno Express; returns address.

## 6. Site vs Val's rules (legal pages)

Matches: Panama-only Uno Express, Yappy/bank transfer, no change-of-mind returns, sizing courtesy, water resistant not waterproof, materials, S/M/L, $20 deposit, Verayah pays return shipping, guest checkout with optional accounts.

Differences (in `templates/legal/shipping_returns.html` and `terms.html`):
1. Warranty: site promises 3 months from delivery (legal default), free repair within 30 days, applies to sale and personalised items. Val said 10 days.
2. Store credit: Shipping page says refunds are in money, "never forced into store credit"; Terms says cancelled orders "can receive store credit". The two pages disagree.
3. Promises Val never made: refund if 7+ days late, replace-or-refund for lost/damaged parcels, 48-hour damage window, 2 working day replies, refunds within 10 days.
4. "You receive an invoice for every order": Val may not be able to issue invoices (no aviso/RUC).
5. Tax line says "not decided"; Val says she doesn't pay taxes.
6. Warranty claims waive the "must not be visibly used" condition she wanted.

**Legal findings (news/ACODECO sources, not statute text; not legal advice; Leah's check or a Panamanian lawyer should confirm before `LEGAL_DRAFT=0`):** the legal warranty on new goods is 3 months, though a shorter one can be agreed "depending on nature and price"; remedies are repair, replacement or refund of the amount paid; the statutory withdrawal right (3 business days) only covers home sales and it is unclear whether courier-delivered online orders count (key question for the lawyer); voluntary exchanges are a courtesy, not an obligation; the aviso de operación is a mandatory registry (B/.15 for a natural person, online via Panama Emprende) and does not exempt tax obligations; ACODECO treats the invoice as the main proof of purchase.

**Proposed wording changes (NOT applied, awaiting a yes):**
- Keep the 3-month legal warranty; use Val's 10 days as the window to report damage on arrival or "not as described".
- Customer cancels before dispatch: store credit. Money refund when it's our fault (can't deliver, out of stock, faulty, not as described). Fix the Terms/Shipping inconsistency.
- "Not as described" returns: piece unworn and in packaging. Defect claims stay exempt.
- Lead faulty-item remedy with replacement; keep repair and refund as fallbacks.
- Replace the invoice promise with "you receive an order confirmation with your order number".
- Drop "not decided" on taxes, just say prices are in US dollars, until her accountant confirms the tax position.
- Keep lost/damaged wording but have Val confirm; drop the 7-days-late rule and the 2-working-days reply promise unless she wants them.
- Needs Val or her accountant: warranty length, aviso/invoicing, delivery fee, balance due date, cancel/change cut-off.

## 7. Payment flow (how it works now)

Checkout takes no money. The customer picks Yappy or bank transfer, places the order, and the confirmation page shows `YAPPY_NUMBER` or `BANK_DETAILS` (both blank for now, so it says "we will send you the details shortly"). The customer sends proof on WhatsApp; Val marks the order paid in the admin. Stock is reserved atomically at order time with no expiry for unpaid orders. She earlier declined stale-order handling; her answer on how long to hold unpaid orders should decide whether an auto-release is wanted.

**Drafted but not yet sent:** a plain-text message to Val (two versions, "payment only" and "payment + policy", no hearts) covering Yappy number/type, bank details, proof destination, how long to hold an unpaid order, delivery fee and whether it is paid in the same transfer, deposit/balance/refundability for personalised pieces, refund method, receipts/invoices, cancel cut-off, lost/damaged parcels, store credit rule, aviso/RUC. Re-draft from this section if needed.

## 8. Open items

**Her checklist:**
- Deploy the icon change (`templates/index.html`) and optionally `static/css/fonts.css`; then `git pull` and Reload on PythonAnywhere. No `pip install`, no DB change.
- Change the live admin password (still the default, and it was posted in the group chat on 2 and 5 Nov).
- Send Val the payment/policy questions and bring back her answers.
- Set server environment values: real `SECRET_KEY`, `FLASK_ENV=production`, `LEGAL_DRAFT=0` (only after the legal wording is final), `DELIVERY_FEE`, `YAPPY_NUMBER`, `BANK_DETAILS`, `WHATSAPP_NUMBER`, `BUSINESS_EMAIL`, `RETURNS_ADDRESS`; when mail is enabled also `MAIL_*`, `NOTIFY_EMAIL`, `PUBLIC_BASE_URL`; optional `MAX_UNITS_PER_ORDER`, `INSTAGRAM_URL`.

**Next things I could do (ask which):**
1. Draft exact before/after text for the legal wording changes above.
2. Write a test-order checklist for Val (order, payment instructions, marking paid in admin, status changes through delivery).
3. Launch settings sheet: server env values, marked confirmed vs waiting on Val.
4. Check whether reviews/customer photos exist on the site (Val wants them); not checked.
5. Launch photos swap (needs to know which images go where).
6. Audit leftovers (not fixed, only if she asks): double opt-in for newsletter (needs mail), auto-expiry of unpaid-order stock reservations, atomic admin stock updates, data-erasure lifecycle, throttle / `X-Forwarded-For` ProxyFix identity, hardening notes (session lifetime, CSP, `debug=True` under `python app.py`, lockfile, `.gitignore` gaps).

## 9. How I work on her files (device workflow)

There is no shell on her computer, so:
1. `device_stage_files` copies files into `/mnt/user-data/uploads/verayah-flask-main/<relative path>`.
2. Edit a scratch copy, test it, copy the result to `/mnt/user-data/outputs/verayah-flask-main/<same relative path>`.
3. Show her the diff and wait for sign-off.
4. `device_commit_files` with `stagedPath` and `expectedMtimeMs` (Windows paths with escaped backslashes). Re-stage right before committing so the mtime guard passes.

## 10. Test tooling (in the cloud sandbox; may not survive)

- Venv: `/home/claude/tenv` (Python 3.13). Scratch sites: `/home/claude/fixsite` (fixed copy), `/home/claude/audit/verayah` (original audited copy, don't modify), `/home/claude/testsite`.
- Scripts in `/home/claude/`: `fix_tests.py` (43 checks for the security fixes, all pass), `shop_test2.py`, `admin_test2.py`, `t3.py`, `new_tests.py`, `new_tests2.py`, `gal_test.py`, `t413.py`.
- Known stale-test failures (test drift, not site bugs): `admin_test2` "message appears in admin", `t3` "delete order asks for confirmation", `new_tests` logo/shrink checks (missing `static/logos/Logo-web.png`), `new_tests2` (missing `static/images/shoot2/collection-hero.jpg`).
- Icon preview and chat export from this session: `/home/claude/icons/` (`final_preview.png`, `new.json`) and `/home/claude/valchat/`.
- Audit outputs (not part of her project): `~/security-audit-skill/verayah/run-1/`. Diff of the security fixes: `/mnt/user-data/outputs/verayah-security-fixes.diff`.

## 11. Gotchas

- Uploaded images are shrunk automatically; Pillow 13 is required.
- Admin routes use Flask-Login; customer accounts use the separate session helpers in `services/customer_auth.py`.
- `db.create_all()` won't alter existing tables, so any column change on the live DB needs a manual migration step for her.
- The `.env` file sits in the project root and is gitignored; do not read or print it.
- `static.zip` (about 22 MB) sits in the project root; leave it alone.
