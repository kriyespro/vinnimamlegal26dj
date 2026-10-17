"""Create fixed-price offerings from the fees currently printed on the pricing page.

Idempotent. Offerings are created ACTIVE only when DEBUG is on; in production they are
created inactive so the owner reviews amounts in /admin/ before enabling online payment.
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.billing.models import Offering

OFFERINGS = [
    ("pvt-ltd", "Private Limited Company registration — professional fee", 6999),
    ("llp", "LLP registration — professional fee", 5499),
    ("trademark", "Trademark registration — professional fee", 6999),
    ("msme", "MSME / Udyam registration — professional fee", 999),
    ("partnership", "Partnership firm — professional fee", 2999),
    ("marriage-certificate", "Marriage certificate assistance — professional fee", 4999),
]


class Command(BaseCommand):
    help = "Seed pricing-page offerings (government / stamp fees are NOT included)."

    def handle(self, *args, **options):
        created = 0
        for slug, name, amount in OFFERINGS:
            _, was_created = Offering.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "amount": amount, "active": settings.DEBUG, "kind": Offering.Kind.SERVICE},
            )
            created += was_created
        state = "active" if settings.DEBUG else "INACTIVE — enable in /admin/ after checking amounts"
        self.stdout.write(self.style.SUCCESS(f"{created} offerings created ({state})."))
