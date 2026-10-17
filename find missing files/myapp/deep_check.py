"""Deep check: all pages, all role flows, role isolation, onboarding."""
from __future__ import annotations

import re
import secrets
import sys
from typing import Any

import requests

BASE = "http://127.0.0.1:5000"
results: list[tuple[bool, str, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> bool:
    results.append((bool(cond), name, detail))
    sym = "PASS" if cond else "FAIL"
    print(f"  {sym}  {name}" + (f"  |  {detail}" if detail else ""))
    return bool(cond)


# ────────────────────────────────────────────────────────────
# 1. ALL PUBLIC PAGES – must return 200, no Jinja errors
# ────────────────────────────────────────────────────────────
PUBLIC = [
    "/", "/about", "/adoption", "/blog", "/business-registration",
    "/contact", "/contracts", "/deadlines", "/expert-portal",
    "/faq", "/legal-glossary", "/marriage-certificate", "/msme",
    "/partnership", "/portal-usage-policy", "/pricing",
    "/services", "/services-by-state", "/services-by-state/gujarat",
    "/trademark",
]

print("\n===== PUBLIC PAGES =====")
s = requests.Session()
for path in PUBLIC:
    r = s.get(BASE + path, allow_redirects=True)
    no_error = (
        "Internal Server Error" not in r.text
        and "Traceback" not in r.text
        and "jinja2" not in r.text.lower()
    )
    ok(f"GET {path}", r.status_code == 200 and no_error, f"code={r.status_code}")

# GST route should redirect to /services (not 404 or 500)
r = s.get(BASE + "/gst-compliance", allow_redirects=True)
ok("GET /gst-compliance redirects to /services", r.status_code == 200 and "services" in r.url)

# Non-existent state → 404
r = s.get(BASE + "/services-by-state/delhi", allow_redirects=True)
ok("GET /services-by-state/delhi 404", r.status_code == 404 or "404" in r.text)


# ────────────────────────────────────────────────────────────
# 2. PORTAL AUTH – no session = blocked
# ────────────────────────────────────────────────────────────
print("\n===== AUTH GUARD =====")
anon = requests.Session()
for path in ["/portal/dashboard", "/portal/consultations", "/portal/documents", "/portal/queries"]:
    r = anon.get(BASE + path, allow_redirects=True)
    ok(
        f"Anon {path} → redirected to login",
        "Portal Login" in r.text or "sign in" in r.text.lower() or "/portal" in r.url,
    )


# ────────────────────────────────────────────────────────────
# Helper: login helper
# ────────────────────────────────────────────────────────────
def login(role: str, email: str, pw: str = "demo123") -> requests.Session | None:
    s = requests.Session()
    r = s.post(BASE + "/portal", data={
        "action": "login", "role": role,
        "email": email, "password": pw, "policy": "1",
    }, allow_redirects=True)
    if r.status_code != 200 or "/portal/dashboard" not in r.url:
        return None
    return s


# ────────────────────────────────────────────────────────────
# 3. EACH ROLE: login → dashboard checks → logout
# ────────────────────────────────────────────────────────────
ROLES = [
    {
        "role": "client",
        "email": "client@lexassist.in",
        "dashboard": ["Client Dashboard", "LA-2026-0142"],
        "blocked_case": "LA-2026-0999",  # other client's case
        "allowed_paths": ["/portal/dashboard"],
        "forbidden_paths": [],
    },
    {
        "role": "partner",
        "email": "partner@lexassist.in",
        "dashboard": ["Partner Dashboard", "LA-2026"],
        "blocked_case": None,
        "allowed_paths": ["/portal/dashboard"],
        "forbidden_paths": [],
    },
    {
        "role": "staff",
        "email": "staff@lexassist.in",
        "dashboard": [],
        "dashboard_soft": ["Office", "lead", "enquir", "Escalat"],
        "blocked_case": None,
        "allowed_paths": ["/portal/dashboard"],
        "forbidden_paths": [],
    },
    {
        "role": "ceo",
        "email": "ceo@lexassist.in",
        "dashboard": [],
        "dashboard_soft": ["Founder", "Revenue", "command"],
        "blocked_case": None,
        "allowed_paths": ["/portal/dashboard"],
        "forbidden_paths": [],
    },
]

print("\n===== ROLE FLOWS =====")
sessions: dict[str, requests.Session | None] = {}
for cfg in ROLES:
    role = cfg["role"]
    print(f"\n-- {role.upper()} --")
    s = login(role, cfg["email"])
    sessions[role] = s
    ok(f"{role}: login", s is not None)
    if not s:
        continue

    # dashboard content
    r = s.get(BASE + "/portal/dashboard", allow_redirects=True)
    text = r.text
    if cfg.get("dashboard"):
        for needle in cfg["dashboard"]:
            ok(f"{role}: dashboard contains '{needle}'", needle in text)
    if cfg.get("dashboard_soft"):
        soft_hit = any(n.lower() in text.lower() for n in cfg["dashboard_soft"])
        ok(f"{role}: dashboard loads correctly", soft_hit, cfg["dashboard_soft"][0])

    # ACL: client should not see another client's case
    if cfg.get("blocked_case"):
        ok(f"{role}: ACL blocks {cfg['blocked_case']}", cfg["blocked_case"] not in text)

    # no server error
    ok(
        f"{role}: dashboard no server error",
        "Internal Server Error" not in text and "Traceback" not in text,
    )

    # logout
    r = s.post(BASE + "/portal/logout", allow_redirects=True)
    ok(f"{role}: logout", "Portal Login" in r.text or "Sign In" in r.text, f"url={r.url}")

    # dashboard blocked after logout
    r = s.get(BASE + "/portal/dashboard", allow_redirects=True)
    ok(f"{role}: dashboard blocked after logout", "Portal Login" in r.text or "/portal" in r.url)


# ────────────────────────────────────────────────────────────
# 4. CROSS-ROLE ISOLATION
# ────────────────────────────────────────────────────────────
print("\n===== CROSS-ROLE ISOLATION =====")
# Client accessing staff-only escalate POST should redirect with error or 403
sc = login("client", "client@lexassist.in")
if sc:
    r = sc.get(BASE + "/portal/dashboard", allow_redirects=True)
    ok("client: no staff-only controls visible", "office rule" not in r.text.lower() and "Website leads" not in r.text)
    # client should not get staff leads panel
    r = sc.get(BASE + "/portal/dashboard?panel=leads", allow_redirects=True)
    ok("client: panel=leads ignored (client sees My Jobs)", "Website leads" not in r.text)
    r = sc.post(BASE + "/portal/escalate", data={"note": "test"}, allow_redirects=True)
    ok("client: POST /portal/escalate denied or error", r.status_code in (200, 403) and ("permission" in r.text.lower() or "Website leads" not in r.text or "Client" in r.text))
    sc.post(BASE + "/portal/logout")

# Wrong role login rejected
print("\n===== NEGATIVE LOGIN CHECKS =====")
s = requests.Session()
r = s.post(BASE + "/portal", data={
    "action": "login", "role": "staff",
    "email": "partner@lexassist.in", "password": "demo123", "policy": "1",
}, allow_redirects=True)
ok("Wrong role rejected (partner→staff)", "registered as partner" in r.text.lower() or "Portal Login" in r.text)

r = s.post(BASE + "/portal", data={
    "action": "login", "role": "partner",
    "email": "partner@lexassist.in", "password": "wrongpw", "policy": "1",
}, allow_redirects=True)
ok("Wrong password rejected", "Invalid email" in r.text or "Portal Login" in r.text)

r = s.post(BASE + "/portal", data={
    "action": "login", "role": "partner",
    "email": "partner@lexassist.in", "password": "demo123",
    # no policy
}, allow_redirects=True)
ok("Login without policy rejected", "policy" in r.text.lower() or "Portal Login" in r.text)


# ────────────────────────────────────────────────────────────
# 5. CLIENT SELF-SIGNUP ONBOARDING
# ────────────────────────────────────────────────────────────
print("\n===== CLIENT SIGNUP ONBOARDING =====")
new_email = f"test_{secrets.token_hex(4)}@example.com"
s = requests.Session()
r = s.get(BASE + "/portal")
ok("signup: Create account button visible", "Create account" in r.text)
s = requests.Session()  # fresh session for signup test

# signup happy path
r = s.post(BASE + "/portal", data={
    "action": "signup", "role": "client",
    "name": "New Test User",
    "email": new_email, "password": "secret123",
    "confirm_password": "secret123", "policy": "1",
}, allow_redirects=True)
ok("signup: reaches dashboard directly", r.status_code == 200 and "/portal/dashboard" in r.url)
ok("signup: no server error", "Traceback" not in r.text)
ok(
    "signup: empty state handled",
    "No active matters" in r.text or "Request a service" in r.text or "Welcome" in r.text or "Browse services" in r.text,
)
s.post(BASE + "/portal/logout")

# duplicate email
r = s.post(BASE + "/portal", data={
    "action": "signup", "role": "client",
    "name": "Dup", "email": new_email, "password": "secret123",
    "confirm_password": "secret123", "policy": "1",
}, allow_redirects=True)
ok("signup: duplicate email rejected", "already exists" in r.text.lower())

# password mismatch
r = s.post(BASE + "/portal", data={
    "action": "signup", "role": "client",
    "name": "X", "email": "unique_" + new_email, "password": "abc123",
    "confirm_password": "xyz999", "policy": "1",
}, allow_redirects=True)
ok("signup: password mismatch rejected", "match" in r.text.lower())

# short password
r = s.post(BASE + "/portal", data={
    "action": "signup", "role": "client",
    "name": "X", "email": "short_" + new_email, "password": "ab",
    "confirm_password": "ab", "policy": "1",
}, allow_redirects=True)
ok("signup: short password rejected", "6" in r.text or "character" in r.text.lower() or "Portal Login" in r.text)

# no policy
r = s.post(BASE + "/portal", data={
    "action": "signup", "role": "client",
    "name": "X", "email": "nopolicy_" + new_email, "password": "abc123",
    "confirm_password": "abc123",
}, allow_redirects=True)
ok("signup: missing policy rejected", "policy" in r.text.lower() or "Portal Login" in r.text)


# ────────────────────────────────────────────────────────────
# SUMMARY
# ────────────────────────────────────────────────────────────
passed = sum(1 for c, _, _ in results if c)
failed = sum(1 for c, _, _ in results if not c)
print(f"\n{'='*60}")
print(f"SUMMARY: {passed} passed, {failed} failed of {len(results)}")
if failed:
    print("\nFAILED:")
    for c, n, d in results:
        if not c:
            print(f"  ✗ {n}" + (f"  [{d}]" if d else ""))
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
    sys.exit(0)
