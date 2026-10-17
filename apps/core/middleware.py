import secrets

from django.conf import settings

RAZORPAY = "https://*.razorpay.com"


def build_csp(nonce):
    """Per-request CSP.

    Inline <script> blocks must carry the request nonce, so injected inline scripts and inline event
    handlers are blocked. 'unsafe-eval' stays only because Alpine's standard build evaluates expressions;
    styles keep 'unsafe-inline' (Alpine :style / style attributes).
    """
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}' 'unsafe-eval' {RAZORPAY}",
            "style-src 'self' 'unsafe-inline'",
            "font-src 'self' data:",
            f"img-src 'self' data: {RAZORPAY}",
            f"connect-src 'self' {RAZORPAY}",
            f"frame-src {RAZORPAY}",
            f"form-action 'self' {RAZORPAY}",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "object-src 'none'",
            "upgrade-insecure-requests" if not settings.DEBUG else "",
        ]
    ).replace("; ;", ";").rstrip("; ")


class SecurityHeadersMiddleware:
    """Nonce-based CSP, Permissions-Policy and noindex hints on every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(16)
        response = self.get_response(request)
        if not request.path.startswith(f"/{settings.ADMIN_URL}/"):  # Django admin ships inline scripts
            response.headers.setdefault("Content-Security-Policy", build_csp(request.csp_nonce))
        if request.path.startswith(("/portal", "/billing", "/admin/", f"/{settings.ADMIN_URL}/", "/search", "/healthz")):
            response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(self), interest-cohort=()")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response


class TrailingSlashRedirectMiddleware:
    """`/about/` -> 301 `/about` when only the slash-less URL exists (one canonical URL per page, keeps inbound links)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if len(path) > 1 and path.endswith("/") and request.method in ("GET", "HEAD"):
            from django.http import HttpResponsePermanentRedirect
            from django.urls import Resolver404, resolve

            try:
                resolve(path)
            except Resolver404:
                try:
                    resolve(path.rstrip("/"))
                except Resolver404:
                    pass
                else:
                    target = path.rstrip("/") + (("?" + request.META["QUERY_STRING"]) if request.META.get("QUERY_STRING") else "")
                    return HttpResponsePermanentRedirect(target)
        return self.get_response(request)
