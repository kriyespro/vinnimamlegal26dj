from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from .models import Enquiry
from .views import RATE_LIMIT


class EnquiryTests(TestCase):
    def setUp(self):
        cache.clear()

    def post(self, **over):
        data = {"name": "Asha", "phone": "+91 98765 43210", "source": "contact", "next": "/contact"}
        data.update(over)
        return self.client.post(reverse("enquire"), data)

    def test_valid_saves(self):
        r = self.post()
        self.assertRedirects(r, "/contact", fetch_redirect_response=False)
        self.assertEqual(Enquiry.objects.count(), 1)
        self.assertEqual(Enquiry.objects.get().source_page, "contact")

    def test_invalid_phone_rejected(self):
        self.post(phone="abc")
        self.assertEqual(Enquiry.objects.count(), 0)

    def test_honeypot_silently_dropped(self):
        self.post(website="http://spam")
        self.assertEqual(Enquiry.objects.count(), 0)

    def test_open_redirect_blocked(self):
        r = self.post(next="https://evil.example/")
        self.assertEqual(r["Location"], reverse("contact"))
        r = self.post(next="//evil.example/")
        self.assertEqual(r["Location"], reverse("contact"))

    def test_rate_limit(self):
        for _ in range(RATE_LIMIT):
            self.post()
        self.post()
        self.assertEqual(Enquiry.objects.count(), RATE_LIMIT)

    def test_csrf_enforced(self):
        c = Client(enforce_csrf_checks=True)
        r = c.post(reverse("enquire"), {"name": "A", "phone": "9876543210"})
        self.assertEqual(r.status_code, 403)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(reverse("enquire")).status_code, 405)


    def test_missing_next_falls_back_to_referer_page(self):
        r = self.client.post(reverse("enquire"), {"name": "A", "phone": "9876543210"}, HTTP_REFERER="http://testserver/services-by-state/gujarat")
        self.assertEqual(r["Location"], "/services-by-state/gujarat")

    def test_foreign_referer_ignored(self):
        r = self.client.post(reverse("enquire"), {"name": "A", "phone": "9876543210"}, HTTP_REFERER="https://evil.example/x")
        self.assertEqual(r["Location"], reverse("contact"))
