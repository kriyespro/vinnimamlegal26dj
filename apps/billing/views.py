import json
import logging

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_safe, require_POST

from apps.accounts.decorators import portal_required
from apps.accounts.models import User

from . import services
from .models import Invoice, Offering, Payment, RazorpayEvent

logger = logging.getLogger(__name__)


@require_POST
def buy(request, slug):
    """Create an invoice for a fixed-price offering; the amount always comes from the database."""
    if not request.user.is_authenticated:
        messages.error(request, "Please sign in (or create a free account) to pay online.")
        return redirect(f"{reverse('portal')}?next={reverse('pricing')}")
    return _buy(request, slug)


@portal_required(User.Role.CLIENT)
def _buy(request, slug):
    offering = get_object_or_404(Offering, slug=slug, active=True)
    # One open invoice per offering per client: re-clicking reuses it.
    invoice = Invoice.objects.filter(
        client=request.user, kind=offering.kind, description=offering.name, status=Invoice.Status.PENDING,
        amount=offering.amount, case__isnull=True, consultation__isnull=True,
    ).first() or services.create_invoice(
        client=request.user, kind=offering.kind, amount=offering.amount, description=offering.name
    )
    return redirect("billing_invoice", invoice_id=invoice.pk)


@require_safe
@portal_required(User.Role.CLIENT)
def invoice_detail(request, invoice_id):
    invoice = get_object_or_404(Invoice.objects.select_related("case"), pk=invoice_id, client=request.user)
    return render(
        request,
        "billing/invoice.html",
        {
            "invoice": invoice,
            "payments": invoice.payments.exclude(status=Payment.Status.CREATED),
            "payments_enabled": bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET),
        },
    )


@require_POST
@portal_required(User.Role.CLIENT)
def invoice_pay(request, invoice_id):
    """Create (or reuse) a Razorpay order and return the Checkout.js options."""
    invoice = get_object_or_404(Invoice, pk=invoice_id, client=request.user)
    try:
        payment = services.create_order(invoice)
    except services.BillingNotConfigured as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    except services.BillingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(
        {
            "key": settings.RAZORPAY_KEY_ID,
            "order_id": payment.razorpay_order_id,
            "amount": payment.amount_paise,
            "currency": payment.currency,
            "name": "VinnitaLegal",
            "description": invoice.description or invoice.invoice_no,
            "prefill": {"name": request.user.name, "email": request.user.email},
        }
    )


@require_POST
@portal_required(User.Role.CLIENT)
def checkout_verify(request):
    order_id = request.POST.get("razorpay_order_id", "")
    payment = Payment.objects.filter(razorpay_order_id=order_id, invoice__client=request.user).select_related("invoice").first()
    if payment is None:
        return HttpResponseBadRequest("Unknown order")
    try:
        outcome = services.verify_checkout(
            request.user, order_id, request.POST.get("razorpay_payment_id", ""),
            request.POST.get("razorpay_signature", ""), request=request,
        )
    except services.BillingError as exc:
        messages.error(request, str(exc))
    else:
        if outcome == "paid":
            messages.success(request, "Payment received. Thank you!")
        else:
            messages.success(request, "Payment is being processed. This page will show Paid once it is confirmed.")
    return redirect("billing_invoice", invoice_id=payment.invoice_id)


@csrf_exempt  # authenticated by the Razorpay HMAC signature, not a session
@require_POST
def webhook(request):
    raw = request.body
    if not services.webhook_signature_valid(raw, request.headers.get("X-Razorpay-Signature", "")):
        logger.warning("Razorpay webhook with invalid signature")
        return HttpResponse(status=400)
    try:
        event = json.loads(raw)
    except ValueError:
        return HttpResponse(status=400)
    event_id = request.headers.get("X-Razorpay-Event-Id") or ""
    if not event_id:
        return HttpResponse(status=400)
    record, created = RazorpayEvent.objects.get_or_create(
        event_id=event_id, defaults={"event_type": str(event.get("event", ""))[:60], "payload": event}
    )
    if not created and record.handled:
        return HttpResponse("duplicate")
    try:
        services.apply_webhook_event(event)
    except Exception:
        logger.exception("Webhook processing failed event=%s", event_id)
        return HttpResponse(status=500)  # Razorpay retries
    record.handled = True
    record.save(update_fields=["handled"])
    return HttpResponse("ok")


@require_POST
@portal_required(User.Role.CEO)
def refund(request, payment_id):
    payment = get_object_or_404(Payment.objects.select_related("invoice"), pk=payment_id)
    try:
        services.refund_payment(payment, request.user, request=request)
    except services.BillingError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Refund issued for {payment.invoice.invoice_no}.")
    return redirect(f"{reverse('portal_dashboard')}?panel=revenue")
