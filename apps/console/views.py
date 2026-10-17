"""Custom admin console (/admin/) for the owner. Django's own admin lives at /sd/."""
import logging
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_safe, require_http_methods, require_POST

from apps.accounts.decorators import portal_required
from apps.accounts.models import User
from apps.accounts.views import send_reset_link
from apps.audit.models import AuditLog
from apps.audit.service import log
from apps.billing.models import Invoice, Offering, Payment
from apps.leads.models import Enquiry
from apps.portal.models import Case, Consultation, Draft

from .forms import CaseForm, OfferingForm, UserCreateForm, UserEditForm

logger = logging.getLogger(__name__)
CEO = User.Role.CEO
PAGE_SIZE = 20


def console_required(view):
    return portal_required(CEO)(view)


def _page(request, queryset):
    return Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))


def _qs(request, *drop):
    """Current query string without `page` (for pager links)."""
    params = request.GET.copy()
    for key in ("page", *drop):
        params.pop(key, None)
    return params.urlencode()


def _render(request, template, ctx=None, nav=""):
    from django.conf import settings

    return render(request, template, {"nav": nav, "admin_url": settings.ADMIN_URL, **(ctx or {})})


# ------------------------------------------------------------------ dashboard


@require_safe
@console_required
def dashboard(request):
    money = lambda status: Invoice.objects.filter(status=status).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    users_by_role = {r["role"]: r["c"] for r in User.objects.filter(is_active=True).values("role").annotate(c=Count("id"))}
    cases_by_status = list(Case.objects.values("status").annotate(c=Count("id")).order_by("-c"))
    stats = [
        ("Active users", sum(users_by_role.values()), "users", "text-royal"),
        ("Open cases", Case.objects.exclude(status=Case.Status.COMPLETED).count(), "cases", "text-navy"),
        ("New leads", Enquiry.objects.filter(status="new").count(), "leads", "text-orange-600"),
        ("Revenue received", f"₹{money('Paid'):,.0f}", "billing", "text-green-600"),
        ("Awaiting payment", f"₹{money('Pending'):,.0f}", "billing", "text-orange-600"),
        ("Payments to review", Payment.objects.filter(needs_review=True).count(), "billing", "text-royal"),
    ]
    return _render(
        request,
        "console/dashboard.html",
        {
            "stats": stats,
            "users_by_role": users_by_role,
            "cases_by_status": cases_by_status,
            "recent_leads": Enquiry.objects.order_by("-id")[:6],
            "recent_audit": AuditLog.objects.select_related("user").order_by("-id")[:8],
            "pending_drafts": Draft.objects.filter(status="pending").count(),
            "consult_requested": Consultation.objects.filter(status="Requested").count(),
            "inactive_offerings": Offering.objects.filter(active=False).count(),
        },
        nav="dashboard",
    )


# ---------------------------------------------------------------------- users


@require_safe
@console_required
def users_list(request):
    qs = User.objects.order_by("role", "name")
    q = (request.GET.get("q") or "").strip()
    role = request.GET.get("role") or ""
    active = request.GET.get("active") or ""
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q))
    if role in User.Role.values:
        qs = qs.filter(role=role)
    if active in ("1", "0"):
        qs = qs.filter(is_active=active == "1")
    return _render(
        request,
        "console/users.html",
        {"page": _page(request, qs), "q": q, "role": role, "active": active, "roles": User.Role.choices, "qs": _qs(request)},
        nav="users",
    )


@require_http_methods(["GET", "HEAD", "POST"])
@console_required
def user_create(request):
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.set_unusable_password()
        user.save()
        send_reset_link(request, user, welcome=True)
        log(request, request.user, "console_user_created", f"{user.email}:{user.role}")
        messages.success(request, f"Account created for {user.name}. A set-password link was emailed to {user.email}.")
        return redirect("console_users")
    return _render(request, "console/form.html", {"form": form, "title": "Add user", "back": "console_users",
                   "note": "No password is typed here: the person gets an email link to set their own."}, nav="users")


def _last_ceo(user):
    return user.role == CEO and not User.objects.filter(role=CEO, is_active=True).exclude(pk=user.pk).exists()


@require_http_methods(["GET", "HEAD", "POST"])
@console_required
def user_edit(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    form = UserEditForm(request.POST or None, instance=target)
    if request.method == "POST" and form.is_valid():
        new_role, new_active = form.cleaned_data["role"], form.cleaned_data["is_active"]
        if target.pk == request.user.pk and (new_role != CEO or not new_active):
            messages.error(request, "You cannot demote or deactivate your own account.")
        elif _last_ceo(target) and (new_role != CEO or not new_active):
            messages.error(request, "At least one active Founder/CEO account must remain.")
        else:
            form.save()
            log(request, request.user, "console_user_updated", f"{target.email}:{new_role}:{'active' if new_active else 'inactive'}")
            messages.success(request, "User updated.")
            return redirect("console_users")
    return _render(request, "console/form.html", {"form": form, "title": f"Edit {target.name}", "back": "console_users",
                   "note": target.email, "extra_action": ("console_user_reset", target.pk, "Email a password-reset link")}, nav="users")


@require_POST
@console_required
def user_quick(request, user_id):
    """One-click role change / activate / deactivate from the users list (same guards as the edit form)."""
    target = get_object_or_404(User, pk=user_id)
    new_role = request.POST.get("role", target.role)
    new_active = target.is_active if "is_active" not in request.POST else request.POST.get("is_active") == "1"
    if new_role not in User.Role.values:
        return HttpResponseBadRequest("Invalid role")
    changing_away = new_role != CEO or not new_active
    if target.pk == request.user.pk and changing_away:
        messages.error(request, "You cannot demote or deactivate your own account.")
    elif _last_ceo(target) and changing_away:
        messages.error(request, "At least one active Founder/CEO account must remain.")
    else:
        target.role, target.is_active = new_role, new_active
        target.save(update_fields=["role", "is_active"])
        log(request, request.user, "console_user_updated", f"{target.email}:{new_role}:{'active' if new_active else 'inactive'}")
        messages.success(request, f"{target.name}: {target.get_role_display()}, {'active' if new_active else 'inactive'}.")
    return redirect(request.POST.get("back") if (request.POST.get("back") or "").startswith("/admin/") else "console_users")


@require_POST
@console_required
def user_reset(request, user_id):
    target = get_object_or_404(User, pk=user_id, is_active=True)
    send_reset_link(request, target)
    log(request, request.user, "console_reset_sent", target.email)
    messages.success(request, f"Password-reset link emailed to {target.email}.")
    return redirect("console_users")


# ---------------------------------------------------------------------- cases


@require_safe
@console_required
def cases_list(request):
    qs = Case.objects.select_related("client", "partner").prefetch_related("staff").order_by("-id")
    q = (request.GET.get("q") or "").strip()
    status = request.GET.get("status") or ""
    if q:
        qs = qs.filter(Q(case_no__icontains=q) | Q(title__icontains=q) | Q(client__name__icontains=q) | Q(client__email__icontains=q))
    if status in Case.Status.values:
        qs = qs.filter(status=status)
    return _render(request, "console/cases.html", {"page": _page(request, qs), "q": q, "status": status,
                   "statuses": Case.Status.choices, "qs": _qs(request)}, nav="cases")


@require_http_methods(["GET", "HEAD", "POST"])
@console_required
def case_create(request):
    form = CaseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        case = form.save()
        log(request, request.user, "console_case_created", case.case_no)
        messages.success(request, f"Case {case.case_no} created.")
        return redirect("console_cases")
    return _render(request, "console/form.html", {"form": form, "title": "New case", "back": "console_cases"}, nav="cases")


@require_http_methods(["GET", "HEAD", "POST"])
@console_required
def case_edit(request, case_id):
    case = get_object_or_404(Case, pk=case_id)
    form = CaseForm(request.POST or None, instance=case)
    if request.method == "POST" and form.is_valid():
        form.save()
        log(request, request.user, "console_case_updated", case.case_no)
        messages.success(request, "Case updated.")
        return redirect("console_cases")
    return _render(request, "console/form.html", {"form": form, "title": f"Edit {case.case_no}", "back": "console_cases"}, nav="cases")


@require_POST
@console_required
def case_quick_status(request, case_id):
    case = get_object_or_404(Case, pk=case_id)
    status = request.POST.get("status") or ""
    if status not in Case.Status.values:
        return HttpResponseBadRequest("Invalid status")
    case.status = status
    case.save(update_fields=["status"])
    log(request, request.user, "console_case_status", f"{case.case_no}:{status}")
    messages.success(request, f"{case.case_no} → {status}.")
    back = request.POST.get("back") or ""
    return redirect(back if back.startswith("/admin/") else "console_cases")


# ---------------------------------------------------------------------- leads


@require_safe
@console_required
def leads_list(request):
    qs = Enquiry.objects.order_by("-id")
    q = (request.GET.get("q") or "").strip()
    status = request.GET.get("status") or ""
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(email__icontains=q) | Q(service__icontains=q))
    if status in Enquiry.Status.values:
        qs = qs.filter(status=status)
    return _render(request, "console/leads.html", {"page": _page(request, qs), "q": q, "status": status,
                   "statuses": Enquiry.Status.choices, "qs": _qs(request)}, nav="leads")


@require_POST
@console_required
def lead_status(request, enquiry_id):
    lead = get_object_or_404(Enquiry, pk=enquiry_id)
    status = request.POST.get("status") or ""
    if status not in Enquiry.Status.values:
        return HttpResponseBadRequest("Invalid status")
    lead.status = status
    lead.save(update_fields=["status"])
    log(request, request.user, "console_lead_status", f"{lead.pk}:{status}")
    messages.success(request, "Lead updated.")
    return redirect("console_leads")


# -------------------------------------------------------------------- billing


@require_safe
@console_required
def billing_overview(request):
    status = request.GET.get("status") or ""
    invoices = Invoice.objects.select_related("client", "case").prefetch_related("payments").order_by("-id")
    if status in Invoice.Status.values:
        invoices = invoices.filter(status=status)
    review = Payment.objects.filter(needs_review=True).select_related("invoice", "invoice__client")
    return _render(request, "console/billing.html", {
        "page": _page(request, invoices), "status": status, "statuses": Invoice.Status.choices, "qs": _qs(request),
        "review": review, "offerings": Offering.objects.all(),
    }, nav="billing")


@require_http_methods(["GET", "HEAD", "POST"])
@console_required
def offering_create(request):
    form = OfferingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        offering = form.save()
        log(request, request.user, "console_offering_saved", f"{offering.slug}:{offering.amount}:{offering.active}")
        messages.success(request, "Offering saved.")
        return redirect("console_billing")
    return _render(request, "console/form.html", {"form": form, "title": "New fixed-price offering", "back": "console_billing"}, nav="billing")


@require_http_methods(["GET", "HEAD", "POST"])
@console_required
def offering_edit(request, offering_id):
    offering = get_object_or_404(Offering, pk=offering_id)
    form = OfferingForm(request.POST or None, instance=offering)
    if request.method == "POST" and form.is_valid():
        form.save()
        log(request, request.user, "console_offering_saved", f"{offering.slug}:{offering.amount}:{offering.active}")
        messages.success(request, "Offering updated.")
        return redirect("console_billing")
    return _render(request, "console/form.html", {"form": form, "title": f"Edit {offering.name}", "back": "console_billing"}, nav="billing")


@require_POST
@console_required
def offering_toggle(request, offering_id):
    offering = get_object_or_404(Offering, pk=offering_id)
    offering.active = not offering.active
    offering.save(update_fields=["active"])
    log(request, request.user, "console_offering_toggled", f"{offering.slug}:{offering.active}")
    messages.success(request, f"{offering.name} is now {'active' if offering.active else 'hidden'}.")
    return redirect("console_billing")


@require_POST
@console_required
def payment_reviewed(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id, needs_review=True)
    payment.needs_review = False
    payment.save(update_fields=["needs_review"])
    log(request, request.user, "console_payment_reviewed", payment.razorpay_order_id)
    messages.success(request, "Marked as reviewed.")
    return redirect("console_billing")


# ---------------------------------------------------------------------- audit


@require_safe
@console_required
def audit_list(request):
    qs = AuditLog.objects.select_related("user").order_by("-id")
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(action__icontains=q) | Q(ref__icontains=q) | Q(user__email__icontains=q))
    return _render(request, "console/audit.html", {"page": _page(request, qs), "q": q, "qs": _qs(request)}, nav="audit")
