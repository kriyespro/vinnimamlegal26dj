"""SEO, security-hardening and performance regression tests."""
import json
import re
from pathlib import Path

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.db import connection
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.audit.service import client_ip
from apps.portal.models import Case
from apps.portal.tests import PortalBase, login

from .urls import PAGES

PUBLIC_URLS = [reverse_name for _, reverse_name, _ in PAGES] + ["pricing"]
BASE_DIR = Path(settings.BASE_DIR)


def get(client, name, **kw):
    return client.get(reverse(name, kwargs=kw or None))


def meta(html, attr, value):
    m = re.search(rf'<meta[^>]*{attr}="{re.escape(value)}"[^>]*content="([^"]*)"', html)
    return m.group(1) if m else None


class SeoChecklistTests(TestCase):
    def pages(self):
        for name in PUBLIC_URLS:
            yield name, get(self.client, name).content.decode()
        yield "state", self.client.get("/services-by-state/gujarat").content.decode()

    def test_title_and_description_lengths(self):
        for name, html in self.pages():
            title = re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()
            desc = meta(html, "name", "description")
            self.assertLessEqual(len(title), 60, f"{name}: title {len(title)} chars: {title}")
            self.assertGreaterEqual(len(title), 15, name)
            self.assertTrue(desc and 70 <= len(desc) <= 160, f"{name}: description {len(desc or '')} chars")

    def test_titles_and_descriptions_unique(self):
        titles, descs = {}, {}
        for name, html in self.pages():
            t = re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()
            d = meta(html, "name", "description")
            self.assertNotIn(t, titles, f"{name} duplicates title of {titles.get(t)}")
            self.assertNotIn(d, descs, f"{name} duplicates description of {descs.get(d)}")
            titles[t], descs[d] = name, name

    def test_head_tags_on_every_page(self):
        for name, html in self.pages():
            self.assertIn('<html lang="en-IN">', html, name)
            self.assertRegex(html, r'<link rel="canonical" href="http://testserver/[^"]*"', name)
            self.assertEqual(html.count('rel="canonical"'), 1, name)
            for prop in ("og:title", "og:description", "og:url", "og:image", "og:type", "og:site_name"):
                self.assertTrue(meta(html, "property", prop), f"{name}: {prop}")
            self.assertTrue(meta(html, "property", "og:image").endswith("og-default.jpg"), name)
            self.assertEqual(meta(html, "name", "twitter:card"), "summary_large_image", name)
            self.assertEqual(meta(html, "name", "theme-color"), "#1D4ED8", name)
            self.assertIn("index", meta(html, "name", "robots"), name)
            self.assertIn('name="viewport"', html, name)
            self.assertIn("<main", html, name)

    def test_exactly_one_h1_and_no_skipped_heading_levels(self):
        for name, html in self.pages():
            self.assertEqual(len(re.findall(r"<h1[\s>]", html)), 1, f"{name}: h1 count")

    def test_images_have_alt_text(self):
        for name, html in self.pages():
            for tag in re.findall(r"<img\b[^>]*>", html):
                self.assertIn("alt=", tag, f"{name}: {tag[:80]}")

    def test_json_ld_is_valid_and_typed(self):
        def docs(html):
            return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]

        home = docs(get(self.client, "index").content.decode())
        types = {t for d in home for t in (d["@type"] if isinstance(d["@type"], list) else [d["@type"]])}
        self.assertTrue({"LegalService", "WebSite"} <= types, types)
        org = next(d for d in home if "Organization" in d["@type"])
        self.assertEqual(org["name"], "VinnitaLegal")
        self.assertIn("telephone", org)
        faq = docs(get(self.client, "faq").content.decode())
        faq_page = next(d for d in faq if d["@type"] == "FAQPage")
        self.assertGreaterEqual(len(faq_page["mainEntity"]), 5)
        self.assertTrue(all(q["acceptedAnswer"]["text"] for q in faq_page["mainEntity"]))
        tm = docs(get(self.client, "trademark").content.decode())
        self.assertIn("Service", {d["@type"] for d in tm})
        crumbs = next(d for d in tm if d["@type"] == "BreadcrumbList")
        self.assertEqual([i["name"] for i in crumbs["itemListElement"]], ["Home", "Trademark Registration in India"])
        self.assertFalse([d for d in docs(get(self.client, "index").content.decode()) if d["@type"] == "BreadcrumbList"])

    def test_json_ld_cannot_break_out_of_script(self):
        from .seo import dumps

        out = dumps({"x": "</script><script>alert(1)</script>"})
        self.assertNotIn("</script>", out)
        self.assertNotIn("<", out)

    def test_faq_markup_is_accessible(self):
        html = get(self.client, "faq").content.decode()
        self.assertIn("aria-expanded", html)
        self.assertIn("aria-controls=\"faq-a1\"", html)
        self.assertEqual(html.count("<h2"), len(re.findall(r'aria-controls="faq-a\d+"', html)))

    def test_search_results_are_noindex_and_portal_is_blocked(self):
        html = self.client.get(reverse("site_search"), {"q": "trademark"}).content.decode()
        self.assertEqual(meta(html, "name", "robots"), "noindex,follow")
        self.assertIn("noindex", self.client.get(reverse("site_search"))["X-Robots-Tag"])
        for path in ("/portal", "/admin/", "/healthz"):
            self.assertIn("noindex", self.client.get(path)["X-Robots-Tag"], path)

    def test_error_pages_noindex(self):
        r = self.client.get("/definitely-missing")
        self.assertContains(r, 'content="noindex"', status_code=404)

    def test_sitemap_has_lastmod_and_only_indexable_urls(self):
        xml = self.client.get("/sitemap.xml").content.decode()
        self.assertGreaterEqual(xml.count("<lastmod>"), 15)
        urls = re.findall(r"<loc>(.*?)</loc>", xml)
        self.assertGreaterEqual(len(urls), 19)
        for bad in ("/portal<", "/billing", "/admin", "/search", "/healthz", "/enquire"):
            self.assertFalse([u for u in urls if bad.strip("<") in u and not u.endswith("portal-usage-policy")], bad)
        self.assertIn("http://testserver/", urls)

    def test_robots_txt_points_to_sitemap_and_blocks_private_areas(self):
        txt = self.client.get("/robots.txt").content.decode()
        for line in ("Disallow: /portal", "Disallow: /billing", "Disallow: /admin/", "Disallow: /sd/", "Sitemap: http://testserver/sitemap.xml"):
            self.assertIn(line, txt)

    def test_manifest_icons_and_og_image_exist(self):
        for rel in ("favicon.svg", "site.webmanifest", "img/icon-192.png", "img/icon-512.png", "img/apple-touch-icon.png", "img/og-default.jpg"):
            self.assertTrue((BASE_DIR / "static" / rel).exists(), rel)
        manifest = json.loads((BASE_DIR / "static" / "site.webmanifest").read_text())
        self.assertEqual(manifest["lang"], "en-IN")
        self.assertTrue(all((BASE_DIR / "static" / i["src"]).exists() for i in manifest["icons"]))
        self.assertLess((BASE_DIR / "static/img/og-default.jpg").stat().st_size, 150_000)

    def test_internal_links_on_public_pages_resolve(self):
        from django.urls import resolve

        for name, html in self.pages():
            for href in set(re.findall(r'href="(/[^"#?]*)', html)):
                if href.startswith("/static/") or href in ("/robots.txt",):
                    continue
                resolve(href)


class SecurityHardeningTests(TestCase):
    def test_csp_uses_nonce_not_unsafe_inline_scripts(self):
        r1, r2 = self.client.get("/"), self.client.get("/")
        csp1, csp2 = r1["Content-Security-Policy"], r2["Content-Security-Policy"]
        script_src = next(p for p in csp1.split("; ") if p.startswith("script-src"))
        self.assertNotIn("'unsafe-inline'", script_src)
        self.assertIn("'nonce-", script_src)
        self.assertNotEqual(csp1, csp2)  # fresh nonce per request
        self.assertIn("upgrade-insecure-requests", csp1) if not settings.DEBUG else None

    def test_inline_scripts_carry_the_request_nonce(self):
        r = self.client.get("/")
        nonce = re.search(r"'nonce-([^']+)'", r["Content-Security-Policy"]).group(1)
        html = r.content.decode()
        for tag in re.findall(r"<script\b[^>]*>", html):
            if "src=" in tag or "application/ld+json" in tag:
                continue
            self.assertIn(f'nonce="{nonce}"', tag, tag)

    def test_no_inline_event_handlers_in_templates(self):
        pattern = re.compile(r"\son(click|change|submit|input|load|error|focus|blur|keyup|keydown)=", re.I)
        offenders = [str(p) for p in (BASE_DIR / "templates").rglob("*.html") if pattern.search(p.read_text())]
        self.assertEqual(offenders, [])

    def test_no_third_party_hosts_for_assets_in_templates(self):
        banned = ("googleapis", "gstatic", "cdn.jsdelivr", "cdn.tailwindcss", "unpkg", "cdnjs", "ui-avatars", "unsplash")
        for p in (BASE_DIR / "templates").rglob("*.html"):
            text = p.read_text()
            for b in banned:
                self.assertNotIn(b, text, f"{p} references {b}")

    def test_csrf_cookie_httponly_and_renamed_session_cookie(self):
        r = self.client.get(reverse("portal"))
        self.assertTrue(r.cookies["vl_csrf"]["httponly"])
        self.assertEqual(settings.SESSION_COOKIE_NAME, "vl_session")

    def test_security_headers_present(self):
        r = self.client.get("/")
        self.assertEqual(r["X-Frame-Options"], "DENY")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r["Referrer-Policy"], "same-origin")
        self.assertEqual(r["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertEqual(r["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertIn("camera=()", r["Permissions-Policy"])

    @override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.Argon2PasswordHasher", "django.contrib.auth.hashers.PBKDF2PasswordHasher"])
    def test_passwords_are_hashed_with_argon2(self):
        from apps.accounts.models import User

        user = User.objects.create_user(email="h@t.test", password="a-long-enough-pass-1", name="H")
        self.assertTrue(user.password.startswith("argon2$"))
        self.assertTrue(user.check_password("a-long-enough-pass-1"))

    def test_settings_pin_argon2_first(self):
        self.assertTrue(Path(BASE_DIR / "config/settings/base.py").read_text().count("Argon2PasswordHasher") >= 1)

    def test_healthz_and_security_txt(self):
        r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok", "database": True, "cache": True})
        self.assertEqual(r["Cache-Control"], "no-store")
        txt = self.client.get("/.well-known/security.txt").content.decode()
        self.assertIn("Contact: mailto:", txt)
        self.assertIn("Expires:", txt)

    def test_healthz_reports_degraded_when_cache_is_down(self):
        from unittest import mock

        with mock.patch("django.core.cache.cache.get", return_value=None):
            r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["status"], "degraded")

    def test_client_ip_trust_model(self):
        rf = RequestFactory()
        spoof = rf.get("/", HTTP_X_FORWARDED_FOR="6.6.6.6", REMOTE_ADDR="10.0.0.1")
        self.assertEqual(client_ip(spoof), "10.0.0.1")  # header ignored without trusted proxies
        with override_settings(TRUSTED_PROXY_COUNT=1):
            self.assertEqual(client_ip(rf.get("/", HTTP_X_FORWARDED_FOR="6.6.6.6, 203.0.113.9", REMOTE_ADDR="10.0.0.1")), "203.0.113.9")
            self.assertEqual(client_ip(rf.get("/", HTTP_X_FORWARDED_FOR="not-an-ip", REMOTE_ADDR="10.0.0.1")), "10.0.0.1")
            self.assertEqual(client_ip(rf.get("/", REMOTE_ADDR="10.0.0.1")), "10.0.0.1")
        with override_settings(TRUSTED_PROXY_COUNT=2):
            self.assertEqual(client_ip(rf.get("/", HTTP_X_FORWARDED_FOR="1.1.1.1, 2.2.2.2, 10.9.9.9", REMOTE_ADDR="10.0.0.1")), "2.2.2.2")

    def test_rate_limit_is_per_real_client_when_behind_a_proxy(self):
        cache.clear()
        payload = {"name": "A", "phone": "9876543210", "next": "/contact"}
        with override_settings(TRUSTED_PROXY_COUNT=1):
            from apps.leads.views import RATE_LIMIT

            for _ in range(RATE_LIMIT + 1):
                self.client.post(reverse("enquire"), payload, HTTP_X_FORWARDED_FOR="198.51.100.1", REMOTE_ADDR="10.0.0.1")
            r = self.client.post(reverse("enquire"), payload, HTTP_X_FORWARDED_FOR="198.51.100.2", REMOTE_ADDR="10.0.0.1")
        from apps.leads.models import Enquiry

        self.assertEqual(Enquiry.objects.filter(phone="9876543210").count(), RATE_LIMIT + 1)  # the 2nd visitor still got through

    def test_safe_redis_cache_degrades_instead_of_raising(self):
        from apps.core.cache import SafeRedisCache

        dead = SafeRedisCache("redis://127.0.0.1:1/0", {"OPTIONS": {"socket_connect_timeout": 0.2, "socket_timeout": 0.2}})
        self.assertEqual(dead.get("k", "fallback"), "fallback")
        self.assertIsNone(dead.set("k", "v"))
        self.assertFalse(dead.add("k", "v"))
        self.assertEqual(dead.get_many(["a"]), {})
        self.assertFalse(dead.delete("k"))

    def test_login_still_works_when_cache_backend_fails(self):
        from unittest import mock

        from apps.accounts.models import PolicyAcceptance, User

        user = User.objects.create_user(email="u@t.test", password="a-long-enough-pass-1", name="U")
        with mock.patch("apps.accounts.views.cache.get", side_effect=RuntimeError("cache down")):
            r = self.client.post(reverse("portal"), {"action": "signup", "name": "N", "email": "n@t.test", "password": "a-long-enough-pass-1", "confirm_password": "a-long-enough-pass-1", "policy": "1"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(User.objects.filter(email="n@t.test").exists())

    def test_sensitive_files_not_served_as_static(self):
        for path in ("/static/../.env", "/static/db.sqlite3", "/private_media/"):
            self.assertNotEqual(self.client.get(path).status_code, 200, path)


class PerformanceBudgetTests(PortalBase):
    def test_gzip_compresses_html(self):
        r = Client().get("/", HTTP_ACCEPT_ENCODING="gzip")
        self.assertEqual(r["Content-Encoding"], "gzip")
        self.assertIn("Accept-Encoding", r["Vary"])

    def test_public_pages_do_no_database_work(self):
        for name in ("index", "services", "pricing", "faq", "contact"):
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(reverse(name))
            self.assertLessEqual(len(ctx), 1, f"{name}: {[q['sql'][:60] for q in ctx]}")  # pricing reads offerings

    def test_css_bundle_budget_and_single_stylesheet(self):
        size = (BASE_DIR / "static/css/app.min.css").stat().st_size
        self.assertLess(size, 90_000, f"app.min.css is {size} bytes")
        html = self.client.get("/").content.decode()
        self.assertEqual(len(re.findall(r'<link rel="stylesheet"', html)), 1)
        self.assertEqual(len(re.findall(r"<script[^>]+src=", html)), 1)  # Alpine only
        self.assertIn('rel="preload"', html)

    def test_fonts_are_self_hosted_and_swap(self):
        css = (BASE_DIR / "static/css/app.min.css").read_text()
        self.assertIn("font-display:swap", css)
        self.assertNotIn("fonts.googleapis", css)
        for f in ("inter-latin-wght-normal.woff2", "inter-symbols-wght-normal.woff2"):
            self.assertLess((BASE_DIR / "static/fonts" / f).stat().st_size, 100_000)

    def _query_count(self, user):
        c = login(user)
        with CaptureQueriesContext(connection) as ctx:
            r = c.get(reverse("portal_dashboard"))
        self.assertEqual(r.status_code, 200)
        return len(ctx)

    def test_dashboard_query_count_does_not_grow_with_cases(self):
        users = [self.client1, self.partner, self.staff, self.ceo]
        before = {u.role: self._query_count(u) for u in users}
        for i in range(8):
            c = Case.objects.create(case_no=f"BULK-{i}", title=f"Bulk {i}", client=self.client1, partner=self.partner)
            c.staff.add(self.staff)
        after = {u.role: self._query_count(u) for u in users}
        for role in before:
            self.assertLessEqual(after[role], before[role] + 2, f"{role}: {before[role]} -> {after[role]} queries (N+1?)")
        for role, n in after.items():
            self.assertLess(n, 45, f"{role} dashboard uses {n} queries")

    def test_indexes_exist_for_hot_filters(self):
        from apps.billing.models import Invoice
        from apps.leads.models import Enquiry

        self.assertIn("inv_client_status", [i.name for i in Invoice._meta.indexes])
        self.assertIn("enq_status_created", [i.name for i in Enquiry._meta.indexes])
        self.assertIn("case_status", [i.name for i in Case._meta.indexes])

    def test_search_catalog_is_cached(self):
        from .search import build_search_items

        build_search_items()
        with CaptureQueriesContext(connection) as ctx:
            build_search_items()
        self.assertEqual(len(ctx), 0)


class HeadRequestTests(TestCase):
    def test_head_works_on_public_pages_for_crawlers_and_monitors(self):
        for name in PUBLIC_URLS + ["site_search"]:
            r = self.client.head(reverse(name))
            self.assertEqual(r.status_code, 200, name)
            self.assertEqual(r.content, b"", name)
        for path in ("/robots.txt", "/sitemap.xml", "/healthz", "/.well-known/security.txt", "/portal"):
            self.assertEqual(self.client.head(path).status_code, 200, path)

    def test_mutating_endpoints_still_reject_get_and_head(self):
        for name in ("enquire", "portal_logout"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 405, name)
            self.assertEqual(self.client.head(reverse(name)).status_code, 405, name)


class CanonicalUrlTests(TestCase):
    def test_trailing_slash_urls_301_to_the_canonical_page(self):
        r = self.client.get("/about/")
        self.assertEqual((r.status_code, r["Location"]), (301, "/about"))
        r = self.client.get("/search/?q=trade")
        self.assertEqual((r.status_code, r["Location"]), (301, "/search?q=trade"))
        self.assertEqual(self.client.get("/admin/").status_code, 302)  # console keeps its own trailing slash
        self.assertEqual(self.client.get("/nope/").status_code, 404)
        self.assertEqual(self.client.post("/enquire/", {}).status_code, 404)  # only GET/HEAD are redirected
