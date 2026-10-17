from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from urllib.parse import urlencode

from .models import PolicyAcceptance


def portal_required(*roles):
    """Authenticated + current-policy accepted + (optionally) one of `roles`.

    Authorisation is enforced here and again by object-level scoping in the views.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                messages.error(request, "Please sign in to access the portal.")
                if request.method == "GET":
                    return redirect(f"{reverse('portal')}?{urlencode({'next': request.get_full_path()})}")
                return redirect("portal")
            accepted = PolicyAcceptance.objects.filter(user=user, version=settings.POLICY_VERSION).exists()
            if not accepted:
                logout(request)
                messages.error(request, "Please sign in again and accept the Portal Usage Policy.")
                return redirect("portal")
            if roles and user.role not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
