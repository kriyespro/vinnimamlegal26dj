# VinnitaLegal — Django app

Django 5 · Jinja2 · Tailwind (built CSS) · Alpine.js · SQLite (dev) / PostgreSQL (prod) · Razorpay.
Rules: `rule.md`. Plan + progress log: `dev.md`. Old Flask/static code: `legacy_*` (reference only).

## Run locally
```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # optional in dev
python manage.py migrate
python manage.py seed_demo      # DEBUG only; prints demo logins + random password once
python manage.py seed_offerings # fixed-price items for the pricing page
python manage.py runserver      # http://127.0.0.1:8000
```
Tests: `python manage.py test --settings=config.settings.test`

## Admin areas
- `/admin/` — **owner console** (Founder/CEO role only): users (email set-password onboarding), cases & assignment, leads, billing/offerings, audit log. Sign in via the single `/portal` form (role is auto-detected).
- `/sd/` — Django's built-in admin (advanced/raw data; needs a `createsuperuser` account, configurable with `DJANGO_ADMIN_URL`).

## Mobile audit
`npm i` then `DEMO_PW=<demo password> node tools/mobile_audit.js 390 /tmp/shots` (needs local Chrome; reports horizontal overflow per page) and `node tools/shoot.js 390 /tmp/out ceo /admin/ 2` for screenshots.

## Frontend build (only when templates/classes change)
```bash
npm install && npm run build:css    # Tailwind + assets/styles.src.css + self-hosted fonts -> static/css/app.min.css (one minified file, committed)
node tools/make_icons.js            # regenerates favicon PNGs + social share image (needs local Chrome)
```
Fonts are self-hosted (`static/fonts`, Inter variable). No third-party requests are made by the site.

## Production checklist
Set env (see `.env.example`): `DJANGO_SETTINGS_MODULE=config.settings.prod`, `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DATABASE_*` (PostgreSQL), `SITE_EMAIL/PHONE/WHATSAPP`,
`EMAIL_*`, `RAZORPAY_*`, optional `DJANGO_ADMIN_URL`. Prod refuses to start without hosts, secret and contact details.
```bash
python manage.py migrate && python manage.py collectstatic --noinput
python manage.py createsuperuser
gunicorn config.wsgi --bind 0.0.0.0:8000 --workers 3
```
Put it behind HTTPS (proxy must send `X-Forwarded-Proto`). Back up the database **and** `private_media/` (client documents).
Razorpay: webhook URL `https://<host>/billing/webhook/razorpay`, events `payment.captured, payment.failed, order.paid, refund.processed`.
Review offering amounts in the console (`/admin/` → Billing) before enabling (`seed_offerings` creates them inactive in prod).

## Ops, security & quality tooling
| What | How |
|---|---|
| Health probe (load balancer / uptime monitor) | `GET /healthz` → 200 `{"status":"ok","database":true,"cache":true}` or 503 |
| Pre-flight report | `python manage.py check_services` (DB, Redis, secrets, static build, media, email, Razorpay, placeholders) |
| Django deploy checks | `python manage.py check --deploy` |
| Redis | set `REDIS_URL`; sessions become `cached_db`, rate limits are shared across workers. Without it production uses the DB cache (`manage.py createcachetable`). A Redis outage degrades to cache misses — it never raises. |
| Behind a proxy | set `TRUSTED_PROXY_COUNT` so rate limits/lockouts/audit use the real visitor IP |
| Static files | `python manage.py collectstatic --noinput` → hashed, immutable-cached, Brotli/gzip pre-compressed by WhiteNoise |
| Dependency audit | `pip-audit -r requirements.txt` and `npm audit --omit=dev` (dev-only npm findings are in QA tooling, never deployed) |
| Static analysis | `ruff check apps config` · `bandit -r apps config -ll` |
| Browser QA | `node tools/flow_check.js` (53 flows) · `site_check.js` · `perf_check.js` · `mobile_audit.js` · `seo`/security tests in `apps/core/test_quality.py` |
| security.txt | `/.well-known/security.txt` (contact = `SITE_EMAIL`) |
# vinnimamlegal26dj
