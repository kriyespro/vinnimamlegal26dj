# dev.md — Development Plan: VinnitaLegal → Django

Follows `rule.md`. Brand: **VinnitaLegal** (old code says "LexAssist" — rename everywhere).
Decisions from owner: real **Razorpay** payments, **no OTP** (for now).

## 1. Current State (inspected)

Root folder: 19 static HTML pages + `styles.css` + `kw.txt` (older static snapshot).

`find missing files/` holds the real latest work:
- `myapp_deploy.zip` (Aug 7 2026) — **newest**. `myapp_july.zip` (Jul 24) and extracted `myapp/` (Jul 20, has SQLite DB + 3 seed uploads) are older.
- It is a **Flask + SQLite** app, ~1.4k-line `app.py`, `db.py` (raw sqlite3, 20 tables), `auth.py`, `state_services.py`, 30+ templates.
- Root static snapshot is missing: `index.html` (home), `about.html`, `search.html`, `portal_dashboard.html`, `client_dashboard.html`, `partner_dashboard.html`, `staff_dashboard.html`, `ceo_dashboard.html`, `includes/*` (state menu, site search, nav bits). All present in `myapp/templates`.
- Flask app has: client signup/login/password reset, roles (`client`, `partner`, `staff`, `ceo`), policy acceptance gate, case/milestone/update tracking, document upload/download with ext+size limit, doc requests, drafts approve/reject, conflict check, comms log, enquiries + WhatsApp outreach, consultations booking, invoices, escalation, breach report, audit log, state-wise services, site search, CEO dashboard.
- Frontend: Tailwind CDN + Alpine CDN, nav/footer duplicated per page, Jinja2 already (Flask) so templates port easily.

### Problems found in Flask code (must NOT carry over)
- `SECRET_KEY` fallback `"lexassist-dev-secret-change-me"`; `app.run(debug=True)`.
- Seed users with password `demo123`; `password_reset` flashes the reset code on screen ("Demo code: ...") and stores it in session — anyone can reset any account.
- Password min length 6; no login throttling; no CSRF tokens seen in grep.
- Invoice "payment" is a staff button that just sets `status='Paid'` — no real payment.
- Raw sqlite3 SQL, no migrations, schema patching at runtime.
- Stale old references in site (`index.html` links).

## 2. Approach

Flask app = **functional spec + UI source**, not code to keep. Port to Django per `rule.md` (Django ORM, Jinja2, Tailwind, Alpine, HTMX). Preserve visual design exactly; reuse templates, rewriting only `url_for`, `session`, `flash`, form actions, and inline-JS data bits.

First step: extract `myapp_deploy.zip` into project (`legacy_flask/`, reference only, never deployed), copy `styles.css` + images. Delete nothing until ported.

## 3. Target Architecture

```
config/            settings (base/dev/prod), urls, wsgi
apps/
  core/            base layout, home, about, static pages, search, sitemap, robots, error pages
  catalog/         Service, State, StateServiceInfo, PricingPlan, Deadline, GlossaryTerm, FAQ, BlogPost
  accounts/        custom User (email login), roles, policy acceptance, password reset
  leads/           Enquiry, Consultation, WhatsApp outreach log
  cases/           Case, CaseStaff, Milestone, CaseUpdate, Document, DocumentRequest, Draft, Query, StaffMessage, ComplianceAlert
  compliance/      ConflictCheck, Communication, Incident(breach), Escalation
  billing/         Invoice, Payment, RazorpayEvent (webhook log); services/razorpay.py
  audit/           AuditLog (append-only)
templates/         base.html, components/, partials/ (htmx), pages/, dashboards/
static/            styles.css (kept), tailwind build, vendored alpine + htmx
```

Stack: Python 3.12, Django 5, Jinja2 backend, Tailwind CLI build (drop CDN), Alpine + HTMX vendored, SQLite dev / PostgreSQL prod, whitenoise, gunicorn.
Deps (minimal): `django`, `jinja2`, `django-htmx`, `razorpay`, `psycopg[binary]`, `whitenoise`, `gunicorn`, `django-axes` (login lockout), `python-dotenv`/env. No Celery, no DRF for MVP.

## 4. Razorpay Plan (billing app)

Flow per `rule.md §19` — browser never decides amount or paid status:

1. Client opens invoice in dashboard → clicks **Pay**.
2. `POST /billing/invoices/<id>/pay` (login + client owns case + invoice unpaid). Server reads amount from `Invoice` (paise = amount × 100), calls Razorpay `order.create`, stores `Payment(status=created, razorpay_order_id)`, returns HTMX partial with Checkout JS config (key_id only, order_id).
3. Razorpay Checkout.js runs in browser. Handler posts `razorpay_payment_id`, `razorpay_order_id`, `razorpay_signature` to `/billing/verify`.
4. Server verifies signature (`HMAC_SHA256(order_id|payment_id, key_secret)`, constant-time compare), checks order belongs to that user's invoice, marks `Payment` captured + `Invoice` Paid inside `transaction.atomic`, writes CaseUpdate + AuditLog.
5. **Webhook** `/billing/webhook/razorpay` (csrf_exempt, only this route): verify `X-Razorpay-Signature` with `RAZORPAY_WEBHOOK_SECRET` over raw body; store `RazorpayEvent` by event id (unique → idempotent); handle `payment.captured`, `payment.failed`, `order.paid`, `refund.processed`. Webhook is source of truth; verify step is UX speed-up only.
6. Staff can view payments and trigger refund (partner/ceo only, audited). Remove old "mark paid" button; if offline payment needed, separate `record_offline_payment` action for ceo only, audited.
7. Config via env: `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`. Test mode in dev, live in prod. Never in JS/git.
8. GST/receipt: generate invoice PDF/receipt later (not MVP).
9. Tests: amount tamper, other client's invoice, bad signature, replayed webhook, double pay, failed payment, webhook arrives before verify.

Also usable for pricing-page "pay now"/consultation fee: add `Invoice` without a case (`kind=consultation`) — decide with owner.

## 5. Auth (no OTP)

- Email + password login, Django auth, custom User with `role`. Min 10-char password validators.
- **No OTP / no 2FA now.** Remove OTP UI from portal login. Keep design hook so email OTP/TOTP can be added later for staff/ceo.
- Password reset: Django token emailed via SMTP (console backend dev). Never display the code/token on page.
- Policy acceptance: store `PolicyAcceptance(user, version, accepted_at, ip)`; gate all portal views.
- `django-axes` lockout, secure cookies, idle timeout.
- Remove seeded `demo123` users from prod path; dev seed via management command only, refuses to run when `DEBUG=False`.
- Authorization: view-level role decorators + object-level scoping (port `user_can_access_case`, `cases_for_user` as queryset managers). Every case/doc/invoice/draft fetch goes through scoped queryset → 404 on foreign ID.

## 6. Phases

### Phase 0 — Setup
git init + `.gitignore`; venv; Django project; env settings; `.env.example`; Jinja2 env (`url`, `static`, `csrf_input`); whitenoise; Tailwind CLI; unzip Flask app to `legacy_flask/`.

### Phase 1 — Base layout + public pages
`base.html` with nav (incl. state menu, site search, mobile portal nav) and footer from `includes/*`. Port all public templates (index, about, services, pricing, contracts, deadlines, gst, trademark, business-registration, msme, partnership, marriage, adoption, glossary, faq, blog, contact, expert-portal, policy). Named URLs replace hrefs. SEO blocks, sitemap, robots. Visual parity check vs Flask app.

### Phase 2 — Catalog from DB
Port `state_services.py` data → `State` / `StateServiceInfo` models + fixture. Services by state with HTMX. Site search (Django ORM over catalog + pages) replacing Flask `/search`. Pricing/FAQ/glossary/deadlines as models with admin, seeded from current content.

### Phase 3 — Leads
`/enquire` → ModelForm + HTMX partial response, honeypot, rate limit, email to firm. Consultation booking. Port staff enquiry list + WhatsApp link generator (server builds `wa.me` URL, no API needed).

### Phase 4 — Accounts + portal
Custom User, login/signup (client self-signup, staff/partner/ceo admin-created), logout POST, reset, policy gate. Dashboards per role (client, partner, staff, ceo) ported template-by-template; replace page reloads with HTMX panels where simple (tabs stay Alpine). Port features in this order: cases/milestones/updates → documents (private storage, authorized download view, MIME + ext + size checks, random stored names) → doc requests → drafts approve/reject → queries/messages → conflicts → comms → escalation/breach → audit log → CEO dashboard stats (aggregate queries, no N+1).

### Phase 5 — Billing (Razorpay)
Section 4. Invoice model migrated from Flask `invoices`; dashboard payments tab gets Pay button.

### Phase 6 — Data migration
Script `import_flask_db` reads `lexassist.db` (demo data only, unless owner confirms real data) into Django models; passwords re-hashed on first reset (Werkzeug hashes not compatible unless custom hasher — simpler: force reset for real users). Uploads copied into private media.

### Phase 7 — Hardening + launch
Prod settings (DEBUG off, HTTPS, HSTS, secure cookies, CSP, ALLOWED_HOSTS), friendly 400/403/404/500, logging without PII, PostgreSQL, backups, gunicorn + proxy, Razorpay live keys + webhook URL, accessibility + mobile pass, security review.

## 7. Testing (priority, rule §36)
Auth, role matrix, IDOR on case/document/invoice/draft IDs, upload abuse, password reset, Razorpay cases above, audit rows written, HTMX partials, mobile layout. Port Flask `smoke_test.py`, `deep_check.py`, `check_portal_auth.py` as starting checks.

## 8. Per-Feature Checklist
Backend works · design preserved · Jinja2/HTMX/Alpine/Tailwind in proper roles · authn + authz + ownership checked · CSRF · server validation · queries reviewed · mobile checked · errors handled · tests added · no secrets · no unrelated files changed.

## 9. Open Questions
1. Confirm final brand text/logo/domain ("VinnitaLegal") — Gujarat-focused copy OK?
2. Does `lexassist.db` contain real client data or demo only? (affects migration + privacy)
3. Razorpay account ready? Need test keys to start; live KYC for launch.
4. What do clients pay for: case invoices only, or also fixed-price services on pricing page / consultation fee?
5. Refund policy and who may issue refunds.
6. GST invoice requirements (GSTIN, HSN/SAC, tax split).
7. Email provider for reset + notifications; WhatsApp stays as click-to-chat link?
8. Document storage: local private dir vs S3-compatible; retention period.
9. Hosting target.
10. Staff/partner/ceo onboarding: admin-created only?

## 10. Start Order
Phase 0 → Phase 1 (home + services + contact first to prove parity) → Phase 4 login/dashboards → Phase 5 Razorpay → Phases 2, 3 → 6 → 7.

## 11. Progress Log

**2026-09-30 — Phase 0 + Phase 1 (public pages) done**
- Project: `config/` (settings split base/dev/prod, no fallback secret in prod), apps `core`, `leads`, `catalog`. Python 3.12 venv `.venv`, `requirements.txt`, `.env.example`, `.gitignore`, `git init` (no commit yet).
- Old files moved: static snapshot → `legacy_static/`, Flask app (from `myapp_deploy.zip`) → `legacy_flask/`. Reference only.
- 21 public templates ported as-is from Flask (Jinja2 backend). `url_for` shim in `apps/core/jinja.py` keeps templates unchanged; Django URL names = old Flask endpoint names.
- Brand renamed to VinnitaLegal. Canonical tag on home removed (old domain unknown).
- `/enquire` rebuilt: ModelForm, CSRF, honeypot, IP rate limit (5/h), open-redirect guard, admin list. Flask bug fixed (form sent `source`, code read `source_page`).
- `/portal` is a placeholder page until Phase 4.
- 12 tests pass; all pages return 200.

**Deferred / to do in Phase 1b**
- Extract shared `base.html` + nav/footer (pages still carry duplicated nav). Risky refactor → do after visual check in browser.
- Replace Tailwind CDN with CLI build; vendor Alpine/HTMX.
- Old email `support@lexassist.in` and phone `+91 98765 43210` still in copy — need real VinnitaLegal contact details.
- Marketing claims ("2 Lakh+ businesses", "#1 portal", testimonials) look like template filler — confirm before launch.
- State/service data still in `apps/catalog/data.py` (Python dicts) → models in Phase 2.

**Decisions received**
- `lexassist.db` = demo data only → no data migration needed; skip Phase 6 import.
- No Razorpay test keys yet → build billing against the SDK with env keys; tests mock signature/webhook. Owner must create Razorpay account + test keys before manual end-to-end test.
- Payments cover fixed-price services and consultation fees (not only case invoices) → `Invoice`/`Order` model must allow no-case purchase; pricing page gets Pay buttons.

**2026-09-30 — Phase 1b (base layout) + Phase 4 (accounts & portal) done**
- `templates/base.html` + `components/nav.html` + `components/footer.html`. All 21 public pages now `{% extends 'base.html' %}` with blocks `title`, `meta`, `xdata`, `content`. Single nav/footer = the home-page design (Services + By State menus, search, Client Portal button) on every page — a small visible change for inner pages that had a simpler nav. Not yet visually compared in a browser (Chrome extension was not connected).
- Apps: `accounts` (email-login User, roles client/partner/staff/ceo, `PolicyAcceptance` per version), `audit` (append-only `AuditLog`, read-only admin), `portal` (Case, Milestone, CaseUpdate, DocRequest, Document, CaseMessage, Communication, Draft, Conflict, Incident, Consultation, ComplianceAlert, StaffMessage), `billing` (`Invoice` only for now), `leads` (+`EnquiryOutreach`, statuses new/whatsapp_sent/converted/closed). Deviation from plan: `cases` + `compliance` merged into `portal`.
- Login/signup/forgot/logout; **no OTP**. Password reset = emailed single-use token link (old flow showed the reset code on screen — removed). Min password 10 chars + Django validators. django-axes lockout (5 failures → IP or email locked 1h). Rate limits on signup/forgot.
- Portal: `portal_required(*roles)` decorator (auth + current policy + role → 403) and `access.get_case()` object scoping (other user's IDs → 404). CEO = org-wide read, no write routes. All 4 dashboards ported from Flask templates with CSRF on every form; data built by `portal/rows.py` so templates stayed nearly unchanged.
- Documents: stored in `private_media/` (outside static), random names, ext + magic-byte + 10 MB checks, served only via authorised download view (attachment, nosniff, no-store).
- Removed: staff "Mark paid" button/route, demo credentials on login page, `demo123` seeds. `manage.py seed_demo` (DEBUG only) creates `*@demo.local` users with a random password printed once.
- Validation added vs Flask: case status/milestone/consultation/enquiry enums, consultation date not in past, draft can be reviewed once.
- Tests: 42 pass (`python manage.py test --settings=config.settings.test`) — login/policy/lockout/signup/reset, role matrix, IDOR 404s, upload abuse, path traversal, download scoping, consultations.

**Known gaps / next**
- Razorpay (Phase 5): client dashboard still lacks Pay button; no standalone-invoice view yet (service/consultation invoices with `case=None`).
- Partner/staff/ceo accounts are admin-created (Django admin at `/admin/`, needs `createsuperuser`).
- Email link host comes from request Host (ALLOWED_HOSTS enforced) — set real hosts in prod.
- `SESSION` idle timeout 2h; consider shorter for staff.
- Tailwind CDN / Alpine CDN / Chart.js CDN still in use (Phase 7: vendor + CSP).
- Dashboard slices (updates/messages) are cut in Python after prefetch; fine for MVP volumes.

**2026-09-30 — Phase 5 (Razorpay billing) done — built against mocks, not yet tried with real keys**
- Models (`apps/billing`): `Offering` (admin-managed fixed prices: service / consultation fee, `active` flag), `Invoice` (+`consultation` link, kinds case/service/consultation), `Payment` (one Razorpay order; unique order/payment ids; `needs_review` flag), `RazorpayEvent` (webhook log, unique event id).
- Flow: client clicks Pay → `POST /billing/invoices/<id>/pay` (owner only) → server creates/reuses a Razorpay order for the **invoice amount in paise** → Checkout.js → `POST /billing/verify`: HMAC signature check **and** `payment.fetch` (order id, amount, currency, status=captured must match) → `mark_paid`.
- Webhook `POST /billing/webhook/razorpay` (csrf-exempt, HMAC of raw body with `RAZORPAY_WEBHOOK_SECRET`, event-id dedupe, amount/currency checked): handles `payment.captured`, `order.paid`, `payment.failed`, `refund.processed`. Returns 500 on processing error so Razorpay retries.
- `mark_paid` is atomic + idempotent (row locks); a second capture on an already-paid invoice is flagged `needs_review` (refund manually). Paying a case invoice posts a "[Payment received]" update on the case + audit log.
- Buying: pricing page rows show **Pay online** only when an active `Offering` exists (price shown from DB), else the old Apply link. `POST /billing/buy/<slug>` takes the amount from the DB only; anonymous users are sent to login with `?next=`. Login now honours a safe `next`.
- Consultation fee: if an active `consultation` Offering exists, booking creates an invoice and sends the client to pay; partner cannot mark the consultation Confirmed until it is paid. No offering = free booking (old behaviour).
- Refunds: CEO only (`/billing/payments/<id>/refund`, full amount, audited); refund button in CEO dashboard revenue table. Staff "mark paid" stays removed.
- Client dashboard: "Payments due" card (includes case-less invoices) + Pay links in billing tab. Invoice page `templates/billing/invoice.html`.
- `manage.py seed_offerings`: creates 6 offerings from the pricing-page "Our Fee" column (Pvt Ltd 6,999 · LLP 5,499 · Trademark 6,999 · MSME 999 · Partnership 2,999 · Marriage cert. 4,999). Active in DEBUG, **inactive in prod** until the owner checks amounts in /admin/. Govt/stamp fees are not included in these amounts.
- Tests: 85 pass (43 earlier + 42 billing: tampered amounts, other client's invoice, bad/foreign signatures, mismatch, authorized-only, outage, replay, duplicate payment, failed-after-captured, refund, consultation gating).

**To test with real Razorpay (owner steps)**
1. Create a Razorpay account → Dashboard in **Test Mode** → Settings → API Keys → generate; put `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` in `.env`.
2. Webhooks → add `https://<public-host>/billing/webhook/razorpay` (use ngrok/cloudflared locally), secret → `RAZORPAY_WEBHOOK_SECRET`; events: `payment.captured`, `payment.failed`, `order.paid`, `refund.processed`.
3. `python manage.py seed_offerings`, sign up as a client, buy from /pricing, pay with Razorpay test UPI/card. Live keys + KYC only for launch.
- Not built: invoice PDF/GST receipt, subscription plans on the pricing page (Starter/Growth — GST service is hidden), partner/staff UI to raise case invoices (use Django admin), partial refunds.

**2026-09-30 — Phase 7 (hardening) done; app running locally** (Phase 6 data import skipped: old DB was demo data)
- Frontend: Tailwind CDN removed → built `static/css/tailwind.css` (`npm run build:css`, Tailwind 3.4.17, committed); Alpine and Chart.js vendored under `static/js/`. HTMX is not vendored because nothing uses it yet. Google Fonts is the only third-party asset left. Portal/billing pages now also get the Inter font (their inline Tailwind config used to omit it).
- Headers: CSP (self + `*.razorpay.com`; still needs `'unsafe-inline'`/`'unsafe-eval'` for inline page scripts and Alpine), `X-Frame-Options: DENY`, Referrer-Policy, Permissions-Policy, `X-Robots-Tag: noindex` on /portal, /billing, admin. **CSP/Razorpay Checkout not verified in a real browser** (Chrome extension unavailable) — test one payment in Razorpay test mode and watch the console for CSP violations.
- Errors: friendly 400/403/404/500 pages (500 has no DB/context dependency). Logging config (console; no bodies/passwords).
- SEO: canonical tag, `/robots.txt`, `/sitemap.xml` (public pages + state pages).
- Config: contact details now `SITE_EMAIL / SITE_PHONE / SITE_WHATSAPP` env → templates (`site.*`); **prod refuses to start** without `DJANGO_ALLOWED_HOSTS`, secret key and contact details; configurable admin URL; prod uses manifest static storage, 1h sessions. `check --deploy` only warns about HSTS preload (deliberately off).
- `README.md` with run/deploy steps. `seed_demo` also creates `admin@demo.local` (superuser).
- Tests: 93 pass.

**Still open**
- Real contact details, real marketing claims/testimonials, policy text review with counsel (DPDP / Bar Council), logo/brand assets.
- Visual check of all pages in a browser (layout parity, mobile) — never done; Chrome extension was not connected.
- Razorpay end-to-end with real test keys; invoice PDFs/GST receipts; partner/staff UI to raise case invoices; HTMX/partial updates (currently full-page posts); stricter CSP via nonces; `SECURE_HSTS_PRELOAD` decision; backups + monitoring at deploy; PostgreSQL test run.

**2026-09-30 — Follow-up: raise-invoice UI**
- Partners (progress tab) and staff (payments tab) can raise a case invoice (description, ₹1–10,00,000, optional due date) → `POST /portal/cases/<id>/invoices`, scoped to their own cases (404 otherwise), client/CEO get 403. Posts a case update for the client and logs `invoice_created`. Client then pays online. 98 tests pass. Tailwind CSS rebuilt.

**2026-09-30 — Owner console + mobile pass**
- `/admin/` is now a custom **owner console** (`apps/console`, CEO role only, CSRF, every action audited): dashboard KPIs + "needs attention", users (create → emailed set-password link, no typed password; edit role/active; can't demote/deactivate self or the last CEO), cases (create/edit, auto-number VL-YYYY-NNNN, role-checked client/partner/staff assignment), leads (status), billing (offerings CRUD/toggle, invoices, double-payment review queue), audit log. Responsive layout: drawer nav on mobile, stacked rows instead of tables. Django's admin moved to **`/sd/`** (`DJANGO_ADMIN_URL`, must not be `admin`). Anonymous visits to protected GET pages now go to login with `?next=`.
- Mobile: `tools/mobile_audit.js` (puppeteer-core + local Chrome) found horizontal overflow on every public page (footer contact column at 390px) → fixed; touch-target/overflow CSS in `static/styles.css`; Tailwind CSS rebuilt (must rebuild after adding new classes, e.g. new templates!). No overflow at 390px on any public page or dashboard afterwards.
- Found while auditing (not changed): pricing page still advertises GST subscription plans although the GST service is hidden; "2,00,000+ businesses" style claims; seeded demo invoice numbers/descriptions look odd.
- 118 tests pass.

**2026-09-30 — Main nav + dropdown fixes** (`templates/components/nav.html`, `includes/state_menu.html`, `static/styles.css`)
- Found with `tools/nav_shots.js` (desktop 1600/1280/1024 + mobile screenshots): "By State"/"All Services" wrapped to 2 lines; nav overflowed the viewport at 1280 and 1024 (search + "Get Started" pushed off-screen; `.btn-primary`'s display overrode `hidden`); dropdowns were translucent (hero text bled through) and closed when the pointer crossed the 4px gap; hover-only (no keyboard/touch); "More states" block empty; mobile menu missed Business Registration, Trademark, About, Resources.
- Fixes: nowrap links, search only ≥1536px, Get Started only ≥1280px; solid `.dd-menu` panels with hover bridge + z-index; Services menu in 2 columns (no scroll); open on hover/click/focus, close on Esc/click-outside/focus-out, `aria-expanded`; empty "More states" hidden; current page highlighted (`aria-current`); mobile menu grouped (Services/Company), larger tap targets, scrollable. No horizontal overflow at 1600/1280/1024/390. 122 tests pass.

**2026-09-30 — Full-project check + visual upgrade** (`tools/site_check.js` crawls every page/role: failed requests, console errors, broken images, dead links, alt/labels, duplicate ids, h1)
- **Regression found & fixed:** the Phase-7 CSP blocked every third-party image, so all avatars (ui-avatars.com) and stock photos (unsplash.com) were broken. Replaced with self-contained initials avatars and gradient/icon panels — no third-party image hosts (also better for visitor privacy).
- Fixed: invoice page JS error (`invoicePay` undefined when payments disabled); `/favicon.ico` 404 → added `static/favicon.svg` to all layouts; dead `href="#"` social icons → now env-driven (`SOCIAL_TWITTER/LINKEDIN/FACEBOOK`), hidden when unset; unlabeled form controls in dashboards/console/state page given `aria-label`s; Business-Registration "How we register" steps rebuilt as one clean 5-step timeline (was two mismatched grids); ₹ amounts in dashboards now use thousands separators; invoice kind label instead of raw "case".
- Semantics/a11y: `<main id="main">` + skip-to-content link; consistent focus rings.
- Visual layer (`static/styles.css` "refinement layer v2"): balanced headings/tighter tracking, selection colour, tactile button hover/press, card lift + soft depth, form-control hover, footer link polish, fluid section padding, WhatsApp button repositioned on desktop, thin scrollbars, `prefers-reduced-motion`, print styles.
- Crawl result after fixes: 0 errors on all 22 public pages and all role/admin pages; 0 dead internal links; no horizontal overflow at 390/320px. 122 tests pass.

**2026-10-04 — Skin v3: Blue · Orange · White**
- Palette (single source: `tailwind.config.js` + `static/styles.css`): blue `#1D4ED8` (deep `#1E40AF`, tint canvas `#F5F8FF`), orange `#F97316` (`#EA580C` on white for text contrast, `#FDBA74` on blue), deep navy `#0B1F4D` for text/sidebars/footer, white surfaces. The legacy `gold` Tailwind name now means brand orange; decorative purple/pink/rose/sky/amber scales collapse into blue/orange (green/red stay for success/error).
- Header is now white (blue-outline "Client Portal", orange "Get Started Free"); heroes are a bright blue gradient with orange glow + dot grid; cards are white with blue hairline and orange hover accent; orange primary buttons; orange-tint section badges; footer deep blue with orange top rule; dashboards/console keep the layout with the new palette.
- Contrast: lighter orange on blue heroes, deeper orange on white; fixed an invisible secondary hero button, footer 6-column layout/overflow, badge colours.
- Verification: screenshot review of home, services, pricing, contact, about, trademark, expert portal, portal login, client/partner dashboards, console, footer, mobile home/pricing; crawl clean, no overflow at 390px, 122 tests pass.
- Note: after changing classes in templates run `npm run build:css`.

**2026-10-04 — Full flow QA (`tools/flow_check.js`, 53 browser flows) — all pass**
- Covers: every enquiry form (contact, 6 hero forms, validation), FAQ/pricing/services/glossary/expert/trademark/state interactions, nav dropdowns (hover/click/Esc) + mobile menu, pricing Pay-online → login → `next` → invoice page, client signup → forgot-password email link → single-use reset → login, role-tab mismatch, UI login, upload/download/message/consultation, partner (status, invoice, update, doc request, reply, milestone, draft, conflict), staff (lead status, WhatsApp log, partner message, invoice, escalate, breach), CEO dashboard charts, console (create user, edit/deactivate, create case, lead status, offering create/toggle, audit), `/sd/` Django admin, console mobile drawer.
- Bugs found and fixed: staff **communication log had no UI** (route existed, form missing) → new "Comms log" tab + history per case; **nav dropdown closed itself** when clicked while hovered (hover/click conflict) → fixed for mouse + touch; **state-page enquiry form gave no feedback**, sent users to /contact, and phone field wasn't `type=tel` → flash + `#enquiry` return + proper input types; enquiry rate limit raised 5 → 20/h/IP (shared office/carrier NAT); forms without `next` now return to the referring page; staff case card showed "· ₹ due" without amount.
- Not a bug: deadlines page has a single category (filter chips have nothing to filter). Django logs expected 403s (client opening /admin/) as warnings.
- Not testable here: real Razorpay Checkout round-trip (needs test keys; backend covered by 40+ unit tests).
- 127 unit tests, crawl clean, no overflow at 390px.

**2026-10-04 — Role dashboards redesigned: compact, fewer clicks, bugs fixed**
- New shared kit: `templates/portal/base.html` (slim header, auto-dismissing toasts, no per-page boilerplate), `_ui.html` macros (pill / kpi / money), dashboard CSS kit (`.db-*`) in `static/styles.css`.
- **Client:** one screen per job — progress chips, documents (upload picks *which* requested doc it fulfils), messages with inline composer, firm updates, billing with Pay, deadlines. No tabs. Payment strip with one-click Pay, consultation form opens inline. Most urgent job (docs/payment due) opens first.
- **Partner:** case list sorted by unanswered messages/drafts; status+date+note on one row; checklist with one-click status dropdowns and **“+ Add step” (partners could not create steps before — empty cases were a dead end)**; drafts approve/reject inline (returns to the case); reply, update, doc requests, upload, invoices, read-only comms log all on the page. Consultations and conflict disclosure are one-click drawers.
- **Staff:** leads as a compact filterable list — **status change and WhatsApp (opens chat + logs outreach) are one click, no reload** (fetch + 204); cases show comms log / client update / partner message as one-line forms, documents, invoices, unified timeline; escalate/report side by side.
- **CEO:** KPI strip, “Needs attention” jump list (overdue invoices, drafts, docs, consultations, new leads), three fixed-height charts (the old charts grew to fill the screen), compact tables per tab, “Open console” link, refunds with confirm.
- Bugs fixed: oversized/stretching Chart.js canvases; checklist/doc selects collapsing titles; client upload always ticked the *first* needed doc → now the chosen one (validated to the same case); `pending_replies` counted all client messages → now only unanswered; draft approve/reject sent partner to a stale view; staff comms had no UI (earlier) and now sits inline; `h1` missing on staff/CEO; flash banners shifted layout → toasts.
- Demo DB reset and re-seeded (new demo password in `test_users.txt`). 135 unit tests, 53 browser flows, crawl clean, no overflow at 390/320px.

**2026-10-04 — Console (/admin/) redesigned to match the compact dashboards**
- Same `db-*` kit as the role dashboards: slim 13rem sidebar, toasts instead of banners, KPI strip, dense rows instead of big cards, compact filter bar (selects filter on change), 2-column compact forms.
- Fewer clicks: users list has **inline role dropdown + Deactivate/Activate + Reset link** (`/admin/users/<id>/quick/`, same guards: can't demote/deactivate self or last CEO); cases list has **inline status dropdown** (`/admin/cases/<id>/status/`); leads status inline; offerings toggle by clicking the Active/Hidden pill; dashboard has **+ User / + Case / + Offering** buttons. `back` redirects are restricted to `/admin/` URLs.
- Billing page: offerings and invoices side by side; case form reordered (title, number, client, partner, status, date, staff, note).
- 140 unit tests, 53/53 browser flows (the last run's 3 failures were the dev server auto-reloading during an edit; re-run passed), crawl clean, no overflow at 390px.

**2026-10-04 — `/portal` is now one sign-in for every role**
- Removed the Client/Partner/Staff/CEO tabs: a single email + password form; the server detects the role and opens the matching dashboard (welcome toast names the role). Any posted `role` field is ignored.
- Only clients can self-register (separate "Create client account" mode, no role field; staff/partner/founder accounts stay admin-created via the console). Forgot-password mode, show/hide password, safe `?next=` support, `?mode=signup|forgot` deep links.
- Split-screen layout (brand panel + form) on desktop, single card on phones; blue/orange/white skin.
- Tests: role auto-detect for all four roles, posted-role ignored, no role tabs / client-only sign-up copy; browser flow added. 142 unit tests pass.

**2026-10-04 — Hero + top bar + portal copy**
- `/portal`: removed the "Partner, staff and founder accounts are created by the office…" note.
- Top bar on every public page: support phone (tap-to-call), support email, hours, WhatsApp, "Client login →" (values from `SITE_PHONE/SITE_EMAIL/SITE_WHATSAPP`; phones show phone + email, hours/WhatsApp hide <768px).
- Home hero rebuilt as a **light** hero (white → soft blue, faint grid, orange/blue glows): honest headline (dropped the unverifiable "India's Most Trusted"), two CTAs, one-click "Popular right now" service chips, three real feature points, and a CSS-only **sample client dashboard** with floating payment/message cards. Below it a floating white **callback bar** (name, phone, service → `/enquire`, returns to `/#callback` with confirmation) and a light stats strip. Inner-page heroes stay blue for contrast.
- Tests: top bar contacts on 5 pages, callback form + return, no superlative in hero; browser flows for both. 146 unit tests pass; no overflow at 390px.

**2026-10-04 — Deep audit: bugs, performance, security, Redis, SEO** (details + checklists)

### Bugs found and fixed
- **Production `collectstatic` crashed** (`js/chart.umd.min.js` referenced a missing `.map` file; ManifestStaticFilesStorage is strict) — never caught because earlier checks ran with dev settings. Fixed; prod build verified (177 files, hashed, Brotli/gzip).
- **HEAD requests returned 405** on every page (`require_GET`) → crawlers/uptime monitors would see errors. All read views now `require_safe`; `/portal` HEAD handled.
- **Behind a reverse proxy every visitor would share one IP** (rate limits, login lockout and audit log would lock out the world) → `TRUSTED_PROXY_COUNT` + `client_ip()` (X-Forwarded-For only trusted when configured; Axes wired to it).
- **A cache outage would have 500'd login/signup/enquiries** → `SafeRedisCache` degrades to cache misses; rate limiter fails open (login lockout still enforced by Axes in the DB).
- Oversized uploads were fully spooled to disk before the size check → streaming `SizeLimitUploadHandler` aborts at 10 MB.
- Weak SHA-1 used for a temp invoice number (bandit B324) → `secrets`; Jinja autoescape made explicit (B701); `raise … from None`, lint cleanup (ruff clean).
- Trailing-slash duplicates (`/about/`) → 301 to the single canonical URL.

### Performance checklist (measured with `tools/perf_check.js`, cache off)
- [x] One minified stylesheet (`app.min.css` 63 KB → **11 KB Brotli**), Tailwind purged; Alpine only JS on public pages; Chart.js only on the CEO dashboard.
- [x] Fonts self-hosted, `font-display: swap`, only the Latin file is preloaded; the rupee sign comes from a **1.2 KB subset** (the old latin-ext file was 85 KB on every page with ₹). No third-party requests (0 hosts).
- [x] Static files hashed + `immutable` 10-year cache + pre-compressed (WhiteNoise); HTML gzip (66 KB → 14 KB); `Vary: Accept-Encoding`.
- [x] Public pages: **0 DB queries**; dashboards: query count constant as cases grow (test), search catalog cached per process.
- [x] DB indexes on hot filters (enquiry status/date, invoice client/status/due, case/draft/consultation status, user role).
- [x] Postgres: `CONN_MAX_AGE=60` + health checks; session store in Redis (`cached_db`).
- [x] Results: FCP 150–570 ms, LCP ≤ 570 ms, CLS ≤ 0.04, 4–8 requests/page, ≤ 190 KB uncompressed (≈ 60 KB compressed). Budgets enforced by `perf_check.js` and `PerformanceBudgetTests`.
- [ ] Not done: image CDN (no raster images used), HTTP/2/3 + TLS (proxy), Brotli for dynamic HTML (proxy/CDN), service worker.

### Security checklist
- [x] CSP is **nonce-based** — no `'unsafe-inline'` for scripts; inline event handlers removed (test fails if one returns); `object-src 'none'`, `frame-ancestors 'none'`, `base-uri`, `form-action`, `upgrade-insecure-requests`. Remaining weakness: `'unsafe-eval'` (Alpine standard build) and `'unsafe-inline'` for *styles*.
- [x] Argon2 password hashing (PBKDF2 hashes upgrade on next login); 10-char min + validators; Axes lockout; neutral reset/login messages.
- [x] Cookies: HttpOnly + SameSite=Lax, Secure in prod, CSRF cookie HttpOnly, renamed (`vl_session`, `vl_csrf`), 1 h idle session in prod.
- [x] Headers: HSTS (+ preload opt-in), COOP/CORP same-origin, nosniff, Referrer-Policy, Permissions-Policy, X-Frame-Options, noindex on private areas.
- [x] Prod refuses to start without hosts/secret/contact details/PostgreSQL; `check --deploy` clean except HSTS preload (intentional); `SECURE_REDIRECT_EXEMPT` for `/healthz`.
- [x] `pip-audit`: no known vulnerabilities; `npm audit --omit=dev`: 0 (dev-only tooling advisories remain in puppeteer/tailwind CLI, never deployed); bandit: clean after fixes.
- [x] IDOR/role matrix, upload abuse, CSRF, webhook signatures/replay, Razorpay amount tampering covered by tests (190+).
- [x] `/.well-known/security.txt`, `/healthz` (no secrets), private media outside static, `legacy_*` folders are reference-only (delete before deploying).
- [ ] Open items for you: set real `SITE_*`, Razorpay keys, SMTP; consider moving to Alpine CSP build later to drop `'unsafe-eval'`; enable `DJANGO_HSTS_PRELOAD=1` only after HTTPS is stable on all subdomains.

### Redis
- [x] Installed & tested locally: `REDIS_URL=redis://127.0.0.1:6379/N` → `RedisCache` (prefix `vl`), sessions `cached_db`, shared rate limits; `check_services` pings it; failure mode verified (dead Redis → misses, site stays up). Without Redis: DB cache table in prod (`createcachetable`), locmem in dev.

### SEO checklist (all enforced by `apps/core/test_quality.py`)
- [x] Unique `<title>` ≤ 60 chars and meta description 70–160 chars on every page (rewrote all; removed unverifiable "India's #1 / 2 Lakh+" claims from titles/descriptions).
- [x] Canonical (self), `hreflang en-IN` + `x-default`, `lang="en-IN"`, robots meta, `theme-color`, viewport, exactly one `<h1>`, `<main>`, image alts.
- [x] Open Graph (title, description, url, type, site_name, locale, image 1200×630 JPG 75 KB) + Twitter `summary_large_image`.
- [x] JSON-LD: `LegalService`/`Organization` + `WebSite` (+SearchAction) on home, `FAQPage` (visible FAQ and schema share one data source), `Service` on 7 service pages, `BreadcrumbList` on inner pages; output escaped against `</script>` break-out.
- [x] `robots.txt` (+Sitemap, blocks private areas), `sitemap.xml` with `lastmod`, noindex on search/portal/billing/admin/healthz, 404 noindex, clean 301 for trailing-slash duplicates.
- [x] Web app manifest + favicon SVG/PNG/apple-touch icons; accessible FAQ accordion (`aria-expanded/controls`); all internal links resolve (test).
- [ ] Needs your content/accounts: Google Search Console + Bing verification, real address/GST in schema (`LocalBusiness`), Google Business Profile, backlinks, real reviews (do not add `AggregateRating` until genuine), blog articles (blog page is a stub), per-service landing copy.
