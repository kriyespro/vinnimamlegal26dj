import hashlib
import hmac
import json
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import PolicyAcceptance, User
from apps.audit.models import AuditLog
from apps.portal.models import Case, CaseUpdate, Consultation

from . import services
from .models import Invoice, Offering, Payment, RazorpayEvent

KEY_SECRET = "test_key_secret"
WH_SECRET = "test_webhook_secret"
PW = "correct-horse-battery-9"


def mk_user(email, role):
    from django.conf import settings

    u = User.objects.create_user(email=email, password=PW, name=email.split("@")[0], role=role)
    PolicyAcceptance.objects.create(user=u, version=settings.POLICY_VERSION)
    return u


def login(user):
    c = Client()
    c.force_login(user)
    return c


def sign_checkout(order_id, payment_id, secret=KEY_SECRET):
    return hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def webhook_body(event, order_id, payment_id, amount, currency="INR", **extra):
    entity = {"id": payment_id, "order_id": order_id, "amount": amount, "currency": currency, **extra}
    return json.dumps({"event": event, "payload": {"payment": {"entity": entity}}}).encode()


@override_settings(RAZORPAY_KEY_ID="rzp_test_x", RAZORPAY_KEY_SECRET=KEY_SECRET, RAZORPAY_WEBHOOK_SECRET=WH_SECRET)
class BillingBase(TestCase):
    def setUp(self):
        self.client1 = mk_user("c1@t.test", "client")
        self.client2 = mk_user("c2@t.test", "client")
        self.partner = mk_user("p@t.test", "partner")
        self.ceo = mk_user("ceo@t.test", "ceo")
        self.case = Case.objects.create(case_no="T-1", title="T", client=self.client1, partner=self.partner)
        self.invoice = services.create_invoice(client=self.client1, kind="case", amount="1234.50", description="Fee", case=self.case)
        self.rzp = mock.MagicMock()
        self.rzp.order.create.return_value = {"id": "order_1"}
        patcher = mock.patch("apps.billing.services.get_client", return_value=self.rzp)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_payment(self, order_id="order_1"):
        return Payment.objects.create(invoice=self.invoice, razorpay_order_id=order_id, amount_paise=123450)

    def post_webhook(self, body, event_id="evt_1", secret=WH_SECRET, signature=None):
        sig = signature if signature is not None else hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return Client(enforce_csrf_checks=True).post(
            reverse("billing_webhook"), data=body, content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sig, HTTP_X_RAZORPAY_EVENT_ID=event_id,
        )


class BuyTests(BillingBase):
    def setUp(self):
        super().setUp()
        self.offering = Offering.objects.create(slug="trademark", name="Trademark", amount="6999", active=True)

    def test_anonymous_redirected_to_login_with_next(self):
        r = Client().post(reverse("billing_buy", kwargs={"slug": "trademark"}))
        self.assertIn(reverse("portal"), r["Location"])
        self.assertIn("next=", r["Location"])

    def test_amount_comes_from_database_not_request(self):
        r = login(self.client1).post(reverse("billing_buy", kwargs={"slug": "trademark"}), {"amount": "1"})
        inv = Invoice.objects.exclude(pk=self.invoice.pk).get()
        self.assertEqual(str(inv.amount), "6999.00")
        self.assertEqual(inv.client, self.client1)
        self.assertRedirects(r, reverse("billing_invoice", kwargs={"invoice_id": inv.pk}), fetch_redirect_response=False)

    def test_reclick_reuses_open_invoice(self):
        c = login(self.client1)
        for _ in range(2):
            c.post(reverse("billing_buy", kwargs={"slug": "trademark"}))
        self.assertEqual(Invoice.objects.filter(kind="service").count(), 1)

    def test_inactive_offering_404_and_non_client_403(self):
        self.offering.active = False
        self.offering.save()
        self.assertEqual(login(self.client1).post(reverse("billing_buy", kwargs={"slug": "trademark"})).status_code, 404)
        self.offering.active = True
        self.offering.save()
        self.assertEqual(login(self.partner).post(reverse("billing_buy", kwargs={"slug": "trademark"})).status_code, 403)

    def test_pricing_page_shows_pay_button_only_for_active(self):
        self.assertContains(self.client.get(reverse("pricing")), "Pay online")
        Offering.objects.update(active=False)
        self.assertNotContains(self.client.get(reverse("pricing")), "Pay online")


class PayTests(BillingBase):
    def pay(self, user=None, invoice=None):
        return login(user or self.client1).post(reverse("billing_pay", kwargs={"invoice_id": (invoice or self.invoice).pk}), {"amount": "1"})

    def test_order_amount_is_server_side_paise(self):
        r = self.pay()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.rzp.order.create.call_args[0][0]["amount"], 123450)
        data = r.json()
        self.assertEqual((data["order_id"], data["amount"], data["key"]), ("order_1", 123450, "rzp_test_x"))
        self.assertNotIn(KEY_SECRET, r.content.decode())

    def test_existing_order_reused(self):
        self.pay()
        self.pay()
        self.assertEqual(self.rzp.order.create.call_count, 1)
        self.assertEqual(Payment.objects.count(), 1)

    def test_other_clients_invoice_404(self):
        self.assertEqual(self.pay(user=self.client2).status_code, 404)
        self.assertEqual(login(self.client2).get(reverse("billing_invoice", kwargs={"invoice_id": self.invoice.pk})).status_code, 404)

    def test_paid_invoice_not_payable(self):
        self.invoice.status = "Paid"
        self.invoice.save()
        self.assertEqual(self.pay().status_code, 400)

    def test_not_configured_returns_503(self):
        with mock.patch("apps.billing.services.get_client", side_effect=services.BillingNotConfigured("off")):
            self.assertEqual(self.pay().status_code, 503)

    def test_razorpay_failure_is_friendly(self):
        self.rzp.order.create.side_effect = RuntimeError("boom: secret details")
        r = self.pay()
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("boom", r.content.decode())

    def test_role_gate(self):
        self.assertEqual(self.pay(user=self.partner).status_code, 403)

    def test_invoice_page_renders_without_secret(self):
        r = login(self.client1).get(reverse("billing_invoice", kwargs={"invoice_id": self.invoice.pk}))
        self.assertContains(r, "VL-INV-")
        self.assertNotContains(r, KEY_SECRET)


class VerifyTests(BillingBase):
    def verify(self, *, user=None, order="order_1", pid="pay_1", sig=None):
        return login(user or self.client1).post(
            reverse("billing_verify"),
            {"razorpay_order_id": order, "razorpay_payment_id": pid, "razorpay_signature": sig if sig is not None else sign_checkout(order, pid)},
        )

    def setUp(self):
        super().setUp()
        self.payment = self.make_payment()
        self.rzp.payment.fetch.return_value = {"order_id": "order_1", "amount": 123450, "currency": "INR", "status": "captured"}

    def test_valid_payment_marks_paid_and_notifies_case(self):
        r = self.verify()
        self.assertRedirects(r, reverse("billing_invoice", kwargs={"invoice_id": self.invoice.pk}), fetch_redirect_response=False)
        self.invoice.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual((self.invoice.status, self.payment.status, self.payment.razorpay_payment_id), ("Paid", "captured", "pay_1"))
        self.assertTrue(CaseUpdate.objects.filter(case=self.case, body__contains="Payment received").exists())
        self.assertTrue(AuditLog.objects.filter(action="payment_captured").exists())

    def test_bad_signature_does_not_mark_paid(self):
        self.verify(sig="0" * 64)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "Pending")
        self.rzp.payment.fetch.assert_not_called()

    def test_signature_from_wrong_secret_rejected(self):
        self.verify(sig=sign_checkout("order_1", "pay_1", secret="attacker"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "Pending")

    def test_amount_mismatch_from_razorpay_rejected(self):
        self.rzp.payment.fetch.return_value["amount"] = 100
        self.verify()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "Pending")

    def test_order_mismatch_rejected(self):
        self.rzp.payment.fetch.return_value["order_id"] = "order_other"
        self.verify()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "Pending")

    def test_authorized_not_captured_stays_pending(self):
        self.rzp.payment.fetch.return_value["status"] = "authorized"
        self.verify()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "Pending")

    def test_razorpay_outage_leaves_pending_for_webhook(self):
        self.rzp.payment.fetch.side_effect = RuntimeError("down")
        self.verify()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "Pending")

    def test_other_client_cannot_verify_my_order(self):
        self.assertEqual(self.verify(user=self.client2).status_code, 400)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "Pending")

    def test_idempotent(self):
        self.verify()
        self.verify()
        self.assertEqual(CaseUpdate.objects.filter(case=self.case, body__contains="Payment received").count(), 1)

    def test_csrf_enforced(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.client1)
        self.assertEqual(c.post(reverse("billing_verify"), {}).status_code, 403)


class WebhookTests(BillingBase):
    def setUp(self):
        super().setUp()
        self.payment = self.make_payment()

    def captured(self, amount=123450, **kw):
        return webhook_body("payment.captured", "order_1", "pay_1", amount, status="captured", **kw)

    def test_bad_or_missing_signature_rejected(self):
        self.assertEqual(self.post_webhook(self.captured(), signature="bad").status_code, 400)
        self.assertEqual(self.post_webhook(self.captured(), secret="other").status_code, 400)
        self.assertFalse(RazorpayEvent.objects.exists())
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "Pending")

    def test_no_secret_configured_rejects_everything(self):
        with override_settings(RAZORPAY_WEBHOOK_SECRET=""):
            self.assertEqual(self.post_webhook(self.captured(), signature="").status_code, 400)

    def test_captured_marks_paid_without_csrf_or_login(self):
        r = self.post_webhook(self.captured())
        self.assertEqual(r.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "Paid")

    def test_replay_is_ignored(self):
        body = self.captured()
        self.post_webhook(body)
        r = self.post_webhook(body)
        self.assertEqual(r.content, b"duplicate")
        self.assertEqual(CaseUpdate.objects.filter(body__contains="Payment received").count(), 1)
        self.assertEqual(RazorpayEvent.objects.count(), 1)

    def test_different_event_ids_same_payment_still_single_effect(self):
        self.post_webhook(self.captured(), event_id="e1")
        self.post_webhook(webhook_body("order.paid", "order_1", "pay_1", 123450), event_id="e2")
        self.assertEqual(CaseUpdate.objects.filter(body__contains="Payment received").count(), 1)

    def test_amount_or_currency_mismatch_ignored(self):
        self.post_webhook(self.captured(amount=1), event_id="e1")
        self.post_webhook(webhook_body("payment.captured", "order_1", "pay_1", 123450, currency="USD"), event_id="e2")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "Pending")

    def test_failed_payment_recorded_but_does_not_override_captured(self):
        self.post_webhook(webhook_body("payment.failed", "order_1", "pay_x", 123450, error_description="Card declined"), event_id="e1")
        self.payment.refresh_from_db()
        self.assertEqual((self.payment.status, self.payment.failure_reason), ("failed", "Card declined"))
        self.payment.status = "created"
        self.payment.save()
        self.post_webhook(self.captured(), event_id="e2")
        self.post_webhook(webhook_body("payment.failed", "order_1", "pay_y", 123450), event_id="e3")
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "captured")

    def test_unknown_order_and_invalid_json_and_missing_event_id(self):
        r = self.post_webhook(webhook_body("payment.captured", "order_zzz", "pay_9", 100))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.post_webhook(b"not json").status_code, 400)
        body = self.captured()
        sig = hmac.new(WH_SECRET.encode(), body, hashlib.sha256).hexdigest()
        r = Client().post(reverse("billing_webhook"), data=body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=sig)
        self.assertEqual(r.status_code, 400)

    def test_second_payment_on_paid_invoice_flagged_for_review(self):
        self.post_webhook(self.captured(), event_id="e1")
        second = Payment.objects.create(invoice=self.invoice, razorpay_order_id="order_2", amount_paise=123450)
        self.post_webhook(webhook_body("payment.captured", "order_2", "pay_2", 123450), event_id="e2")
        second.refresh_from_db()
        self.assertTrue(second.needs_review)
        self.assertEqual(CaseUpdate.objects.filter(body__contains="Payment received").count(), 1)

    def test_refund_processed_marks_invoice_refunded(self):
        self.post_webhook(self.captured(), event_id="e1")
        body = json.dumps({"event": "refund.processed", "payload": {"refund": {"entity": {"id": "rfnd_1", "payment_id": "pay_1"}}}}).encode()
        self.post_webhook(body, event_id="e2")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "Refunded")

    def test_get_not_allowed(self):
        self.assertEqual(Client().get(reverse("billing_webhook")).status_code, 405)


class RefundTests(BillingBase):
    def setUp(self):
        super().setUp()
        self.payment = self.make_payment()
        services.mark_paid(self.payment.pk, "pay_1", source="test")
        self.rzp.payment.refund.return_value = {"id": "rfnd_1"}
        self.url = reverse("billing_refund", kwargs={"payment_id": self.payment.pk})

    def test_only_ceo(self):
        for user in (self.client1, self.partner):
            self.assertEqual(login(user).post(self.url).status_code, 403)
        self.rzp.payment.refund.assert_not_called()

    def test_ceo_refunds_full_amount(self):
        login(self.ceo).post(self.url)
        self.rzp.payment.refund.assert_called_once_with("pay_1", {"amount": 123450})
        self.invoice.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual((self.invoice.status, self.payment.status), ("Refunded", "refunded"))
        self.assertTrue(AuditLog.objects.filter(action="payment_refunded").exists())

    def test_cannot_refund_twice(self):
        login(self.ceo).post(self.url)
        login(self.ceo).post(self.url)
        self.assertEqual(self.rzp.payment.refund.call_count, 1)

    def test_dashboard_shows_refund_button_to_ceo(self):
        self.assertContains(login(self.ceo).get(reverse("portal_dashboard")), "billing/payments/%d/refund" % self.payment.pk)


class ConsultationFeeTests(BillingBase):
    def book(self):
        return login(self.client1).post(reverse("portal_consultation_book"), {
            "practice_area": "Contracts", "preferred_date": "2099-01-01", "preferred_time": "10:00", "mode": "Video"})

    def test_free_when_no_fee_offering(self):
        r = self.book()
        self.assertRedirects(r, reverse("portal_dashboard"), fetch_redirect_response=False)
        self.assertFalse(Invoice.objects.filter(kind="consultation").exists())

    def test_fee_creates_invoice_and_blocks_confirmation_until_paid(self):
        Offering.objects.create(slug="consult", name="Consultation", kind="consultation", amount="500", active=True)
        r = self.book()
        inv = Invoice.objects.get(kind="consultation")
        self.assertRedirects(r, reverse("billing_invoice", kwargs={"invoice_id": inv.pk}), fetch_redirect_response=False)
        self.assertEqual(str(inv.amount), "500.00")
        co = Consultation.objects.get()
        url = reverse("portal_consultation_status", kwargs={"consultation_id": co.pk})
        login(self.partner).post(url, {"status": "Confirmed"})
        co.refresh_from_db()
        self.assertEqual(co.status, "Requested")
        inv.status = "Paid"
        inv.save()
        login(self.partner).post(url, {"status": "Confirmed"})
        co.refresh_from_db()
        self.assertEqual(co.status, "Confirmed")


class DashboardPaymentTests(BillingBase):
    def test_client_dashboard_lists_standalone_and_case_invoices_with_pay_link(self):
        standalone = services.create_invoice(client=self.client1, kind="service", amount="999", description="Trademark")
        r = login(self.client1).get(reverse("portal_dashboard"))
        self.assertContains(r, standalone.invoice_no)
        self.assertContains(r, self.invoice.invoice_no)
        self.assertContains(r, reverse("billing_invoice", kwargs={"invoice_id": standalone.pk}))

    def test_other_clients_invoices_not_listed(self):
        other = services.create_invoice(client=self.client2, kind="service", amount="999", description="X")
        self.assertNotContains(login(self.client1).get(reverse("portal_dashboard")), other.invoice_no)


class RaiseInvoiceTests(BillingBase):
    def setUp(self):
        super().setUp()
        self.staff = mk_user("s@t.test", "staff")
        self.case.staff.add(self.staff)
        self.other_staff = mk_user("s2@t.test", "staff")
        self.url = reverse("portal_invoice_create", kwargs={"case_id": self.case.pk})

    def raise_(self, user, **over):
        data = {"description": "Stage 2 fee", "amount": "2500", "due_date": "2099-01-01"}
        data.update(over)
        return login(user).post(self.url, data)

    def test_staff_and_partner_can_raise_for_client(self):
        for user in (self.staff, self.partner):
            self.raise_(user)
        invs = Invoice.objects.filter(description="Stage 2 fee")
        self.assertEqual(invs.count(), 2)
        inv = invs.first()
        self.assertEqual((inv.client, inv.case, str(inv.amount), inv.status), (self.client1, self.case, "2500.00", "Pending"))
        self.assertTrue(CaseUpdate.objects.filter(case=self.case, body__contains=inv.invoice_no).exists())
        self.assertTrue(AuditLog.objects.filter(action="invoice_created").exists())

    def test_unassigned_staff_client_and_ceo_blocked(self):
        self.assertEqual(self.raise_(self.other_staff).status_code, 404)
        self.assertEqual(self.raise_(self.client1).status_code, 403)
        self.assertEqual(self.raise_(self.ceo).status_code, 403)
        self.assertFalse(Invoice.objects.filter(description="Stage 2 fee").exists())

    def test_invalid_amounts_rejected(self):
        for bad in ("0", "-5", "abc", "1000001", ""):
            self.raise_(self.staff, amount=bad)
        self.raise_(self.staff, due_date="31-12-2099")
        self.raise_(self.staff, description="")
        self.assertFalse(Invoice.objects.filter(description="Stage 2 fee").exists())

    def test_client_then_sees_it_to_pay(self):
        self.raise_(self.staff)
        inv = Invoice.objects.get(description="Stage 2 fee")
        self.assertContains(login(self.client1).get(reverse("portal_dashboard")), inv.invoice_no)

    def test_dashboards_render_with_form(self):
        self.assertContains(login(self.staff).get(reverse("portal_dashboard")), "Raise invoice")
        self.assertContains(login(self.partner).get(reverse("portal_dashboard")), "Raise invoice")
