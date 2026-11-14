# Verayah security audit - REPORT

## 1. Run summary (partial pass)
- **Profile:** `quick` (one hunter wave, one final coverage critic, one fresh verifier per candidate). **This is a partial audit. It does not show the rest of the code is fine.**
- **Target:** Verayah Flask shop, working-tree snapshot of Val_Site/verayah-flask as of 2026-11-14 (no VCS ref; tree hash prefix `9d8a7fada131895f`; matches the files on the owner's device). 67 files, about 1,850 lines of routes/services.
- **Execution:** sandboxed, source-and-local only. All target code ran in an OS sandbox (no network, empty allowlisted environment, read-only source and toolchain, scratch-only writes, low CPU/memory/time limits). Evidence files were promoted into `agents/<id>/artifacts/` by trusted parent-side code only. No live site, PythonAnywhere account, SMTP server or real data was contacted.
- **Agents:** 4 reconnaissance + 5 hunters + 7 verifiers + 1 critic = 17 invocations. No budget was set.
- **Prior runs:** none (no compatible earlier ledger or findings). Nothing carried over.
- **Companions used:** WEB-PROTOCOL-AND-AUTH, CLIENT-SIDE, DATA-ISOLATION-AND-LIFECYCLE, SUPPLY-CHAIN-AND-RELEASE.
- **Process note:** each hunter and verifier received its full prompt as a file (the prompt text is the same blocks the playbook requires) rather than inline.
- **Deferred coverage (accepted by the final critic, not run):** (1) data-erasure lifecycle: what personal data remains after account/order/subscriber/message deletion, plus the admin order-customer rewrite route; (2) rate-limit identity: whether the in-memory throttles can be bypassed through `X-Forwarded-For` / ProxyFix when the app is not behind exactly one appending proxy. Both are explicitly `deferred` in the ledger.

## 2. Security posture
The core of the shop is sound for its size: CSRF protection is app-wide, all database access goes through the ORM, Jinja autoescape is on, the one raw-HTML sink (journal body) held up against 200,000 random inputs, image uploads are fully decoded and re-encoded to JPEG under random names, admin routes all require login, passwords use scrypt hashing, tokens are 192-bit random, and order prices, fees and checkout stock are decided on the server. Nothing found lets an anonymous visitor reach the admin area, read other customers' orders, run code, or alter prices. What turned up are four low-severity issues (one shopper-session weakness, one open redirect, one newsletter consent weakness, one stock-hold abuse) and one deployment-dependent lead. Two admin-only data-integrity bugs were examined and judged not to be security problems.

## 3. Confirmed findings (all low)
| Severity | Title | Boundary | Observed result |
|---|---|---|---|
| low | Stale shopper session cookie authenticates as a different customer after SQLite row-id reuse (`verayah-customer-session-stale-id-reuse-after-account-delete`) | Shopper session -> another customer's account | Cookie of a deleted account loaded the next registrant's dashboard (200) and could edit their name/address |
| low | `safe_next` accepts `/`+TAB prefixes: open redirect after shopper login (`verayah-customer-auth-safe-next-control-char-open-redirect`) | Login redirect -> off-site | `?next=%2F%09%2Fevil.example` gave `302 Location: //evil.example` |
| low | Anyone can re-subscribe an opted-out address without proving mailbox ownership (`newsletter:record_consent-unverified-resubscribe`) | Anonymous visitor -> another person's newsletter consent | Opt-out reversed and consent record overwritten by a third party |
| low | Anonymous guest checkout can reserve all stock with no payment and no expiry (`shop-checkout-unpaid-stock-reservation-uncapped-no-expiry`) | Anonymous visitor -> shop inventory availability | One checkout took stock 12 to 0; other shoppers could not add items |

### 3.1 `verayah-customer-session-stale-id-reuse-after-account-delete`
- **Where:** `services/customer_auth.py:17` (`current_customer`), `models/__init__.py:178` (`Customer.id`), `routes/account_routes.py:137` (`delete_account`), admin `customer_delete`.
- **Principal:** a former shopper (or anyone with a copy of their signed session cookie) after that account was deleted.
- **Reproduction:** register customer A (id 1), keep a copy of its cookie from a second device, delete A, register B (SQLite reuses id 1), then use the old cookie: `GET /account/` shows B's email/name and a CSRF-valid `POST /account/` changes B's name and address.
- **Conditions:** the deleted customer had the highest id, someone registers afterwards, the old cookie was not used in between and is under 31 days old. Admin deletion triggers it without needing the shopper's password.
- **Impact and priority:** read and edit of one other shopper's name, email, phone, address and order list. Rare on a small shop, so low priority, but easy to fix.
- **Smallest fix:** store a random per-customer `session_token` and compare it in `current_customer()` (rotate on creation/deletion), or make the table use SQLite AUTOINCREMENT. Add a test: delete the max-id customer, register a new one, replay the old cookie, expect redirect to login.

### 3.2 `verayah-customer-auth-safe-next-control-char-open-redirect`
- **Where:** `services/customer_auth.py:52` (`safe_next`), used at `routes/account_routes.py:56` and `:67`.
- **Principal:** anonymous attacker who gets a shopper to click a link.
- **Reproduction:** open `/account/login?next=%2F%09%2Fevil.example` and sign in with valid dummy credentials: the response is `302` with `Location: //evil.example`. `//evil.example` and backslash forms are correctly rejected; an LF variant only causes a 500.
- **Impact and priority:** after logging in, the shopper is sent to an attacker's page (phishing risk). No credential or session is passed on. Low.
- **Smallest fix:** reject any control character/whitespace/backslash and require no scheme/netloc after `urlsplit`, falling back to the dashboard (code in `findings.json`).

### 3.3 `newsletter:record_consent-unverified-resubscribe`
- **Where:** `services/newsletter.py:20-22`, reached from `routes/main_routes.py:106` (`/subscribe`), `routes/shop_routes.py:174` (checkout), `routes/account_routes.py:43` (register).
- **Principal:** any anonymous visitor who knows an email address.
- **Reproduction:** subscribe an address, unsubscribe it with its token, then POST `/subscribe` for the same address from another client: `unsubscribed_at` is cleared, both lists re-enabled, `consent_source` overwritten, and the address appears in the admin CSV export.
- **Impact and priority:** someone can put a person back on the marketing list after they opted out and falsify the consent record; harm occurs only if Val mails the exported list. Worth fixing before any bulk mailing.
- **Smallest fix:** double opt-in (pending until the address owner clicks an emailed token); never clear `unsubscribed_at` from an anonymous request.

### 3.4 `shop-checkout-unpaid-stock-reservation-uncapped-no-expiry`
- **Where:** `routes/shop_routes.py:97-176`, `services/security.py:43`, `services/cart.py:9`.
- **Principal:** anonymous visitor who does not intend to pay.
- **Reproduction:** add every in-stock variant to the bag and check out once as a guest: stock goes to 0, one unpaid pending order exists, and the next shopper cannot add anything.
- **Conditions:** real stock is only 1-2 per variant (about 12 pieces), so one bag covers it. Val cancels or deletes the order to release stock; the owner is emailed on new orders only if MAIL_* is configured.
- **Impact and priority:** temporary loss of sales; no data exposure. Low, but cheap to bound.
- **Smallest fix:** cap units per guest order (for example 6) and auto-cancel/restock unpaid website orders after about 48 hours.

## 4. NEEDS VALIDATION
| Lead | Trace | Blocker | Local next step | Owner-observed check |
|---|---|---|---|---|
| Order emails use the request Host for links (`urls:host-header-absolute-links-in-order-emails`) | `routes/shop_routes.py:36-38` -> `services/mailer.py:102,132`; `app.py:25` (no TRUSTED_HOSTS/SERVER_NAME) | Whether PythonAnywhere forwards an arbitrary `Host` to the app, and whether MAIL_* is set | Done in sandbox (Host `evil.example` gave `evil.example` links). After a fix, repeat and assert links stay canonical | Val/Khayanda checks the PythonAnywhere Web tab domain list, whether MAIL_* is set, and the access log for non-canonical Host values. No live probing |
See `NEEDS-VALIDATION.md` for detail. Cheap fix regardless: set `TRUSTED_HOSTS` or a fixed `PUBLIC_BASE_URL` for email links.

## 5. Hardening notes and positives
**Hardening (not findings):** admin stock edits and the admin restock-by-id paths are not atomic and can leave wrong counts (examined; admin-only, rejected as non-security; fingerprints `admin-stock-writes-nonatomic-overwrite-vs-checkout`, `admin-order-restock-dangling-variant-id-reuse`); sessions have no lifetime or server-side revocation (old cookies keep working up to 31 days); no password reset/change or email verification; login throttles are in-memory per process; unknown-user login skips the hash (timing); `SESSION_COOKIE_SECURE`/HSTS depend on `FLASK_ENV=production`; no Content-Security-Policy; `app.py` runs `debug=True` if started with `python app.py` (README suggests it); `requirements.txt` has ranges only, no lockfile; `.gitignore` omits `static/images`, `*.db`, `.env.*`; old main product photos are never deleted on replace/delete; admin `mailto:` links are not URL-encoded; `cart_add` redirects to the raw Referer (not cross-site exploitable because of CSRF + SameSite); README says a 5 MB photo cap while the code allows 60 MB.
**Positive patterns:** app-wide CSRF; ORM only; autoescape with a single hardened Markup sink; uuid-named re-encoded uploads; basename-guarded deletes; atomic checkout stock decrement; server-side pricing; 192-bit tokens; scrypt hashes; CSV formula neutralisation; header-injection-safe mailer; no hardcoded secrets or debug endpoints.

## 6. Coverage summary (from `coverage-ledger.json`, 12 units)
- covered: 5 (admin login; uploads; journal rendering; config/supply chain; obvious-things checklist)
- candidate (candidate raised and independently decided): 5 (checkout; admin orders/stock; shopper accounts; contact/subscribe/mail; redirect/Host trust)
- deferred: 2 (critic-accepted gaps above)
- blocked: 0; out of scope: 0
- Final critic: ran once; accepted 2 missing units, no reassignments. Not a clean-coverage claim.
