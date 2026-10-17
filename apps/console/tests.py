from django.conf import settings
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import PolicyAcceptance, User
from apps.audit.models import AuditLog
from apps.billing.models import Offering
from apps.leads.models import Enquiry
from apps.portal.models import Case

PW = "correct-horse-battery-9"


def mk(email, role, **extra):
    u = User.objects.create_user(email=email, password=PW, name=email.split("@")[0], role=role, **extra)
    PolicyAcceptance.objects.create(user=u, version=settings.POLICY_VERSION)
    return u


def login(u):
    c = Client()
    c.force_login(u)
    return c


class ConsoleBase(TestCase):
    def setUp(self):
        self.ceo = mk("ceo@t.test", "ceo")
        self.client_u = mk("c@t.test", "client")
        self.partner = mk("p@t.test", "partner")
        self.staff = mk("s@t.test", "staff")


class AccessTests(ConsoleBase):
    URLS = ["console", "console_users", "console_user_create", "console_cases", "console_case_create",
            "console_leads", "console_billing", "console_offering_create", "console_audit"]

    def test_admin_path_is_console_and_django_admin_moved(self):
        self.assertEqual(reverse("console"), "/admin/")
        self.assertEqual(reverse("admin:index"), "/sd/")

    def test_ceo_can_open_every_page(self):
        c = login(self.ceo)
        for name in self.URLS:
            self.assertEqual(c.get(reverse(name)).status_code, 200, name)

    def test_everyone_else_forbidden_and_anonymous_redirected_to_login_with_next(self):
        for user in (self.client_u, self.partner, self.staff):
            c = login(user)
            for name in self.URLS:
                self.assertEqual(c.get(reverse(name)).status_code, 403, f"{user.role} {name}")
        r = Client().get(reverse("console"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("next=%2Fadmin%2F", r["Location"])

    def test_post_actions_blocked_for_non_ceo(self):
        lead = Enquiry.objects.create(name="A", phone="9876543210")
        r = login(self.staff).post(reverse("console_lead_status", kwargs={"enquiry_id": lead.pk}), {"status": "closed"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(login(self.client_u).post(reverse("console_user_create"), {"name": "x", "email": "x@t.test", "role": "ceo"}).status_code, 403)
        self.assertFalse(User.objects.filter(email="x@t.test").exists())

    def test_csrf_enforced(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.ceo)
        self.assertEqual(c.post(reverse("console_user_create"), {}).status_code, 403)

    def test_django_admin_requires_its_own_login(self):
        r = login(self.ceo).get("/sd/", follow=False)
        self.assertEqual(r.status_code, 302)  # CEO without is_staff goes to admin login
        self.assertIn("/sd/login/", r["Location"])


class UserManagementTests(ConsoleBase):
    def test_create_user_sends_set_password_email_and_no_password(self):
        r = login(self.ceo).post(reverse("console_user_create"), {"name": "New Partner", "email": "New@T.test", "role": "partner"})
        self.assertRedirects(r, reverse("console_users"), fetch_redirect_response=False)
        user = User.objects.get(email="new@t.test")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.role, "partner")
        self.assertIn("/portal/reset/", mail.outbox[0].body)
        self.assertTrue(AuditLog.objects.filter(action="console_user_created").exists())

    def test_duplicate_and_invalid_role_rejected(self):
        c = login(self.ceo)
        c.post(reverse("console_user_create"), {"name": "D", "email": "C@t.test", "role": "client"})
        c.post(reverse("console_user_create"), {"name": "D", "email": "d@t.test", "role": "superman"})
        self.assertEqual(User.objects.filter(email__iexact="c@t.test").count(), 1)
        self.assertFalse(User.objects.filter(email="d@t.test").exists())

    def test_cannot_demote_or_deactivate_self_or_last_ceo(self):
        c = login(self.ceo)
        url = reverse("console_user_edit", kwargs={"user_id": self.ceo.pk})
        c.post(url, {"name": "CEO", "role": "staff", "is_active": "on"})
        c.post(url, {"name": "CEO", "role": "ceo"})
        self.ceo.refresh_from_db()
        self.assertEqual((self.ceo.role, self.ceo.is_active), ("ceo", True))

    def test_edit_and_deactivate_other_user(self):
        login(self.ceo).post(reverse("console_user_edit", kwargs={"user_id": self.staff.pk}), {"name": "Renamed", "role": "staff"})
        self.staff.refresh_from_db()
        self.assertEqual((self.staff.name, self.staff.is_active), ("Renamed", False))

    def test_reset_link_for_user(self):
        login(self.ceo).post(reverse("console_user_reset", kwargs={"user_id": self.client_u.pk}))
        self.assertEqual(len(mail.outbox), 1)

    def test_list_filters(self):
        r = login(self.ceo).get(reverse("console_users"), {"role": "partner"})
        self.assertContains(r, "p@t.test")
        self.assertNotContains(r, "s@t.test")


class CaseManagementTests(ConsoleBase):
    def payload(self, **over):
        data = {"title": "New matter", "status": "In Progress", "client": self.client_u.pk, "partner": self.partner.pk,
                "staff": [self.staff.pk], "case_no": "", "hearing_date": "", "billing_note": ""}
        data.update(over)
        return data

    def test_create_autonumbers_and_assigns_staff(self):
        login(self.ceo).post(reverse("console_case_create"), self.payload())
        case = Case.objects.get()
        self.assertRegex(case.case_no, r"^VL-\d{4}-\d{4}$")
        self.assertEqual(list(case.staff.all()), [self.staff])
        # the assigned staff member can now see it in the portal
        self.assertContains(login(self.staff).get(reverse("portal_dashboard")), case.case_no)

    def test_roles_are_enforced_on_assignment(self):
        c = login(self.ceo)
        c.post(reverse("console_case_create"), self.payload(client=self.staff.pk))
        c.post(reverse("console_case_create"), self.payload(partner=self.client_u.pk))
        c.post(reverse("console_case_create"), self.payload(staff=[self.partner.pk]))
        self.assertFalse(Case.objects.exists())

    def test_duplicate_case_number_rejected_and_edit_works(self):
        c = login(self.ceo)
        c.post(reverse("console_case_create"), self.payload(case_no="X-1"))
        c.post(reverse("console_case_create"), self.payload(case_no="x-1"))
        self.assertEqual(Case.objects.count(), 1)
        case = Case.objects.get()
        c.post(reverse("console_case_edit", kwargs={"case_id": case.pk}), self.payload(case_no="X-1", status="Completed", title="Renamed"))
        case.refresh_from_db()
        self.assertEqual((case.status, case.title), ("Completed", "Renamed"))

    def test_search(self):
        Case.objects.create(case_no="Z-9", title="Findable", client=self.client_u, partner=self.partner)
        self.assertContains(login(self.ceo).get(reverse("console_cases"), {"q": "findable"}), "Z-9")
        self.assertNotContains(login(self.ceo).get(reverse("console_cases"), {"q": "nomatch"}), "Z-9")


class LeadsBillingTests(ConsoleBase):
    def test_lead_status_update_and_validation(self):
        lead = Enquiry.objects.create(name="Lead", phone="9876543210")
        c = login(self.ceo)
        url = reverse("console_lead_status", kwargs={"enquiry_id": lead.pk})
        self.assertEqual(c.post(url, {"status": "bogus"}).status_code, 400)
        c.post(url, {"status": "converted"})
        lead.refresh_from_db()
        self.assertEqual(lead.status, "converted")

    def test_offering_crud_and_toggle_reflect_on_pricing_page(self):
        c = login(self.ceo)
        c.post(reverse("console_offering_create"), {"name": "Trademark", "slug": "trademark", "kind": "service", "amount": "7500", "description": "", "active": "on"})
        offering = Offering.objects.get()
        self.assertContains(self.client.get(reverse("pricing")), "₹7,500")
        c.post(reverse("console_offering_toggle", kwargs={"offering_id": offering.pk}))
        offering.refresh_from_db()
        self.assertFalse(offering.active)
        self.assertNotContains(self.client.get(reverse("pricing")), "Pay online")

    def test_offering_amount_must_be_positive(self):
        login(self.ceo).post(reverse("console_offering_create"), {"name": "Bad", "slug": "bad", "kind": "service", "amount": "-5", "description": ""})
        self.assertFalse(Offering.objects.exists())

    def test_audit_and_billing_pages_render_data(self):
        self.assertContains(login(self.ceo).get(reverse("console_audit")), "Audit log")
        self.assertContains(login(self.ceo).get(reverse("console")), "Console")


class QuickActionTests(ConsoleBase):
    def test_role_change_and_toggle_from_list(self):
        c = login(self.ceo)
        url = reverse("console_user_quick", kwargs={"user_id": self.staff.pk})
        c.post(url, {"role": "partner"})
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.role, "partner")
        c.post(url, {"is_active": "0"})
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)
        self.assertEqual(c.post(url, {"role": "emperor"}).status_code, 400)

    def test_quick_guards_self_and_last_ceo_and_permissions(self):
        c = login(self.ceo)
        url = reverse("console_user_quick", kwargs={"user_id": self.ceo.pk})
        c.post(url, {"role": "staff"})
        c.post(url, {"is_active": "0"})
        self.ceo.refresh_from_db()
        self.assertEqual((self.ceo.role, self.ceo.is_active), ("ceo", True))
        self.assertEqual(login(self.staff).post(reverse("console_user_quick", kwargs={"user_id": self.client_u.pk}), {"role": "ceo"}).status_code, 403)
        self.client_u.refresh_from_db()
        self.assertEqual(self.client_u.role, "client")

    def test_back_param_is_restricted_to_console(self):
        r = login(self.ceo).post(reverse("console_user_quick", kwargs={"user_id": self.staff.pk}), {"role": "staff", "back": "https://evil.example/"})
        self.assertEqual(r["Location"], reverse("console_users"))
        r = login(self.ceo).post(reverse("console_user_quick", kwargs={"user_id": self.staff.pk}), {"role": "staff", "back": "/admin/users/?role=staff"})
        self.assertEqual(r["Location"], "/admin/users/?role=staff")

    def test_case_status_quick_change(self):
        case = Case.objects.create(case_no="Q-1", title="Q", client=self.client_u, partner=self.partner)
        c = login(self.ceo)
        url = reverse("console_case_status", kwargs={"case_id": case.pk})
        c.post(url, {"status": "Completed"})
        case.refresh_from_db()
        self.assertEqual(case.status, "Completed")
        self.assertEqual(c.post(url, {"status": "nope"}).status_code, 400)
        self.assertEqual(login(self.partner).post(url, {"status": "On Hold"}).status_code, 403)

    def test_pages_have_compact_markup(self):
        html = login(self.ceo).get(reverse("console")).content.decode()
        self.assertIn("db-panel", html)
        self.assertIn("Needs attention", html)
