from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_safe

from apps.catalog.data import (
    FEATURED_STATES,
    REGIONS,
    SERVICE_CATALOG,
    STATE_BY_SLUG,
    STATE_CATALOG,
    services_for_state,
)

from . import seo
from .search import build_search_items, search


def page(template, url_name=None):
    """Thin view for a static marketing page (+ JSON-LD where defined)."""

    @require_safe
    def view(request):
        ctx = {"jsonld": seo.for_page(request, url_name)} if url_name else {}
        if url_name == "faq":
            ctx["faqs"] = seo.faqs()
        return render(request, template, ctx)

    return view


@require_safe
def site_search(request):
    q = (request.GET.get("q") or "").strip()
    return render(request, "search.html", {"q": q, "results": search(build_search_items(), q)})


@require_safe
def gst_compliance(request):
    # GST / accounts service is hidden — send visitors to legal services.
    return redirect("services")


@require_safe
def services_by_state(request, state_slug=None):
    active = None
    state_services = []
    if state_slug:
        active = STATE_BY_SLUG.get(state_slug)
        if not active:
            raise Http404
        state_services = services_for_state(state_slug)
    return render(
        request,
        "services-by-state.html",
        {
            "states": STATE_CATALOG,
            "regions": REGIONS,
            "active_state": active,
            "state_services": state_services,
            "all_services": SERVICE_CATALOG,
            "featured_states": FEATURED_STATES,
        },
    )


@require_safe
def pricing(request):
    from apps.billing.models import Offering

    offerings = {o.slug: o for o in Offering.objects.filter(active=True, kind=Offering.Kind.SERVICE)}
    return render(request, "pricing.html", {"offerings": offerings})


# ----- error pages (friendly; never expose internals) -----
def _error(request, template, status):
    return render(request, template, status=status)


def error_400(request, exception=None):
    return _error(request, "errors/400.html", 400)


def error_403(request, exception=None):
    return _error(request, "errors/403.html", 403)


def error_404(request, exception=None):
    return _error(request, "errors/404.html", 404)


def error_500(request):
    # Must not depend on DB or context processors.
    from django.http import HttpResponseServerError
    from django.template.loader import render_to_string

    return HttpResponseServerError(render_to_string("errors/500.html"))


@require_safe
def robots_txt(request):
    from django.conf import settings
    from django.http import HttpResponse
    from django.urls import reverse

    lines = [
        "User-agent: *",
        "Disallow: /portal",
        "Disallow: /billing",
        "Disallow: /admin/",
        f"Disallow: /{settings.ADMIN_URL}/",
        "Disallow: /search",
        "Disallow: /enquire",
        "Disallow: /healthz",
        f"Sitemap: {request.build_absolute_uri(reverse('sitemap'))}",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


@require_safe
def healthz(request):
    """Liveness/readiness probe for load balancers and uptime monitors (no secrets, never cached)."""
    from django.core.cache import cache
    from django.db import connection
    from django.http import JsonResponse

    checks = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = True
    except Exception:
        checks["database"] = False
    try:
        cache.set("healthz", "1", 10)
        checks["cache"] = cache.get("healthz") == "1"
    except Exception:
        checks["cache"] = False
    ok = all(checks.values())
    response = JsonResponse({"status": "ok" if ok else "degraded", **checks}, status=200 if ok else 503)
    response["Cache-Control"] = "no-store"
    return response


@require_safe
def security_txt(request):
    from datetime import date, timedelta

    from django.conf import settings
    from django.http import HttpResponse

    expires = (date.today() + timedelta(days=365)).isoformat() + "T00:00:00.000Z"
    body = (
        f"Contact: mailto:{settings.SITE_EMAIL}\n"
        f"Expires: {expires}\n"
        "Preferred-Languages: en\n"
        f"Canonical: {request.build_absolute_uri('/.well-known/security.txt')}\n"
    )
    return HttpResponse(body, content_type="text/plain; charset=utf-8")
