from django.test import TestCase
from django.urls import reverse

from .urls import PAGES


class PublicPagesTests(TestCase):
    def test_all_pages_render(self):
        for _, name, _ in PAGES:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_pricing_page(self):
        self.assertEqual(self.client.get(reverse("pricing")).status_code, 200)

    def test_state_pages(self):
        self.assertEqual(self.client.get(reverse("services-by-state")).status_code, 200)
        self.assertEqual(self.client.get(reverse("services-by-state", kwargs={"state_slug": "gujarat"})).status_code, 200)
        self.assertEqual(self.client.get("/services-by-state/nope").status_code, 404)

    def test_search(self):
        r = self.client.get(reverse("site_search"), {"q": "trademark"})
        self.assertContains(r, "Trademark")

    def test_contact_form_has_csrf(self):
        self.assertContains(self.client.get(reverse("contact")), "csrfmiddlewaretoken")

    def test_no_old_brand(self):
        self.assertNotContains(self.client.get(reverse("index")), "LexAssist")


class HardeningTests(TestCase):
    def test_friendly_404_hides_internals(self):
        r = self.client.get("/definitely-not-a-page")
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "Page not found", status_code=404)
        self.assertNotContains(r, "Traceback", status_code=404)

    def test_403_page(self):
        from apps.accounts.models import User

        user = User.objects.create_user(email="x@t.test", password="pw-long-enough-1", name="X")
        from apps.accounts.models import PolicyAcceptance
        from django.conf import settings

        PolicyAcceptance.objects.create(user=user, version=settings.POLICY_VERSION)
        self.client.force_login(user)
        r = self.client.post(reverse("portal_comms"), {})
        self.assertContains(r, "Access denied", status_code=403)

    def test_security_headers(self):
        r = self.client.get(reverse("index"))
        csp = r["Content-Security-Policy"]
        for part in ("frame-ancestors 'none'", "object-src 'none'", "https://*.razorpay.com", "'nonce-"):
            self.assertIn(part, csp)
        self.assertNotIn("cdn.tailwindcss.com", csp)
        self.assertIn("Permissions-Policy", r)
        self.assertEqual(r["X-Frame-Options"], "DENY")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r["Referrer-Policy"], "same-origin")

    def test_portal_and_billing_noindex(self):
        self.assertIn("noindex", self.client.get(reverse("portal"))["X-Robots-Tag"])
        self.assertNotIn("X-Robots-Tag", self.client.get(reverse("index")))

    def test_no_third_party_script_cdns(self):
        html = self.client.get(reverse("index")).content.decode() + self.client.get(reverse("portal")).content.decode()
        self.assertNotIn("cdn.tailwindcss.com", html)
        self.assertNotIn("cdn.jsdelivr.net", html)
        self.assertIn("css/app.min.css", html)

    def test_robots_and_sitemap(self):
        r = self.client.get("/robots.txt")
        self.assertContains(r, "Disallow: /portal")
        self.assertContains(r, "sitemap.xml")
        sm = self.client.get("/sitemap.xml")
        self.assertEqual(sm.status_code, 200)
        self.assertContains(sm, "/services-by-state/gujarat")
        self.assertNotContains(sm, "/portal<")
        self.assertNotContains(sm, "/portal/")

    def test_canonical_tag(self):
        self.assertContains(self.client.get(reverse("faq")), 'rel="canonical" href="http://testserver/faq"')

    def test_contact_details_come_from_settings(self):
        from django.test import override_settings

        with override_settings(SITE_EMAIL="hello@vinnita.test", SITE_PHONE="+91 11111 22222", SITE_WHATSAPP="911111122222"):
            html = self.client.get(reverse("contact")).content.decode()
        self.assertIn("hello@vinnita.test", html)
        self.assertIn("+91 11111 22222", html)
        self.assertIn("wa.me/911111122222", html)
        self.assertNotIn("lexassist", html.lower())


class NavTests(TestCase):
    def test_desktop_and_mobile_nav_have_all_key_links(self):
        html = self.client.get(reverse("index")).content.decode()
        for name in ("business-registration", "trademark", "partnership", "msme", "contracts", "marriage-certificate",
                     "expert-portal", "services-by-state", "services", "pricing", "blog", "about", "contact", "portal"):
            self.assertIn(f'href="{reverse(name)}"', html, name)

    def test_dropdowns_are_accessible_and_solid(self):
        html = self.client.get(reverse("index")).content.decode()
        self.assertIn('aria-haspopup="true"', html)
        self.assertIn(":aria-expanded", html)
        self.assertIn("dd-menu", html)
        self.assertNotIn("glass-card rounded-2xl p-4 shadow-2xl max-h-[70vh]", html)

    def test_current_page_highlighted(self):
        html = self.client.get(reverse("pricing")).content.decode()
        self.assertIn('aria-current="page"', html)
        self.assertNotIn('aria-current="page"', self.client.get(reverse("faq")).content.decode())

    def test_no_dead_links_in_nav(self):
        from django.urls import resolve
        import re

        html = self.client.get(reverse("index")).content.decode()
        nav = html[html.index("<nav"):html.index("</nav>")]
        for href in set(re.findall(r'href="(/[^"#?]*)', nav)):
            resolve(href)  # raises Resolver404 for dead links


class StateEnquiryFlashTests(TestCase):
    def test_state_page_shows_confirmation_after_enquiry(self):
        r = self.client.post(reverse("enquire"), {"name": "A", "phone": "9876543210", "source_page": "services-by-state/gujarat",
                                                  "next": "/services-by-state/gujarat#enquiry"}, follow=True)
        self.assertContains(r, "Request received")
        self.assertEqual(r.redirect_chain[-1][0], "/services-by-state/gujarat#enquiry")


class HomeAndTopBarTests(TestCase):
    def test_top_bar_shows_phone_and_email_on_every_page(self):
        from django.test import override_settings

        with override_settings(SITE_EMAIL="help@vinnita.test", SITE_PHONE="+91 22222 33333", SITE_WHATSAPP="912222233333"):
            for name in ("index", "services", "pricing", "contact", "faq"):
                html = self.client.get(reverse(name)).content.decode()
                self.assertIn('href="tel:+912222233333"', html, name)
                self.assertIn('href="mailto:help@vinnita.test"', html, name)
                self.assertIn("+91 22222 33333", html, name)

    def test_home_hero_callback_form(self):
        html = self.client.get(reverse("index")).content.decode()
        self.assertIn("hero-light", html)
        self.assertIn("Get a free callback", html)
        self.assertIn('action="/enquire"', html)
        self.assertIn("csrfmiddlewaretoken", html)
        self.assertIn("Sample client dashboard", html)

    def test_home_callback_submits_and_returns_to_home(self):
        r = self.client.post(reverse("enquire"), {"name": "Asha", "phone": "9876543210", "source": "home-callback", "next": "/#callback"}, follow=True)
        self.assertContains(r, "Request received")
        self.assertEqual(r.redirect_chain[-1][0], "/#callback")
        from apps.leads.models import Enquiry

        self.assertEqual(Enquiry.objects.get().source_page, "home-callback")

    def test_no_unverifiable_superlative_in_hero(self):
        self.assertNotContains(self.client.get(reverse("index")), "Most Trusted")
