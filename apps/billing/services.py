"""Razorpay integration. The server decides amounts and paid-status; the browser never does.

Flow: create_order (amount from Invoice) -> Checkout.js in browser -> verify_checkout
(signature + fetch payment from Razorpay) and/or webhook -> mark_paid (idempotent).
"""
import hashlib
import hmac
import logging
import secrets
from decimal import ROUND_HALF_UP, Decimal

import razorpay
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.service import log
from apps.portal.models import CaseUpdate

from .models import Invoice, Payment

logger = logging.getLogger(__name__)


class BillingError(Exception):
    """User-presentable billing problem."""


class BillingNotConfigured(BillingError):
    pass


def to_paise(amount):
    return int((Decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def get_client():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise BillingNotConfigured("Online payments are not available right now.")
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def _hmac_hex(secret, message):
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def checkout_signature_valid(order_id, payment_id, signature):
    if not (order_id and payment_id and signature and settings.RAZORPAY_KEY_SECRET):
        return False
    expected = _hmac_hex(settings.RAZORPAY_KEY_SECRET, f"{order_id}|{payment_id}".encode())
    return hmac.compare_digest(expected, signature)


def webhook_signature_valid(raw_body, signature):
    if not (signature and settings.RAZORPAY_WEBHOOK_SECRET):
        return False
    return hmac.compare_digest(_hmac_hex(settings.RAZORPAY_WEBHOOK_SECRET, raw_body), signature)


def create_invoice(*, client, kind, amount, description="", case=None, consultation=None, due_date=None):
    with transaction.atomic():
        invoice = Invoice.objects.create(
            invoice_no=f"TMP-{secrets.token_hex(8)}",
            client=client, kind=kind, amount=amount, description=description[:200],
            case=case, consultation=consultation, due_date=due_date,
        )
        invoice.invoice_no = f"VL-INV-{invoice.pk:06d}"
        invoice.save(update_fields=["invoice_no"])
    return invoice


def create_order(invoice):
    """Return a Payment with a Razorpay order for this invoice (reusing an open one)."""
    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.status != Invoice.Status.PENDING:
            raise BillingError("This invoice is not payable.")
        paise = to_paise(invoice.amount)
        existing = invoice.payments.filter(status=Payment.Status.CREATED, amount_paise=paise).first()
        if existing:
            return existing
        try:
            order = get_client().order.create(
                {"amount": paise, "currency": "INR", "receipt": invoice.invoice_no,
                 "notes": {"invoice_id": str(invoice.pk), "invoice_no": invoice.invoice_no}}
            )
        except BillingError:
            raise
        except Exception:
            logger.exception("Razorpay order creation failed for invoice %s", invoice.pk)
            raise BillingError("Could not start the payment. Please try again shortly.") from None
        return Payment.objects.create(invoice=invoice, razorpay_order_id=order["id"], amount_paise=paise)


def mark_paid(payment_pk, razorpay_payment_id, *, source, request=None):
    """Idempotently record a captured payment. Returns True if this call changed state."""
    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related("invoice").get(pk=payment_pk)
        if payment.status == Payment.Status.CAPTURED:
            return False
        if payment.status == Payment.Status.REFUNDED:
            return False
        invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)
        try:
            payment.razorpay_payment_id = razorpay_payment_id
            payment.status = Payment.Status.CAPTURED
            payment.captured_at = timezone.now()
            payment.failure_reason = ""
            if invoice.status == Invoice.Status.PAID:
                payment.needs_review = True  # customer paid twice: flag for a manual refund
                logger.error("Duplicate capture payment=%s invoice=%s", payment.pk, invoice.pk)
            payment.save()
        except IntegrityError:
            logger.error("payment id %s already linked to another payment", razorpay_payment_id)
            return False
        if invoice.status == Invoice.Status.PENDING:
            invoice.status = Invoice.Status.PAID
            invoice.save(update_fields=["status"])
            if invoice.case_id:
                CaseUpdate.objects.create(
                    case_id=invoice.case_id, author=None,
                    body=f"[Payment received] Invoice {invoice.invoice_no} — ₹{invoice.amount:.0f} paid online. Thank you.",
                )
    log(request, invoice.client, "payment_captured", f"{invoice.invoice_no}:{payment.razorpay_payment_id}:{source}")
    return True


def verify_checkout(user, order_id, payment_id, signature, request=None):
    """Handle the browser callback. Returns 'paid' or 'processing'; raises BillingError otherwise."""
    payment = (
        Payment.objects.select_related("invoice")
        .filter(razorpay_order_id=order_id, invoice__client=user)
        .first()
    )
    if payment is None:
        raise BillingError("Payment not found.")
    if not checkout_signature_valid(order_id, payment_id, signature):
        log(request, user, "payment_signature_invalid", payment.invoice.invoice_no)
        raise BillingError("Payment could not be verified. If money was deducted it will be reconciled automatically.")
    try:
        remote = get_client().payment.fetch(payment_id)
    except BillingError:
        raise
    except Exception:
        logger.exception("Razorpay fetch failed payment=%s", payment_id)
        return "processing"  # webhook will finalise
    if (
        remote.get("order_id") != order_id
        or remote.get("amount") != payment.amount_paise
        or remote.get("currency") != payment.currency
    ):
        log(request, user, "payment_mismatch", payment.invoice.invoice_no)
        raise BillingError("Payment details did not match the invoice. Please contact support.")
    if remote.get("status") == "captured":
        mark_paid(payment.pk, payment_id, source="checkout", request=request)
        return "paid"
    return "processing"


def apply_webhook_event(event):
    """Apply a verified Razorpay webhook payload. Returns True when it was acted on."""
    etype = event.get("event", "")
    payload = event.get("payload", {})
    payment_entity = (payload.get("payment") or {}).get("entity") or {}
    refund_entity = (payload.get("refund") or {}).get("entity") or {}

    if etype in ("payment.captured", "order.paid", "payment.failed"):
        order_id = payment_entity.get("order_id") or (payload.get("order", {}).get("entity") or {}).get("id")
        payment = Payment.objects.filter(razorpay_order_id=order_id).first() if order_id else None
        if payment is None:
            logger.warning("Webhook %s for unknown order %s", etype, order_id)
            return False
        if etype == "payment.failed":
            if payment.status == Payment.Status.CREATED:
                payment.status = Payment.Status.FAILED
                payment.failure_reason = (payment_entity.get("error_description") or "")[:300]
                payment.save(update_fields=["status", "failure_reason"])
                return True
            return False
        if payment_entity.get("amount") != payment.amount_paise or payment_entity.get("currency") != payment.currency:
            logger.error("Webhook amount mismatch order=%s", order_id)
            return False
        return mark_paid(payment.pk, payment_entity.get("id"), source="webhook")

    if etype == "refund.processed":
        payment = Payment.objects.filter(razorpay_payment_id=refund_entity.get("payment_id")).first()
        if payment is None:
            return False
        return _mark_refunded(payment.pk, refund_entity.get("id", ""))
    return False


def _mark_refunded(payment_pk, refund_id):
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment_pk)
        if payment.status == Payment.Status.REFUNDED:
            return False
        payment.status = Payment.Status.REFUNDED
        payment.razorpay_refund_id = refund_id
        payment.save(update_fields=["status", "razorpay_refund_id"])
        invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)
        if invoice.status == Invoice.Status.PAID and not invoice.payments.filter(status=Payment.Status.CAPTURED).exists():
            invoice.status = Invoice.Status.REFUNDED
            invoice.save(update_fields=["status"])
    return True


def refund_payment(payment, user, request=None):
    """Full refund of a captured payment (CEO only — enforced by the view)."""
    if payment.status != Payment.Status.CAPTURED or not payment.razorpay_payment_id:
        raise BillingError("Only captured payments can be refunded.")
    try:
        refund = get_client().payment.refund(payment.razorpay_payment_id, {"amount": payment.amount_paise})
    except BillingError:
        raise
    except Exception:
        logger.exception("Razorpay refund failed payment=%s", payment.pk)
        raise BillingError("Refund could not be issued. Try again or use the Razorpay dashboard.") from None
    _mark_refunded(payment.pk, refund.get("id", ""))
    log(request, user, "payment_refunded", f"{payment.invoice.invoice_no}:{payment.razorpay_payment_id}")
