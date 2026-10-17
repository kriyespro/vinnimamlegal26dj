"""Login + logout checks for client, partner, staff, and CEO dashboards."""
from __future__ import annotations

import re
import sys

import requests

BASE = "http://127.0.0.1:5000"
results: list[tuple[bool, str, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    results.append((bool(cond), name, detail))
    status = "PASS" if cond else "FAIL"
    print(f"{status}  {name}" + (f"  |  {detail}" if detail else ""))


def main() -> int:
    roles = [
        {
            "role": "partner",
            "email": "partner@lexassist.in",
            "password": "demo123",
            "otp": False,
        },
        {
            "role": "staff",
            "email": "staff@lexassist.in",
            "password": "demo123",
            "otp": False,
        },
        {
            "role": "ceo",
            "email": "ceo@lexassist.in",
            "password": "demo123",
            "otp": False,
        },
        {
            "role": "client",
            "email": "client@lexassist.in",
            "password": "demo123",
            "otp": True,
        },
    ]

    for cfg in roles:
        role = cfg["role"]
        print(f"\n==== {role.upper()} ====")
        s = requests.Session()

        r = s.get(BASE + "/portal")
        ok(f"{role}: GET /portal login page", r.status_code == 200 and "Sign In" in r.text)

        anon = requests.Session()
        r = anon.get(BASE + "/portal/dashboard", allow_redirects=True)
        ok(
            f"{role}: dashboard blocked when logged out",
            r.status_code == 200 and ("Portal Login" in r.text or "sign in" in r.text.lower()),
        )

        if cfg["otp"]:
            r = s.post(
                BASE + "/portal",
                data={
                    "action": "send_otp",
                    "role": "client",
                    "email": cfg["email"],
                    "password": cfg["password"],
                    "policy": "1",
                },
                allow_redirects=True,
            )
            otp_m = re.search(r"Demo OTP:\s*<strong>(\d{6})</strong>", r.text)
            if not otp_m:
                otp_m = re.search(r"Use code:\s*(\d{6})", r.text)
            ok(f"{role}: OTP sent (client verification)", bool(otp_m), otp_m.group(1) if otp_m else "")
            otp = otp_m.group(1) if otp_m else "000000"
            login_data = {
                "action": "login",
                "role": role,
                "email": cfg["email"],
                "password": cfg["password"],
                "policy": "1",
                "otp": otp,
            }
        else:
            login_data = {
                "action": "login",
                "role": role,
                "email": cfg["email"],
                "password": cfg["password"],
                "policy": "1",
            }

        r = s.post(BASE + "/portal", data=login_data, allow_redirects=True)
        text = r.text
        if role == "partner":
            dash_ok = r.status_code == 200 and "Partner" in text and "LA-2026" in text
        elif role == "staff":
            dash_ok = r.status_code == 200 and (
                "Office" in text or "enquir" in text.lower() or "Escalat" in text
            )
        elif role == "ceo":
            dash_ok = r.status_code == 200 and (
                "Founder" in text or "Revenue" in text or "command" in text.lower()
            )
        else:
            dash_ok = (
                r.status_code == 200
                and "LA-2026-0142" in text
                and ("Client" in text or "Progress" in text)
            )
        ok(f"{role}: login to dashboard", dash_ok, f"url={r.url}")

        has_logout = "logout" in text.lower() and ("form" in text.lower() or "post" in text.lower())
        ok(f"{role}: logout control present", has_logout)

        r2 = s.get(BASE + "/portal/dashboard", allow_redirects=True)
        stay_in = r2.status_code == 200 and "Portal Login" not in r2.text[:800]
        ok(f"{role}: session kept on dashboard reload", stay_in)

        r3 = s.post(BASE + "/portal/logout", allow_redirects=True)
        ok(
            f"{role}: logout returns to login",
            r3.status_code == 200 and ("Portal Login" in r3.text or "Sign In" in r3.text),
            f"url={r3.url}",
        )

        r4 = s.get(BASE + "/portal/dashboard", allow_redirects=True)
        blocked = "Portal Login" in r4.text or "sign in" in r4.text.lower() or r4.url.rstrip("/").endswith(
            "/portal"
        )
        ok(f"{role}: dashboard blocked after logout", blocked, f"url={r4.url}")

    print("\n==== NEGATIVE CHECKS ====")
    s = requests.Session()
    r = s.post(
        BASE + "/portal",
        data={
            "action": "login",
            "role": "partner",
            "email": "partner@lexassist.in",
            "password": "demo123",
        },
        allow_redirects=True,
    )
    ok(
        "login without policy stays/fails to portal",
        "Portal Login" in r.text or "policy" in r.text.lower(),
    )

    r = s.post(
        BASE + "/portal",
        data={
            "action": "login",
            "role": "staff",
            "email": "partner@lexassist.in",
            "password": "demo123",
            "policy": "1",
        },
        allow_redirects=True,
    )
    ok(
        "wrong role (partner as staff) rejected",
        "registered as partner" in r.text.lower() or "Portal Login" in r.text,
    )

    r = requests.get(BASE + "/portal")
    has_signup = any(
        x in r.text.lower() for x in ("sign up", "signup", "create account", "register now")
    )
    ok(
        "no public self-signup form (login-only portal)",
        not has_signup,
        "use provisioned demo accounts",
    )

    passed = sum(1 for c, _, _ in results if c)
    failed = sum(1 for c, _, _ in results if not c)
    print(f"\nSUMMARY: {passed} passed, {failed} failed of {len(results)}")
    if failed:
        print("FAILED:")
        for c, n, d in results:
            if not c:
                print(f"  - {n}  {d}")
        return 1
    print("ALL AUTH CHECKS PASSED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.exceptions.ConnectionError:
        print("FAIL  Flask server not running at", BASE)
        raise SystemExit(1)
