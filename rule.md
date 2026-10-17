# CLAUDE.md — Django Full-Stack Project Rules

## 1. PROJECT OBJECTIVE

This project is an existing frontend application that must be converted into a production-ready full-stack Django application.

Existing frontend:

* HTML
* CSS
* JavaScript

Target stack:

* Python 3.12+
* Django 5+
* PostgreSQL in production
* SQLite for local development when appropriate
* Jinja2 templates
* Tailwind CSS
* Alpine.js
* HTMX
* Django ORM
* REST/API endpoints only where genuinely required

Primary objective:

> Preserve the existing frontend design and UX while progressively connecting it to a clean, secure, maintainable Django backend.

Do not redesign the frontend unnecessarily.

---

# 2. SESSION START RULES

Before making changes:

1. Inspect the existing project structure.
2. Read this file completely.
3. Inspect existing frontend pages, components, CSS and JavaScript.
4. Identify the existing functionality before implementing backend logic.
5. Check existing Django configuration before creating new configuration.
6. Reuse existing code whenever practical.
7. Do not create duplicate models, views, components or utilities.
8. Do not make architectural changes without understanding the existing structure.

Before modifying an important feature:

* Identify the relevant template.
* Identify the relevant JavaScript.
* Identify the relevant Django app.
* Identify related models.
* Identify existing URLs/views.
* Identify existing authentication/authorization logic.

---

# 3. CORE ENGINEERING PRINCIPLES

Follow these principles:

* Build the simplest production-ready solution.
* Prefer boring, maintainable Django over unnecessary complexity.
* Keep business logic out of templates.
* Keep templates primarily responsible for presentation.
* Keep JavaScript minimal.
* Prefer server-rendered HTML.
* Use HTMX for server-driven interactions.
* Use Alpine.js for lightweight client-side state.
* Use Django ORM instead of raw SQL unless there is a documented reason.
* Avoid unnecessary APIs.
* Avoid unnecessary SPA architecture.
* Avoid unnecessary JavaScript frameworks.
* Avoid premature abstraction.
* Avoid over-engineering the MVP.

Priority:

```text
Correctness
Security
Maintainability
Performance
Developer Experience
Feature Speed
```

---

# 4. ARCHITECTURE

Preferred architecture:

```text
Browser
   │
   ├── HTML
   ├── Tailwind CSS
   ├── Alpine.js
   └── HTMX
        │
        ▼
     Django
        │
   ┌────┴────┐
   │         │
Views      Services
   │         │
   └────┬────┘
        │
      Models
        │
        ▼
   PostgreSQL
```

Use Django's server-side rendering as the default architecture.

Do NOT turn the application into a React/Vue SPA unless explicitly requested.

---

# 5. EXISTING FRONTEND IS THE SOURCE OF TRUTH

The existing frontend represents the intended visual design.

When converting frontend pages:

* Preserve layout.
* Preserve typography.
* Preserve spacing.
* Preserve colors.
* Preserve responsive behavior.
* Preserve navigation.
* Preserve forms.
* Preserve existing UX patterns.
* Preserve important animations where practical.

Do not redesign a page simply because a different design seems better.

Only change the UI when:

* The user explicitly requests it.
* The existing implementation is technically broken.
* A backend integration requires a minimal UI adjustment.

---

# 6. TEMPLATE ENGINE — JINJA2

Use Jinja2 for Django templates.

Preferred structure:

```text
templates/
    base.html
    components/
    partials/
    pages/
```

Use template inheritance:

```jinja2
{% extends "base.html" %}

{% block content %}
...
{% endblock %}
```

Use reusable components/macros when they genuinely reduce duplication.

Do not create abstractions for tiny pieces of markup that are only used once.

Keep business logic out of templates.

Avoid complex Python-like logic inside templates.

---

# 7. TEMPLATE RULES

Templates should primarily:

* Display data.
* Render forms.
* Render components.
* Handle simple conditional presentation.
* Provide HTMX targets.
* Provide Alpine.js state.

Do not perform:

* Database queries.
* Business calculations.
* Permission decisions.
* Complex data transformations.
* Security decisions.

All important business logic belongs in Python.

---

# 8. TAILWIND CSS

Use Tailwind CSS for styling.

Prefer utility classes directly in templates.

Example:

```html
<div class="rounded-xl border bg-white p-6 shadow-sm">
```

Avoid creating large custom CSS files when Tailwind can solve the problem.

Use custom CSS only when:

* Tailwind cannot reasonably express the requirement.
* A third-party library requires it.
* Complex animations/effects require it.
* Existing project CSS must be preserved.

Do not rewrite the entire existing design system unnecessarily.

Maintain responsive behavior:

```text
mobile
tablet
desktop
large desktop
```

---

# 9. ALPINE.JS

Use Alpine.js for lightweight client-side interactions.

Good use cases:

* Dropdowns
* Modals
* Tabs
* Toggles
* Mobile navigation
* Local UI state
* Show/hide elements
* Small interactive components

Example:

```html
<div x-data="{ open: false }">
```

Do not use Alpine.js for business logic that belongs on the server.

Do not build a full client-side application using Alpine.js.

---

# 10. HTMX

HTMX is the preferred solution for server-driven dynamic interactions.

Use HTMX for:

* Search
* Filtering
* Pagination
* Inline editing
* CRUD operations
* Modal loading
* Partial updates
* Form submissions
* Dashboard widgets
* Table updates
* Infinite scrolling where appropriate

Preferred pattern:

```text
Browser
   ↓
HTMX request
   ↓
Django view
   ↓
Jinja partial
   ↓
HTML response
   ↓
HTMX updates DOM
```

Prefer returning HTML fragments instead of JSON when the response is intended only for the web UI.

Do not create an API endpoint just to update HTML that HTMX can handle directly.

---

# 11. HTMX + ALPINE RESPONSIBILITY

Use:

```text
HTMX = server communication
Alpine.js = local UI state
Django = business logic
Jinja2 = rendering
Tailwind = styling
```

Example:

```text
Dropdown open/close
→ Alpine.js

Search results
→ HTMX + Django

Database filtering
→ Django

Visual styling
→ Tailwind
```

Do not mix responsibilities unnecessarily.

---

# 12. DJANGO APPS

Organize Django applications by business domain.

Example:

```text
apps/
    accounts/
    stores/
    products/
    orders/
    payments/
    analytics/
    marketing/
```

Avoid creating a single giant application such as:

```text
app/
    models.py
    views.py
```

for the entire product.

Each app should have a clear responsibility.

---

# 13. MODELS

Use Django ORM.

Models should represent business entities clearly.

Prefer:

```python
class Product(models.Model):
    store = models.ForeignKey(Store, ...)
```

for multi-tenant data.

Use:

* Appropriate indexes.
* Unique constraints.
* Database constraints.
* `select_related()`.
* `prefetch_related()`.
* Appropriate field types.

Do not rely solely on application-level validation when a database constraint is appropriate.

Never store derived values unless there is a clear performance or historical-data reason.

---

# 14. MULTI-TENANCY

If this is a multi-store SaaS, tenant isolation is CRITICAL.

Every tenant-owned object must be associated with the correct store/tenant.

Example:

```python
Product.objects.filter(
    store=request.store
)
```

Never trust:

```text
store_id
tenant_id
user_id
```

directly from browser input.

Always derive authorization from the authenticated user/session and server-side relationships.

Never allow:

```text
Store A user
    ↓
modify Store B data
```

through manipulated URLs, IDs, POST data, HTMX requests or APIs.

Every read/write operation must enforce tenant authorization.

---

# 15. AUTHENTICATION

Use Django authentication unless there is a specific reason to replace it.

Support where required:

* Login
* Logout
* Password reset
* Email verification
* Session management
* 2FA/MFA
* Social login

For sensitive actions, require re-authentication or MFA where appropriate.

Never store plaintext passwords.

---

# 16. AUTHORIZATION

Authentication answers:

> Who is this user?

Authorization answers:

> What is this user allowed to do?

Always enforce authorization server-side.

Example roles:

```text
Owner
Admin
Staff
Manager
Customer
```

Never rely on:

```html
{% if user.is_admin %}
```

alone for security.

The Django view/service must enforce permissions.

---

# 17. SECURITY

Security is mandatory.

Protect against:

* CSRF
* XSS
* SQL injection
* IDOR
* Broken access control
* Session hijacking
* Brute-force login attempts
* Credential exposure
* Unsafe file uploads
* Mass assignment
* Privilege escalation

Use Django's built-in security mechanisms wherever possible.

Never disable CSRF protection merely to make an HTMX request work.

Never trust client-side validation.

Validate again on the server.

---

# 18. SECRETS

Never hard-code:

* API keys
* Database passwords
* Django SECRET_KEY
* Payment credentials
* OAuth secrets
* SMTP passwords
* Cloud credentials

Use environment variables or a proper secret-management system.

Never commit `.env` files containing real credentials.

Use:

```text
.env.example
```

for documentation.

---

# 19. PAYMENTS

Payment processing must be treated as security-sensitive.

Never trust:

```text
amount
payment_status
order_total
user_id
store_id
```

from the browser.

Calculate important values server-side.

Always verify payment gateway webhooks.

Do not mark an order as paid merely because the frontend says payment succeeded.

Preferred flow:

```text
Checkout
   ↓
Django calculates amount
   ↓
Payment gateway
   ↓
Webhook
   ↓
Django verifies webhook
   ↓
Order marked paid
```

---

# 20. FORMS

Prefer Django forms where appropriate.

Always validate input server-side.

Use CSRF protection.

For HTMX forms:

```html
<form
    hx-post="..."
    hx-target="#result"
    hx-swap="innerHTML"
>
```

Return useful validation errors as HTML.

Do not duplicate validation logic unnecessarily between JavaScript and Python.

---

# 21. URLS

Use named URLs.

Prefer:

```python
path(
    "products/",
    views.product_list,
    name="product_list",
)
```

In templates:

```jinja2
{{ url("products:product_list") }}
```

Do not hard-code application URLs inside templates or JavaScript when Django URL reversing is available.

---

# 22. VIEWS

Keep views thin.

Preferred:

```text
URL
 ↓
View
 ↓
Service / domain logic
 ↓
Model
```

Avoid giant views containing:

* payment logic
* email logic
* inventory logic
* business calculations
* external API logic

Move complex business operations into service functions/classes.

---

# 23. SERVICE LAYER

Use a service layer when business operations become complex.

Example:

```text
services/
    checkout.py
    payments.py
    orders.py
    inventory.py
```

Example:

```python
create_order(...)
process_payment(...)
cancel_order(...)
reserve_inventory(...)
```

Do not create service classes merely for the sake of abstraction.

Use them when they make business logic easier to test and maintain.

---

# 24. DATABASE PERFORMANCE

Avoid N+1 queries.

Use:

```python
select_related()
prefetch_related()
```

where appropriate.

Use pagination for large lists.

Never load thousands of database rows into memory unnecessarily.

Use database indexes for frequently queried fields.

Measure before introducing caching.

---

# 25. CACHING

Use caching where it provides measurable value.

Possible technologies:

```text
Redis
Django cache framework
```

Good candidates:

* Expensive dashboard statistics
* Product/category data
* Configuration
* Frequently accessed public pages

Do not cache user-specific or tenant-specific data without carefully designing cache keys.

Tenant isolation must also apply to cached data.

---

# 26. FILE UPLOADS

Treat uploads as untrusted.

Validate:

* File size
* File type
* MIME type
* Extension
* Image dimensions where relevant

Do not execute uploaded files.

Store user uploads separately from application source code.

Use object storage when scale requires it.

---

# 27. EMAIL

Email sending should not block normal web requests when possible.

Use background processing for:

* Order emails
* Marketing emails
* Notifications
* Reports

Do not expose SMTP credentials.

---

# 28. BACKGROUND JOBS

If background processing is required, use an appropriate task system.

Potential architecture:

```text
Django
   ↓
Redis
   ↓
Worker
```

Good candidates:

* Emails
* Image processing
* Analytics aggregation
* Reports
* Webhook processing
* Scheduled tasks

Do not introduce Celery merely because it is popular.

Use background workers when the task genuinely benefits from asynchronous execution.

---

# 29. ANALYTICS

For ecommerce analytics, track meaningful events.

Examples:

```text
page_view
product_view
add_to_cart
begin_checkout
purchase
```

Where appropriate capture:

```text
store
session
product
traffic_source
campaign
device
country
timestamp
```

Avoid storing unnecessary personal data.

Design analytics storage separately from transactional order data when scale requires it.

---

# 30. API

Do not create APIs by default.

Use Django views + HTMX for normal web interactions.

Create APIs when needed for:

* Mobile apps
* Third-party integrations
* External clients
* Webhooks
* Public developer integrations
* Clearly defined asynchronous clients

Secure APIs with authentication, authorization and rate limiting.

---

# 31. JAVASCRIPT

Use existing JavaScript where practical.

Do not rewrite working JavaScript without a reason.

Prefer:

```text
Alpine.js
HTMX
```

over large custom JavaScript applications.

Keep JavaScript modular and readable.

Avoid global variables.

Avoid putting secrets in JavaScript.

Never put private API credentials in frontend code.

---

# 32. CSS

Preserve existing CSS behavior during migration.

Gradually migrate to Tailwind when practical.

Do not create duplicate styling systems without a reason.

Avoid:

```text
Tailwind + Bootstrap + custom framework
```

unless an existing dependency makes it unavoidable.

---

# 33. RESPONSIVE DESIGN

Every page must work on:

```text
Mobile
Tablet
Desktop
Large desktop
```

Use mobile-first Tailwind classes.

Check:

* Navigation
* Tables
* Forms
* Modals
* Cards
* Dashboard charts
* Checkout
* Product pages

Do not assume desktop-only layouts.

---

# 34. ACCESSIBILITY

Follow basic accessibility practices.

Use:

* Semantic HTML
* Labels for form controls
* Keyboard navigation
* Appropriate buttons
* Alt text
* Focus states
* Accessible dialogs
* Sufficient contrast

Do not use clickable `<div>` elements where a `<button>` or `<a>` is appropriate.

---

# 35. SEO

For public ecommerce pages:

* Semantic HTML
* Proper title
* Meta description
* Canonical URL
* Open Graph metadata
* Structured data where appropriate
* Clean URLs
* Sitemap
* Robots.txt

Product pages should be indexable where the merchant has enabled indexing.

---

# 36. TESTING

Before considering a feature complete:

1. Test the normal flow.
2. Test invalid input.
3. Test unauthorized access.
4. Test tenant isolation.
5. Test mobile layout.
6. Test HTMX interactions.
7. Test database behavior.
8. Test important edge cases.

Use Django tests for business-critical behavior.

Prioritize tests for:

* Authentication
* Authorization
* Tenant isolation
* Payments
* Orders
* Inventory
* Checkout
* Critical business rules

---

# 37. MIGRATIONS

Never manually modify production database structure.

Use:

```bash
python manage.py makemigrations
python manage.py migrate
```

Review migrations before applying them.

Never casually delete or rewrite existing migrations.

---

# 38. GIT

Make small, logical commits.

Do not commit:

```text
.env
secrets
database dumps
uploads
cache files
local virtual environments
```

Before committing:

```text
Check changed files
Check secrets
Check migrations
Run relevant tests
Review diff
```

---

# 39. ERROR HANDLING

Do not expose internal exceptions to users.

Production users should see friendly error pages.

Developers should have sufficient logging to diagnose problems.

Never expose:

* API keys
* passwords
* database credentials
* stack traces containing sensitive information

---

# 40. LOGGING

Log important operational events.

Useful examples:

```text
Authentication failure
Payment webhook
Order creation
External API failure
Background task failure
Security-sensitive action
```

Do not log passwords, tokens, payment credentials or unnecessary personal information.

---

# 41. DEVELOPMENT WORKFLOW

For every feature:

```text
1. Understand existing code
2. Identify affected files
3. Design minimal implementation
4. Implement backend
5. Connect frontend
6. Add validation
7. Add authorization
8. Test
9. Review security
10. Review UX
```

Do not modify unrelated files.

Do not refactor unrelated code while implementing a feature unless necessary.

---

# 42. FRONTEND MIGRATION WORKFLOW

When converting an existing HTML page:

```text
Existing HTML
     ↓
Identify reusable layout
     ↓
Convert to Jinja2
     ↓
Create Django URL/view
     ↓
Connect database
     ↓
Replace static data
     ↓
Use HTMX for dynamic server interactions
     ↓
Use Alpine.js for local interactions
     ↓
Use Tailwind for styling
     ↓
Test responsive behavior
```

Do not convert everything to dynamic Django code at once.

Migrate incrementally.

---

# 43. DO NOT OVERWRITE WORKING FEATURES

Before changing existing functionality:

* Understand how it works.
* Preserve existing behavior.
* Make the smallest change required.

Never replace a working implementation with a new framework/library simply because it is newer.

---

# 44. DEPENDENCY POLICY

Before adding a package, ask:

1. Is it actually necessary?
2. Can Django solve this natively?
3. Can the existing stack solve this?
4. Is the package maintained?
5. Does it introduce unnecessary complexity?
6. Does it create security or licensing concerns?

Prefer fewer dependencies.

---

# 45. CODE QUALITY

Write code that another developer can understand quickly.

Prefer:

```python
def create_order(...)
```

over unnecessarily abstract patterns.

Use clear names.

Avoid:

```python
x
tmp
foo
data2
obj1
```

for important business logic.

Keep functions reasonably small.

---

# 46. PERFORMANCE

Do not optimize blindly.

First identify the bottleneck.

Potential optimization areas:

* Database queries
* N+1 queries
* Caching
* Image optimization
* Static assets
* Pagination
* Background jobs
* CDN
* Redis

Do not introduce complexity without a measurable reason.

---

# 47. PRODUCTION CONFIGURATION

Production should use:

```text
DEBUG=False
PostgreSQL
HTTPS
Secure cookies
Environment-based secrets
Proper logging
Backups
Monitoring
```

Local development can use:

```text
SQLite
DEBUG=True
Local environment variables
```

Do not assume local configuration is safe for production.

---

# 48. WHEN YOU ARE UNSURE

Do not invent project behavior.

Inspect:

```text
models
views
urls
templates
settings
existing JavaScript
existing CSS
migrations
tests
```

before deciding.

Prefer existing project conventions over introducing a new convention.

---

# 49. FINAL IMPLEMENTATION CHECK

Before saying a feature is complete, verify:

```text
□ Backend works
□ Frontend works
□ Existing design preserved
□ Jinja2 used correctly
□ HTMX used where appropriate
□ Alpine.js used where appropriate
□ Tailwind used correctly
□ Authentication checked
□ Authorization checked
□ Tenant isolation checked
□ CSRF checked
□ Validation checked
□ Database queries reviewed
□ Mobile layout checked
□ Errors handled
□ Tests added where appropriate
□ No secrets exposed
□ No unrelated files changed
```

# 50. GOLDEN RULE

Build a **Django-first, server-rendered, secure, multi-tenant application**.

Use:

```text
Django      → backend + business logic
Jinja2      → HTML rendering
HTMX        → server-driven interactivity
Alpine.js   → lightweight browser state
Tailwind    → styling
PostgreSQL  → production database
Redis       → caching/background infrastructure when needed
```

Avoid unnecessary SPA architecture.

Preserve the existing frontend.

Build the MVP quickly, but never compromise:

**Security + tenant isolation + data integrity + maintainability.**
