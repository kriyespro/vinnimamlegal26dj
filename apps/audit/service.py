import ipaddress

from django.conf import settings

from .models import AuditLog


def client_ip(request):
    """Real client address.

    Behind N trusted reverse proxies the client is the Nth entry from the right of X-Forwarded-For;
    never trust the header when TRUSTED_PROXY_COUNT is 0 (it is then attacker-controlled).
    """
    if not request:
        return None
    remote = request.META.get("REMOTE_ADDR")
    count = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    if count > 0:
        parts = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
        if len(parts) >= count:
            candidate = parts[-count]
            try:
                ipaddress.ip_address(candidate)
                return candidate
            except ValueError:
                pass
    return remote


def log(request, user, action, ref=""):
    """Record an audit event. `user` may be None (e.g. failed login)."""
    AuditLog.objects.create(
        user=user if user and user.is_authenticated else None,
        action=action[:60],
        ref=str(ref)[:300],
        ip_address=client_ip(request),
    )
