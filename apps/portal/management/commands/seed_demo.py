"""Create demo users/cases for local development. Refuses to run with DEBUG off."""
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import Invoice
from apps.leads.models import Enquiry
from apps.portal.models import (
    Case,
    CaseMessage,
    CaseUpdate,
    ComplianceAlert,
    DocRequest,
    Draft,
    Milestone,
)


class Command(BaseCommand):
    help = "Seed demo data (development only). Passwords are random and printed once."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DEBUG=True")
        if User.objects.filter(email="client@demo.local").exists():
            self.stdout.write("Demo data already present.")
            return
        password = secrets.token_urlsafe(12)
        mk = lambda email, name, role: User.objects.create_user(email=email, password=password, name=name, role=role)
        client = mk("client@demo.local", "Demo Client", "client")
        other = mk("client2@demo.local", "Other Client", "client")
        partner = mk("partner@demo.local", "Adv. Vikram Malhotra", "partner")
        staff = mk("staff@demo.local", "Office Staff — Priya", "staff")
        mk("ceo@demo.local", "Founder / CEO", "ceo")
        User.objects.create_superuser(email="admin@demo.local", password=password, name="Site Admin")

        today = timezone.localdate()
        c1 = Case.objects.create(case_no="VL-2026-0142", title="Pvt Ltd Incorporation — TechStart", client=client, partner=partner, hearing_date=today + timedelta(days=7), billing_note="Professional fee ₹7,999")
        c2 = Case.objects.create(case_no="VL-2026-0188", title="Trademark Class 9 — Brand Protection", status="Awaiting Client", client=client, partner=partner, billing_note="Professional fee ₹12,500")
        Case.objects.create(case_no="VL-2026-0999", title="GST Registration — OtherCo", client=other, partner=partner)
        c1.staff.add(staff)
        c2.staff.add(staff)

        for case, steps in (
            (c1, [("Name approval", "done"), ("Documents collected", "done"), ("MCA filing", "in_progress"), ("Certificate & CIN delivery", "pending")]),
            (c2, [("Brand search", "done"), ("TM application draft", "pending"), ("Filing", "pending")]),
        ):
            for order, (title, status) in enumerate(steps, 1):
                Milestone.objects.create(case=case, title=title, sort_order=order, status=status)
        DocRequest.objects.create(case=c1, title="PAN of directors", status="verified", sort_order=1)
        DocRequest.objects.create(case=c1, title="Address proof", status="needed", sort_order=2)
        DocRequest.objects.create(case=c2, title="Logo file", status="needed", sort_order=1)
        CaseUpdate.objects.create(case=c2, author=partner, body="Awaiting logo file and user affidavit from client.")
        CaseMessage.objects.create(case=c1, author=client, body="Any update on the MCA filing?")
        Draft.objects.create(case=c2, title="TM application draft", submitted_by=staff)
        ComplianceAlert.objects.create(case=c1, title="DIR-3 KYC", category="MCA", due_date=today + timedelta(days=20), status="action_needed")
        Invoice.objects.create(invoice_no="INV-0142-1", client=client, case=c1, amount="7999", status="Paid")
        Invoice.objects.create(invoice_no="INV-0188-1", client=client, case=c2, amount="12500", due_date=today + timedelta(days=10))
        for source, name, phone, service, status in (
            ("contact", "Rahul Verma", "9876543210", "Pvt Ltd Registration", "new"),
            ("trademark", "Meera Iyer", "9090909090", "Trademark", "converted"),
        ):
            Enquiry.objects.create(source_page=source, name=name, phone=phone, service=service, status=status)
        self.stdout.write(self.style.SUCCESS(f"Seeded. Logins: client/partner/staff/ceo/admin@demo.local — password: {password} (admin = /admin/)"))
