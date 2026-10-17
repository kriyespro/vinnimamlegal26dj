import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import url_has_allowed_host_and_scheme, urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.http import require_http_methods, require_POST

from apps.audit.service import client_ip, log

from .models import PolicyAcceptance, User

logger = logging.getLogger(__name__)
MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"


def _rate_limited(request, bucket, limit, seconds=3600):
    key = f"rl:{bucket}:{client_ip(request)}"
    try:
        count = cache.get(key, 0)
        if count >= limit:
            return True
        cache.set(key, count + 1, seconds)
    except Exception:  # cache outage must not take login/signup down (axes still throttles logins via the DB)
        logger.exception("rate-limit cache unavailable")
    return False


def _accept_policy(request, user):
    PolicyAcceptance.objects.get_or_create(
        user=user, version=settings.POLICY_VERSION, defaults={"ip_address": client_ip(request)}
    )


def _signup(request):
    if _rate_limited(request, "signup", 10):
        messages.error(request, "Too many attempts. Please try again later.")
        return redirect("portal")
    name = (request.POST.get("name") or "").strip()[:120]
    email = (request.POST.get("email") or "").strip().lower()
    password = request.POST.get("password") or ""
    if not request.POST.get("policy"):
        messages.error(request, "You must accept the Portal Usage Policy to create an account.")
        return redirect("portal")
    if password != (request.POST.get("confirm_password") or ""):
        messages.error(request, "Passwords do not match.")
        return redirect("portal")
    try:
        if not name:
            raise ValidationError("Please enter your full name.")
        validate_email(email)
        candidate = User(email=email, name=name)
        validate_password(password, candidate)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("portal")
    if User.objects.filter(email__iexact=email).exists():
        messages.error(request, "Could not create account. If you already registered, sign in or reset your password.")
        return redirect("portal")
    user = User.objects.create_user(email=email, password=password, name=name, role=User.Role.CLIENT)
    _accept_policy(request, user)
    login(request, user, backend=MODEL_BACKEND)
    log(request, user, "signup", email)
    messages.success(request, "Account created. Welcome!")
    return redirect("portal_dashboard")


def send_reset_link(request, user, *, welcome=False):
    """Email a single-use set-password link (also used by the admin console to onboard staff)."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = request.build_absolute_uri(reverse("portal_reset", kwargs={"uidb64": uid, "token": token}))
    if welcome:
        subject = "Your VinnitaLegal portal account"
        intro = "An account has been created for you on the VinnitaLegal portal. Set your password with this link"
    else:
        subject = "Reset your VinnitaLegal portal password"
        intro = "Use this link to set a new password"
    send_mail(
        subject,
        f"Hello {user.name},\n\n{intro} (valid for 3 days, works once):\n{link}\n\n"
        "If you did not expect this email, you can ignore it.",
        None,
        [user.email],
    )


def _forgot_request(request):
    email = (request.POST.get("email") or "").strip().lower()
    neutral = "If an account exists for that email, a password reset link has been sent."
    if _rate_limited(request, "forgot", 5):
        messages.error(request, "Too many attempts. Please try again later.")
        return redirect(f"{reverse('portal')}?mode=forgot")
    user = User.objects.filter(email__iexact=email, is_active=True).first() if "@" in email else None
    if user:
        send_reset_link(request, user)
        log(request, user, "password_reset_requested", email)
    messages.success(request, neutral)
    return redirect(f"{reverse('portal')}?mode=forgot")


def _login(request):
    email = (request.POST.get("email") or "").strip().lower()
    password = request.POST.get("password") or ""
    if not request.POST.get("policy"):
        messages.error(request, "You must accept the Portal Usage Policy as a condition of access.")
        return redirect("portal")
    try:
        user = authenticate(request, username=email, password=password)
    except PermissionDenied:
        messages.error(request, "Too many failed attempts. Try again in an hour or reset your password.")
        return redirect("portal")
    if user is None:
        messages.error(request, "Invalid email or password, or account revoked.")
        log(request, None, "login_failed", email)
        return redirect("portal")
    _accept_policy(request, user)
    login(request, user)
    log(request, user, "login", user.role)
    messages.success(request, f"Welcome, {user.name} ({user.get_role_display()}).")
    next_url = request.POST.get("next") or ""
    if next_url.startswith("/") and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("portal_dashboard")


@require_http_methods(["GET", "HEAD", "POST"])
def portal(request):
    if request.user.is_authenticated:
        return redirect("portal_dashboard")
    if request.method in ("GET", "HEAD"):
        return render(request, "portal/portal.html")
    action = request.POST.get("action", "login")
    if action == "signup":
        return _signup(request)
    if action == "forgot_request":
        return _forgot_request(request)
    return _login(request)


@require_POST
def portal_logout(request):
    if request.user.is_authenticated:
        log(request, request.user, "logout")
    logout(request)
    messages.success(request, "Signed out.")
    return redirect("portal")


def _user_from_token(uidb64, token):
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        return None
    return user if default_token_generator.check_token(user, token) else None


@require_http_methods(["GET", "HEAD", "POST"])
def portal_reset(request, uidb64, token):
    user = _user_from_token(uidb64, token)
    if user is None:
        messages.error(request, "This reset link is invalid or has expired. Request a new one.")
        return redirect(f"{reverse('portal')}?mode=forgot")
    if request.method == "POST":
        password = request.POST.get("password") or ""
        if password != (request.POST.get("confirm_password") or ""):
            messages.error(request, "Passwords do not match.")
        else:
            try:
                validate_password(password, user)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                user.set_password(password)
                user.save(update_fields=["password"])
                log(request, user, "password_reset", user.email)
                messages.success(request, "Password updated. Sign in with your new password.")
                return redirect("portal")
    return render(request, "portal/reset.html", {"uidb64": uidb64, "token": token})
