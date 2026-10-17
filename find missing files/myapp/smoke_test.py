"""Smoke tests for LexAssist portal backend."""
from __future__ import annotations

import re
import sys

import requests

BASE = "http://127.0.0.1:5000"


def main() -> None:
    s = requests.Session()

    r = s.get(BASE + "/")
    assert r.status_code == 200, r.status_code
    print("GET / OK")

    r = s.post(
        BASE + "/portal",
        data={
            "action": "login",
            "role": "partner",
            "email": "partner@lexassist.in",
            "password": "demo123",
            "policy": "1",
        },
        allow_redirects=True,
    )
    assert r.status_code == 200
    assert "LA-2026-0142" in r.text
    assert "Partner Dashboard" in r.text
    print("Partner login OK; dashboard visible")

    m = re.search(r"/portal/drafts/(\d+)/approve", r.text)
    if m:
        r2 = s.post(BASE + f"/portal/drafts/{m.group(1)}/approve", allow_redirects=True)
        assert r2.status_code == 200
        print("Draft approve OK")
    else:
        print("No pending draft form (skip)")

    s2 = requests.Session()
    r = s2.post(
        BASE + "/portal",
        data={
            "action": "send_otp",
            "role": "client",
            "email": "client@lexassist.in",
            "password": "demo123",
            "policy": "1",
        },
        allow_redirects=True,
    )
    otp_m = re.search(r"Demo OTP:\s*<strong>(\d{6})</strong>", r.text)
    if not otp_m:
        otp_m = re.search(r"Use code:\s*(\d{6})", r.text)
    assert otp_m, "OTP not found"
    otp = otp_m.group(1)
    print("Client OTP", otp)

    r = s2.post(
        BASE + "/portal",
        data={
            "action": "login",
            "role": "client",
            "email": "client@lexassist.in",
            "password": "demo123",
            "policy": "1",
            "otp": otp,
        },
        allow_redirects=True,
    )
    assert r.status_code == 200
    assert "LA-2026-0142" in r.text
    assert "LA-2026-0999" not in r.text, "ACL FAIL: other client case visible"
    print("Client login + ACL OK")

    s3 = requests.Session()
    r = s3.post(
        BASE + "/portal",
        data={
            "action": "login",
            "role": "staff",
            "email": "staff@lexassist.in",
            "password": "demo123",
            "policy": "1",
        },
        allow_redirects=True,
    )
    assert r.status_code == 200
    assert "Escalation" in r.text or "Website enquiries" in r.text or "Office" in r.text
    print("Staff login OK; office dashboard visible")
    r = s3.post(
        BASE + "/portal/escalate",
        data={"note": "Client asked for legal opinion", "case_id": ""},
        allow_redirects=True,
    )
    assert r.status_code == 200
    print("Staff escalate OK")

    s4 = requests.Session()
    r = s4.post(
        BASE + "/portal",
        data={
            "action": "login",
            "role": "ceo",
            "email": "ceo@lexassist.in",
            "password": "demo123",
            "policy": "1",
        },
        allow_redirects=True,
    )
    assert r.status_code == 200
    assert "Founder" in r.text or "command centre" in r.text
    assert "Revenue" in r.text or "revenue" in r.text.lower()
    print("CEO login OK; founder dashboard visible")
    print("ALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FAIL", type(e).__name__, e, file=sys.stderr)
        sys.exit(1)
