import shutil
from pathlib import Path
import tempfile

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import PolicyAcceptance, User
from apps.audit.models import AuditLog
from apps.billing.models import Invoice

from .models import Case, CaseMessage, Document, DocRequest, Draft, Milestone

PDF = b"%PDF-1.4\n%fake pdf body\n"
PASSWORD = "correct-horse-battery-9"
TMP_MEDIA = str(Path(tempfile.mkdtemp()).resolve())


def make_user(email, role, name=None):
    user = User.objects.create_user(email=email, password=PASSWORD, name=name or email.split("@")[0], role=role)
    PolicyAcceptance.objects.create(user=user, version=settings.POLICY_VERSION)
    return user


def login(user):
    client = Client()
    client.force_login(user)
    return client


@override_settings(PRIVATE_MEDIA_ROOT=TMP_MEDIA)
class PortalBase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.client1 = make_user("c1@t.test", "client")
        self.client2 = make_user("c2@t.test", "client")
        self.partner = make_user("p@t.test", "partner")
        self.partner2 = make_user("p2@t.test", "partner")
        self.staff = make_user("s@t.test", "staff")
        self.staff2 = make_user("s2@t.test", "staff")
        self.ceo = make_user("ceo@t.test", "ceo")
        self.case1 = Case.objects.create(case_no="T-1", title="Case 1", client=self.client1, partner=self.partner)
        self.case1.staff.add(self.staff)
        self.case2 = Case.objects.create(case_no="T-2", title="Case 2", client=self.client2, partner=self.partner2)
        self.case2.staff.add(self.staff2)
        self.milestone = Milestone.objects.create(case=self.case1, title="Step", sort_order=1)
        self.milestone2 = Milestone.objects.create(case=self.case2, title="Step", sort_order=1)
        self.draft = Draft.objects.create(case=self.case1, title="Draft", submitted_by=self.staff)
        self.draft2 = Draft.objects.create(case=self.case2, title="Draft", submitted_by=self.staff2)
        self.docreq = DocRequest.objects.create(case=self.case2, title="PAN", sort_order=1)
        self.inv = Invoice.objects.create(invoice_no="I-1", client=self.client1, case=self.case1, amount="100")

    def upload(self, client, case, name="a.pdf", data=PDF):
        return client.post(
            reverse("portal_documents_upload"),
            {"case_id": case.pk, "file": SimpleUploadedFile(name, data)},
        )


class LoginTests(PortalBase):
    def post_login(self, email, password=PASSWORD, policy="1", role=""):
        data = {"action": "login", "email": email, "password": password, "role": role}
        if policy:
            data["policy"] = policy
        return Client().post(reverse("portal"), data)

    def test_valid_login_records_policy_and_audit(self):
        user = User.objects.create_user(email="new@t.test", password=PASSWORD, name="New")
        r = self.post_login("new@t.test")
        self.assertRedirects(r, reverse("portal_dashboard"), fetch_redirect_response=False)
        self.assertTrue(PolicyAcceptance.objects.filter(user=user, version=settings.POLICY_VERSION).exists())
        self.assertTrue(AuditLog.objects.filter(action="login", user=user).exists())

    def test_policy_required(self):
        r = self.post_login("c1@t.test", policy="")
        self.assertRedirects(r, reverse("portal"), fetch_redirect_response=False)
        self.assertFalse(AuditLog.objects.filter(action="login").exists())

    def test_wrong_password_and_unknown_user_same_outcome(self):
        for email in ("c1@t.test", "nobody@t.test"):
            r = self.post_login(email, password="wrong-password-1")
            self.assertRedirects(r, reverse("portal"), fetch_redirect_response=False)
        self.assertEqual(AuditLog.objects.filter(action="login_failed").count(), 2)

    def test_role_is_detected_automatically_for_every_role(self):
        for email, label in (("c1@t.test", "Client"), ("p@t.test", "Partner"), ("s@t.test", "Office staff"), ("ceo@t.test", "Founder")):
            c = Client()
            r = c.post(reverse("portal"), {"action": "login", "email": email, "password": PASSWORD, "policy": "1"}, follow=True)
            self.assertEqual(r.redirect_chain[-1][0], reverse("portal_dashboard"), email)
            self.assertContains(r, label)  # welcome toast names the detected role

    def test_a_posted_role_field_is_ignored(self):
        c = Client()
        c.post(reverse("portal"), {"action": "login", "email": "c1@t.test", "password": PASSWORD, "policy": "1", "role": "ceo"})
        self.assertEqual(c.get(reverse("console")).status_code, 403)  # still just a client

    def test_login_page_has_no_role_tabs_and_signup_is_client_only(self):
        html = Client().get(reverse("portal")).content.decode()
        for word in ("Partner</button>", "Staff</button>", "CEO</button>"):
            self.assertNotIn(word, html)
        self.assertIn("Create client account", html)
        self.assertNotIn("created by the VinnitaLegal office", html)  # copy removed on request

    def test_lockout_after_repeated_failures(self):
        for _ in range(5):
            self.post_login("c1@t.test", password="wrong-password-1")
        r = self.post_login("c1@t.test", password=PASSWORD)  # correct password, still locked
        self.assertRedirects(r, reverse("portal"), fetch_redirect_response=False)
        self.assertFalse(AuditLog.objects.filter(action="login", user=self.client1).exists())

    def test_signup_creates_client_and_rejects_weak_password(self):
        base = {"action": "signup", "name": "Zed", "email": "zed@t.test", "policy": "1"}
        Client().post(reverse("portal"), {**base, "password": "short", "confirm_password": "short"})
        self.assertFalse(User.objects.filter(email="zed@t.test").exists())
        Client().post(reverse("portal"), {**base, "password": PASSWORD, "confirm_password": PASSWORD})
        self.assertEqual(User.objects.get(email="zed@t.test").role, "client")

    def test_signup_cannot_choose_role(self):
        Client().post(reverse("portal"), {"action": "signup", "name": "Z", "email": "z@t.test", "policy": "1",
                                          "password": PASSWORD, "confirm_password": PASSWORD, "role": "ceo"})
        self.assertEqual(User.objects.get(email="z@t.test").role, "client")

    def test_logout_requires_post_and_csrf(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.client1)
        self.assertEqual(c.post(reverse("portal_logout")).status_code, 403)
        self.assertEqual(Client().get(reverse("portal_logout")).status_code, 405)

    def test_policy_version_bump_forces_relogin(self):
        c = login(self.client1)
        with override_settings(POLICY_VERSION="2099-01"):
            r = c.get(reverse("portal_dashboard"))
        self.assertRedirects(r, reverse("portal"), fetch_redirect_response=False)


class PasswordResetTests(PortalBase):
    def test_reset_flow_and_single_use(self):
        Client().post(reverse("portal"), {"action": "forgot_request", "email": "c1@t.test"})
        self.assertEqual(len(mail.outbox), 1)
        link = next(w for w in mail.outbox[0].body.split() if "/portal/reset/" in w)
        path = "/" + link.split("/", 3)[3]
        c = Client()
        self.assertEqual(c.get(path).status_code, 200)
        new = "a-brand-new-pass-77"
        c.post(path, {"password": new, "confirm_password": new})
        self.client1.refresh_from_db()
        self.assertTrue(self.client1.check_password(new))
        self.assertEqual(Client().get(path).status_code, 302)  # token now invalid

    def test_unknown_email_sends_nothing_and_shows_same_message(self):
        r = Client().post(reverse("portal"), {"action": "forgot_request", "email": "ghost@t.test"}, follow=True)
        self.assertEqual(len(mail.outbox), 0)
        self.assertContains(r, "If an account exists")

    def test_no_code_or_token_leaked_in_page(self):
        r = Client().post(reverse("portal"), {"action": "forgot_request", "email": "c1@t.test"}, follow=True)
        token = mail.outbox[0].body.split("/")[-1].split()[0]
        self.assertNotContains(r, token)
        self.assertNotContains(r, "Demo code")


class DashboardTests(PortalBase):
    def test_each_role_dashboard_renders(self):
        for user in (self.client1, self.partner, self.staff, self.ceo):
            r = login(user).get(reverse("portal_dashboard"))
            self.assertEqual(r.status_code, 200, user.role)

    def test_anonymous_redirected(self):
        self.assertEqual(Client().get(reverse("portal_dashboard")).status_code, 302)

    def test_client_sees_only_own_cases(self):
        r = login(self.client1).get(reverse("portal_dashboard"))
        self.assertContains(r, "T-1")
        self.assertNotContains(r, "T-2")

    def test_partner_and_staff_scoped(self):
        self.assertNotContains(login(self.partner).get(reverse("portal_dashboard")), "T-2")
        self.assertNotContains(login(self.staff).get(reverse("portal_dashboard")), "T-2")

    def test_ceo_sees_all_cases(self):
        r = login(self.ceo).get(reverse("portal_dashboard"))
        self.assertContains(r, "T-1")
        self.assertContains(r, "T-2")


class AuthorizationTests(PortalBase):
    def test_role_gates_return_403(self):
        cases = [
            (self.client1, "portal_case_status", {"case_id": self.case1.pk}),
            (self.client1, "portal_comms", {}),
            (self.client1, "portal_breach", {}),
            (self.partner, "portal_queries", {}),
            (self.partner, "portal_comms", {}),
            (self.staff, "portal_conflicts", {}),
            (self.staff, "portal_draft_approve", {"draft_id": self.draft.pk}),
            (self.ceo, "portal_case_update", {"case_id": self.case1.pk}),
        ]
        for user, name, kwargs in cases:
            r = login(user).post(reverse(name, kwargs=kwargs), {"body": "x", "status": "Completed"})
            self.assertEqual(r.status_code, 403, f"{user.role} {name}")

    def test_idor_on_case_scoped_actions_returns_404(self):
        c = login(self.client1)
        self.assertEqual(c.post(reverse("portal_queries"), {"case_id": self.case2.pk, "body": "hi"}).status_code, 404)
        self.assertFalse(CaseMessage.objects.filter(case=self.case2).exists())
        self.assertEqual(self.upload(c, self.case2).status_code, 404)
        self.assertFalse(Document.objects.exists())

    def test_partner_cannot_touch_other_partners_objects(self):
        c = login(self.partner)
        self.assertEqual(c.post(reverse("portal_case_status", kwargs={"case_id": self.case2.pk}), {"status": "Completed"}).status_code, 404)
        self.assertEqual(c.post(reverse("portal_milestone_update", kwargs={"milestone_id": self.milestone2.pk}), {"status": "done"}).status_code, 404)
        self.assertEqual(c.post(reverse("portal_draft_approve", kwargs={"draft_id": self.draft2.pk})).status_code, 404)
        self.assertEqual(c.post(reverse("portal_document_request_status", kwargs={"request_id": self.docreq.pk}), {"status": "verified"}).status_code, 404)
        self.draft2.refresh_from_db()
        self.assertEqual(self.draft2.status, "pending")

    def test_unassigned_staff_blocked(self):
        c = login(self.staff)
        self.assertEqual(c.post(reverse("portal_case_update", kwargs={"case_id": self.case2.pk}), {"body": "x"}).status_code, 404)
        self.assertEqual(c.post(reverse("portal_partner_message"), {"case_id": self.case2.pk, "body": "x"}).status_code, 404)
        self.assertEqual(c.post(reverse("portal_comms"), {"case_id": self.case2.pk, "note": "x"}).status_code, 404)

    def test_partner_case_status_validated(self):
        c = login(self.partner)
        c.post(reverse("portal_case_status", kwargs={"case_id": self.case1.pk}), {"status": "<script>"})
        self.case1.refresh_from_db()
        self.assertEqual(self.case1.status, "In Progress")
        c.post(reverse("portal_case_status", kwargs={"case_id": self.case1.pk}), {"status": "Completed"})
        self.case1.refresh_from_db()
        self.assertEqual(self.case1.status, "Completed")

    def test_draft_cannot_be_reviewed_twice(self):
        c = login(self.partner)
        c.post(reverse("portal_draft_approve", kwargs={"draft_id": self.draft.pk}))
        c.post(reverse("portal_draft_reject", kwargs={"draft_id": self.draft.pk}))
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, "approved")

    def test_no_staff_mark_paid_endpoint(self):
        from django.urls import NoReverseMatch

        with self.assertRaises(NoReverseMatch):
            reverse("portal_invoice_payment", kwargs={"invoice_id": self.inv.pk})
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.status, "Pending")


class DocumentTests(PortalBase):
    def test_upload_stores_privately_and_download_is_scoped(self):
        c1 = login(self.client1)
        self.upload(c1, self.case1)
        doc = Document.objects.get()
        self.assertTrue(doc.file.path.startswith(TMP_MEDIA))
        self.assertNotEqual(Path(doc.file.name).name, "a.pdf")  # random stored name
        url = reverse("portal_document_download", kwargs={"doc_id": doc.pk})
        r = c1.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertEqual(b"".join(r.streaming_content), PDF)
        self.assertEqual(login(self.client2).get(url).status_code, 404)
        self.assertEqual(login(self.staff2).get(url).status_code, 404)
        self.assertEqual(login(self.partner).get(url).status_code, 200)
        self.assertEqual(Client().get(url).status_code, 302)

    def test_upload_rejects_bad_extension_magic_and_size(self):
        c = login(self.client1)
        self.upload(c, self.case1, name="evil.exe", data=PDF)
        self.upload(c, self.case1, name="fake.pdf", data=b"MZ not a pdf")
        self.upload(c, self.case1, name="big.pdf", data=PDF + b"0" * (settings.MAX_UPLOAD_BYTES + 1))
        self.assertFalse(Document.objects.exists())

    def test_path_traversal_filename_neutralised(self):
        self.upload(login(self.client1), self.case1, name="../../etc/passwd.pdf")
        doc = Document.objects.get()
        self.assertEqual(doc.filename, "passwd.pdf")
        self.assertTrue(doc.file.path.startswith(TMP_MEDIA))

    def test_client_upload_marks_request_uploaded(self):
        DocRequest.objects.create(case=self.case1, title="Aadhaar", sort_order=1)
        self.upload(login(self.client1), self.case1)
        self.assertEqual(DocRequest.objects.get(case=self.case1).status, "uploaded")


class ConsultationTests(PortalBase):
    def test_booking_validates_date_and_mode(self):
        c = login(self.client1)
        url = reverse("portal_consultation_book")
        c.post(url, {"practice_area": "Contracts", "preferred_date": "2000-01-01", "preferred_time": "10:00", "mode": "Video"})
        c.post(url, {"practice_area": "Contracts", "preferred_date": "2099-01-01", "preferred_time": "10:00", "mode": "Teleport"})
        self.assertEqual(self.client1.consultations.count(), 0)
        c.post(url, {"practice_area": "Contracts", "preferred_date": "2099-01-01", "preferred_time": "10:00", "mode": "Video"})
        self.assertEqual(self.client1.consultations.count(), 1)

    def test_cannot_book_against_other_clients_case(self):
        r = login(self.client1).post(reverse("portal_consultation_book"), {
            "case_id": self.case2.pk, "practice_area": "X", "preferred_date": "2099-01-01", "preferred_time": "10:00"})
        self.assertEqual(r.status_code, 404)


class CommsLogTests(PortalBase):
    def test_staff_can_log_and_see_comms_in_dashboard(self):
        c = login(self.staff)
        r = c.post(reverse("portal_comms"), {"case_id": self.case1.pk, "type": "WhatsApp", "note": "Client confirmed docs"})
        self.assertEqual(r.status_code, 302)
        page = c.get(reverse("portal_dashboard"))
        self.assertContains(page, "Client confirmed docs")
        self.assertContains(page, "Log a call")

    def test_comms_form_present_for_each_case(self):
        self.assertContains(login(self.staff).get(reverse("portal_dashboard")), reverse("portal_comms"))


class DashboardUxTests(PortalBase):
    def test_partner_can_add_milestone_only_on_own_case(self):
        url = reverse("portal_milestone_add", kwargs={"case_id": self.case1.pk})
        r = login(self.partner).post(url, {"title": "Name approval"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Milestone.objects.filter(case=self.case1, title="Name approval").exists())
        self.assertEqual(Milestone.objects.filter(case=self.case1).order_by("-sort_order").first().sort_order, 2)
        self.assertEqual(login(self.partner2).post(url, {"title": "x"}).status_code, 404)
        self.assertEqual(login(self.client1).post(url, {"title": "x"}).status_code, 403)
        self.assertEqual(login(self.staff).post(url, {"title": "x"}).status_code, 403)
        login(self.partner).post(url, {"title": "   "})
        self.assertEqual(Milestone.objects.filter(case=self.case1).count(), 2)  # blank rejected

    def test_client_upload_marks_the_chosen_request_not_just_the_first(self):
        first = DocRequest.objects.create(case=self.case1, title="First", sort_order=1)
        second = DocRequest.objects.create(case=self.case1, title="Second", sort_order=2)
        c = login(self.client1)
        c.post(reverse("portal_documents_upload"), {"case_id": self.case1.pk, "request_id": second.pk, "file": SimpleUploadedFile("a.pdf", PDF)})
        first.refresh_from_db(); second.refresh_from_db()
        self.assertEqual((first.status, second.status), ("needed", "uploaded"))

    def test_client_cannot_mark_other_cases_request_via_request_id(self):
        foreign = DocRequest.objects.create(case=self.case2, title="Foreign", sort_order=9)
        login(self.client1).post(reverse("portal_documents_upload"), {"case_id": self.case1.pk, "request_id": foreign.pk, "file": SimpleUploadedFile("a.pdf", PDF)})
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, "needed")

    def test_unanswered_count_resets_after_reply(self):
        CaseMessage.objects.create(case=self.case1, author=self.client1, body="q1")
        CaseMessage.objects.create(case=self.case1, author=self.client1, body="q2")
        from .rows import build_partner_jobs

        self.assertEqual(build_partner_jobs(self.partner)[0]["pending_replies"], 2)
        CaseMessage.objects.create(case=self.case1, author=self.partner, body="answer")
        self.assertEqual(build_partner_jobs(self.partner)[0]["pending_replies"], 0)

    def test_fetch_actions_return_204_without_flash(self):
        from apps.leads.models import Enquiry

        lead = Enquiry.objects.create(name="L", phone="9876543210")
        c = login(self.staff)
        r = c.post(reverse("portal_enquiry_status", kwargs={"enquiry_id": lead.pk}), {"status": "converted"}, HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(r.status_code, 204)
        r = c.post(reverse("portal_enquiry_whatsapp", kwargs={"enquiry_id": lead.pk}), HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(r.status_code, 204)
        lead.refresh_from_db()
        self.assertEqual(lead.status, "whatsapp_sent")
        self.assertEqual(lead.outreach.count(), 1)
        self.assertNotContains(c.get(reverse("portal_dashboard")), "WhatsApp outreach logged")
        # invalid status is still rejected, fetch or not
        self.assertEqual(c.post(reverse("portal_enquiry_status", kwargs={"enquiry_id": lead.pk}), {"status": "x"}, HTTP_X_REQUESTED_WITH="fetch").status_code, 400)

    def test_dashboards_put_urgent_case_first(self):
        DocRequest.objects.create(case=self.case1, title="Need", sort_order=1)
        CaseMessage.objects.create(case=self.case1, author=self.client1, body="hello")
        newer = Case.objects.create(case_no="T-3", title="Newer idle", client=self.client1, partner=self.partner)
        newer.staff.add(self.staff)
        for user in (self.client1, self.partner, self.staff):
            html = login(user).get(reverse("portal_dashboard")).content.decode()
            self.assertLess(html.index("T-1"), html.index("T-3"), user.role)

    def test_draft_review_returns_to_the_case(self):
        r = login(self.partner).post(reverse("portal_draft_approve", kwargs={"draft_id": self.draft.pk}), {"redirect_case": self.case1.pk})
        self.assertIn(f"case={self.case1.pk}", r["Location"])

    def test_all_role_dashboards_show_core_sections_without_tabs(self):
        checks = {self.client1: ("Messages with your legal team", "Billing", "Documents"),
                  self.partner: ("Execution checklist", "Client conversation", "Share an update"),
                  self.staff: ("Log a call", "Client conversation", "Invoices")}
        for user, needles in checks.items():
            html = login(user).get(reverse("portal_dashboard")).content.decode()
            for needle in needles:
                self.assertIn(needle, html, f"{user.role}: {needle}")


class UploadStreamingLimitTests(PortalBase):
    def test_oversize_upload_is_cut_off_while_streaming(self):
        from unittest import mock

        from .uploads import SizeLimitUploadHandler

        with override_settings(MAX_UPLOAD_BYTES=50_000):
            handler = SizeLimitUploadHandler(mock.Mock())
            handler.receive_data_chunk(b"x" * 30_000, 0)
            from django.core.files.uploadhandler import StopUpload

            with self.assertRaises(StopUpload):
                handler.receive_data_chunk(b"x" * 30_000, 30_000)

    def test_normal_upload_still_works_through_the_handler_chain(self):
        c = login(self.client1)
        self.upload(c, self.case1)
        self.assertTrue(Document.objects.filter(case=self.case1).exists())
