import logging

from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.audit.service import client_ip

from .forms import EnquiryForm

logger = logging.getLogger(__name__)
RATE_LIMIT = 20  # submissions per IP per hour (shared office / carrier NAT friendly)


def _client_ip(request):
    return client_ip(request) or "unknown"


@require_POST
def enquire(request):
    """Public enquiry forms (contact page + service page hero panels)."""
    next_url = request.POST.get("next") or ""
    if not next_url:  # forms without a hidden `next` return to the page they were submitted from
        referer = request.META.get("HTTP_REFERER", "")
        if referer and url_has_allowed_host_and_scheme(referer, allowed_hosts={request.get_host()}):
            from urllib.parse import urlparse

            next_url = urlparse(referer).path
    if not next_url.startswith("/") or next_url.startswith("//") or not url_has_allowed_host_and_scheme(next_url, allowed_hosts=None):
        next_url = reverse("contact")

    key = f"enquiry-rate:{_client_ip(request)}"
    count = cache.get(key, 0)
    if count >= RATE_LIMIT:
        messages.error(request, "Too many requests. Please try again later.")
        return redirect(next_url)

    form = EnquiryForm(request.POST)
    if not form.is_valid():
        if "website" in form.errors:  # bot: pretend success
            messages.success(request, "Request received!")
        else:
            messages.error(request, "Please enter your name and a valid phone number.")
        return redirect(next_url)

    enquiry = form.save(commit=False)
    enquiry.source_page = (request.POST.get("source") or request.POST.get("source_page") or "unknown")[:100]
    enquiry.save()
    cache.set(key, count + 1, 3600)
    logger.info("enquiry_submitted id=%s source=%s", enquiry.pk, enquiry.source_page)
    messages.success(
        request,
        "Request received! Our expert will call you within 30 minutes during business hours.",
    )
    return redirect(next_url)
