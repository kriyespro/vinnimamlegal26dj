from decimal import Decimal

from django.conf import settings
from django.db import models


class Offering(models.Model):
    """A fixed-price item a client can buy online (service or consultation). Admin-managed."""

    class Kind(models.TextChoices):
        SERVICE = "service", "Fixed-price service"
        CONSULTATION = "consultation", "Consultation fee"

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=150)
    description = models.CharField(max_length=300, blank=True)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.SERVICE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Amount in INR charged to the client")
    active = models.BooleanField(default=False)

    class Meta:
        ordering = ["kind", "name"]
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=Decimal("0")), name="offering_amount_positive")]

    def __str__(self):
        return f"{self.name} (₹{self.amount})"


class Invoice(models.Model):
    """Something a client owes: a case fee, a fixed-price service or a consultation."""

    class Kind(models.TextChoices):
        CASE = "case", "Case fee"
        SERVICE = "service", "Fixed-price service"
        CONSULTATION = "consultation", "Consultation fee"

    class Status(models.TextChoices):
        PENDING = "Pending", "Pending"
        PAID = "Paid", "Paid"
        REFUNDED = "Refunded", "Refunded"

    invoice_no = models.CharField(max_length=30, unique=True)
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="invoices")
    case = models.ForeignKey("portal.Case", null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices")
    consultation = models.OneToOneField(
        "portal.Consultation", null=True, blank=True, on_delete=models.SET_NULL, related_name="invoice"
    )
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.CASE)
    description = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["client", "status"], name="inv_client_status"),
            models.Index(fields=["status", "due_date"], name="inv_status_due"),
        ]
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=Decimal("0")), name="invoice_amount_positive"),
        ]

    def __str__(self):
        return f"{self.invoice_no} ₹{self.amount} {self.status}"


class Payment(models.Model):
    """One Razorpay order (and its payment) for an invoice."""

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        CAPTURED = "captured", "Captured"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    razorpay_order_id = models.CharField(max_length=64, unique=True)
    razorpay_payment_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    razorpay_refund_id = models.CharField(max_length=64, blank=True)
    amount_paise = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CREATED)
    failure_reason = models.CharField(max_length=300, blank=True)
    needs_review = models.BooleanField(default=False, help_text="e.g. a second payment captured for an already-paid invoice")
    created_at = models.DateTimeField(auto_now_add=True)
    captured_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"], name="pay_status"),
        ]
        ordering = ["-id"]
        constraints = [models.CheckConstraint(condition=models.Q(amount_paise__gt=0), name="payment_amount_positive")]

    def __str__(self):
        return f"{self.razorpay_order_id} {self.status}"


class RazorpayEvent(models.Model):
    """Every webhook delivery, keyed by Razorpay's event id so replays are ignored."""

    event_id = models.CharField(max_length=80, unique=True)
    event_type = models.CharField(max_length=60)
    payload = models.JSONField()
    handled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
