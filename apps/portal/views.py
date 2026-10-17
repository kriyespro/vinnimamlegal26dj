import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_safe, require_POST

from apps.accounts.decorators import portal_required
from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.audit.service import log
from apps.billing.models import Invoice, Offering
from apps.billing.services import create_invoice
from apps.leads.models import Enquiry, EnquiryOutreach
from apps.leads.services import whatsapp_url

from . import rows
from .access import cases_for, get_case
from .models import (
    Case,
    CaseMessage,
    CaseUpdate,
    Communication,
    Conflict,
    Consultation,
    DocRequest,
    Document,
    Draft,
    Incident,
    Milestone,
)

logger = logging.getLogger(__name__)
ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png"}
MAGIC = {
    ".pdf": (b"%PDF",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
}
CONTENT_TYPES = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
CLIENT, PARTNER, STAFF, CEO = User.Role.CLIENT, User.Role.PARTNER, User.Role.STAFF, User.Role.CEO


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_fetch(request):
    """Inline one-click actions post via fetch and don't need a redirect/flash."""
    return request.headers.get("X-Requested-With") == "fetch"


def _clean(request, name, max_len=2000):
    return (request.POST.get(name) or "").strip()[:max_len]


def _dashboard_url(**params):
    params = {k: v for k, v in params.items() if v not in (None, "")}
    base = reverse("portal_dashboard")
    if params:
        from urllib.parse import urlencode

        return f"{base}?{urlencode(params)}"
    return base


def _after_action(request, *, tab=None, case_id=None, view=None, panel=None):
    """Return to the right dashboard view after an action (port of Flask _portal_redirect)."""
    user = request.user
    rc = _int(request.POST.get("redirect_case") or case_id) or None
    rt = request.POST.get("redirect_tab") or tab
    if user.role == PARTNER:
        return redirect(_dashboard_url(case=rc, tab=rt))
    if user.role == STAFF:
        rp = request.POST.get("redirect_panel") or panel
        if not rp and rc:
            rp = "cases"
        return redirect(_dashboard_url(panel=rp, case=rc, tab=rt))
    return redirect(_dashboard_url(view=view))


# ---------------------------------------------------------------- dashboard


@require_safe
@portal_required()
def dashboard(request):
    user = request.user
    params = request.GET
    view = params.get("view") or "overview"

    if user.role == CLIENT:
        jobs = rows.build_client_jobs(user)
        # Open the job that needs the client's attention first (docs to upload / money due).
        jobs.sort(key=lambda j: (-(len(j["needed_docs"]) + sum(1 for i in j["invoices"] if i["status"] == "Pending")), -j["case"]["id"]))
        payable = rows.payable_invoices_for(user)
        return render(
            request,
            "portal/client_dashboard.html",
            {
                "user": user,
                "jobs": jobs,
                "needed_docs_total": sum(len(j["needed_docs"]) for j in jobs),
                "action_alerts_total": sum(1 for j in jobs for a in j["alerts"] if a["status"] == "action_needed"),
                "due_total": float(sum(i["amount"] for i in payable)),
                "consultations": rows.consultations_for(user),
                "payable_invoices": payable,
                "view": view,
            },
        )

    if user.role == PARTNER:
        jobs = rows.build_partner_jobs(user)
        # Most urgent first: unanswered client messages, then drafts waiting for approval.
        jobs.sort(key=lambda j: (-(j["pending_replies"] + j["pending_drafts"]), -j["case"]["id"]))
        open_case = _int(params.get("case")) or (jobs[0]["case"]["id"] if jobs else None)
        return render(
            request,
            "portal/partner_dashboard.html",
            {
                "user": user,
                "jobs": jobs,
                "consultations": rows.consultations_for(user),
                "client_messages_total": sum(j["pending_replies"] for j in jobs),
                "pending_drafts": rows.pending_drafts_count(user),
                "open_case": open_case,
                "active_tab": params.get("tab") or "progress",
            },
        )

    if user.role == STAFF:
        jobs = rows.build_staff_jobs(user)
        # Cases that need the office first: missing documents, then unpaid invoices.
        jobs.sort(key=lambda j: (-(len(j["needed_docs"]) + len(j["due_invoices"])), -j["case"]["id"]))
        enquiries = []
        for eq in rows.enquiry_rows():
            service = eq["service"] or "your enquiry"
            text = (
                f"Hi {eq['name']}, thank you for reaching out to VinnitaLegal regarding {service}. "
                f"This is {user.name} from our office. Happy to help — when is a good time to speak?"
            )
            enquiries.append({**eq, "whatsapp_link": whatsapp_url(eq["phone"], text)})
        open_case = _int(params.get("case")) or (jobs[0]["case"]["id"] if jobs else None)
        return render(
            request,
            "portal/staff_dashboard.html",
            {
                "user": user,
                "jobs": jobs,
                "enquiries": enquiries,
                "new_leads": sum(1 for e in enquiries if e["status"] == "new"),
                "docs_pending_total": sum(len(j["needed_docs"]) for j in jobs),
                "due_invoices_total": sum(len(j["due_invoices"]) for j in jobs),
                "active_panel": params.get("panel") or "leads",
                "open_case": open_case,
                "active_tab": params.get("tab") or "progress",
            },
        )

    if user.role == CEO:
        m = rows.build_ceo_dashboard()
        charts = {
            "case_status": m["chart_case_status"],
            "revenue": m["chart_revenue"],
            "leads": m["chart_leads"],
            "sources": m["chart_sources"],
            "partners": m["chart_partner_load"],
        }
        return render(
            request,
            "portal/ceo_dashboard.html",
            {
                "user": user,
                "m": m,
                # json.dumps + <, >, & escaped so the blob is safe inside <script>.
                "charts_json": json.dumps(charts).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"),
                "active_panel": params.get("panel") or "overview",
            },
        )
    raise PermissionDenied


# ------------------------------------------------------------ client actions


@require_POST
@portal_required(CLIENT)
def consultation_book(request):
    case_id = _int(request.POST.get("case_id")) or None
    case = get_case(request.user, case_id) if case_id else None
    practice_area = _clean(request, "practice_area", 80)
    preferred_time = _clean(request, "preferred_time", 20)
    mode = _clean(request, "mode", 6) or "Video"
    try:
        preferred_date = date.fromisoformat(_clean(request, "preferred_date", 10))
    except ValueError:
        preferred_date = None
    if not practice_area or not preferred_time or not preferred_date:
        messages.error(request, "Practice area, date and time are required.")
        return redirect("portal_dashboard")
    if preferred_date < timezone.localdate():
        messages.error(request, "Choose a date that is today or later.")
        return redirect("portal_dashboard")
    if mode not in Consultation.Mode.values:
        return HttpResponseBadRequest("Invalid mode")
    consultation = Consultation.objects.create(
        client=request.user,
        case=case,
        practice_area=practice_area,
        preferred_date=preferred_date,
        preferred_time=preferred_time,
        mode=mode,
        note=_clean(request, "note", 500),
    )
    log(request, request.user, "consultation_requested", f"{preferred_date}:{preferred_time}")
    fee = Offering.objects.filter(kind=Offering.Kind.CONSULTATION, active=True).first()
    if fee:
        invoice = create_invoice(
            client=request.user, kind=Invoice.Kind.CONSULTATION, amount=fee.amount,
            description=f"{fee.name} — {preferred_date}", case=case, consultation=consultation,
        )
        messages.success(request, "Consultation requested. Pay the consultation fee to get the slot confirmed.")
        return redirect("billing_invoice", invoice_id=invoice.pk)
    messages.success(request, "Consultation requested. Your assigned expert will confirm the slot.")
    return redirect("portal_dashboard")


@require_POST
@portal_required(PARTNER)
def consultation_status(request, consultation_id):
    status = _clean(request, "status", 12)
    if status not in Consultation.Status.values:
        return HttpResponseBadRequest("Invalid status")
    consultation = get_object_or_404(Consultation.objects.select_related("case"), pk=consultation_id)
    if consultation.case_id and consultation.case.partner_id != request.user.id:
        raise Http404
    invoice = Invoice.objects.filter(consultation=consultation).first()
    if status == Consultation.Status.CONFIRMED and invoice and invoice.status != Invoice.Status.PAID:
        messages.error(request, "The client has not paid the consultation fee yet.")
        return _after_action(request)
    consultation.status = status
    consultation.save(update_fields=["status"])
    log(request, request.user, "consultation_updated", f"{consultation_id}:{status}")
    messages.success(request, "Consultation status updated.")
    return _after_action(request)


@require_POST
@portal_required(CLIENT)
def client_query(request):
    body = _clean(request, "body")
    case = get_case(request.user, _int(request.POST.get("case_id")))
    if not body:
        messages.error(request, "Message cannot be empty.")
        return redirect(_dashboard_url(view="messages"))
    CaseMessage.objects.create(case=case, author=request.user, body=body)
    log(request, request.user, "client_query_submitted", case.pk)
    messages.success(request, "Message sent to your legal team.")
    return redirect("portal_dashboard")


# ----------------------------------------------------- partner/staff actions


@require_POST
@portal_required(PARTNER, STAFF)
def message_reply(request):
    case = get_case(request.user, _int(request.POST.get("case_id")))
    body = _clean(request, "body")
    if not body:
        messages.error(request, "Message cannot be empty.")
        return _after_action(request, tab="messages", case_id=case.pk)
    CaseMessage.objects.create(case=case, author=request.user, body=body)
    log(request, request.user, "partner_message_sent", case.pk)
    messages.success(request, "Reply sent to client.")
    return _after_action(request, tab="messages", case_id=case.pk)


@require_POST
@portal_required(PARTNER, STAFF)
def case_update(request, case_id):
    case = get_case(request.user, case_id)
    body = _clean(request, "body")
    tab = request.POST.get("redirect_tab") or "client"
    panel = "cases" if request.user.role == STAFF else None
    if not body:
        messages.error(request, "Update cannot be empty.")
        return _after_action(request, tab=tab, case_id=case.pk, panel=panel)
    kind = _clean(request, "update_kind", 20)
    if kind == "document":
        body = f"[Document update] {body}"
    elif kind == "payment" or tab == "payments":
        body = f"[Payment update] {body}"
    CaseUpdate.objects.create(case=case, author=request.user, body=body)
    log(request, request.user, "client_update_posted", f"case:{case.pk}")
    messages.success(request, "Update posted on client dashboard.")
    return _after_action(request, tab=tab if panel else "updates", case_id=case.pk, panel=panel)


@require_POST
@portal_required(PARTNER)
def milestone_update(request, milestone_id):
    status = _clean(request, "status", 12)
    milestone = get_object_or_404(Milestone.objects.select_related("case"), pk=milestone_id)
    if milestone.case.partner_id != request.user.id:
        raise Http404
    if status not in Milestone.Status.values:
        messages.error(request, "Invalid milestone status.")
        return _after_action(request, tab="progress", case_id=milestone.case_id)
    milestone.status = status
    milestone.completed_at = timezone.now() if status == "done" else None
    milestone.save(update_fields=["status", "completed_at"])
    log(request, request.user, "milestone_updated", f"{milestone_id}:{status}")
    messages.success(request, "Progress milestone updated for the client.")
    return _after_action(request, tab="progress", case_id=milestone.case_id)


@require_POST
@portal_required(PARTNER, STAFF)
def document_request_add(request, case_id):
    case = get_case(request.user, case_id)
    title = _clean(request, "title", 200)
    if not title:
        messages.error(request, "Document request name is required.")
        return _after_action(request, tab="documents", case_id=case.pk)
    with transaction.atomic():
        next_order = (case.doc_requests.aggregate(m=Max("sort_order"))["m"] or 0) + 1
        DocRequest.objects.create(case=case, title=title, sort_order=next_order)
    log(request, request.user, "document_requested", f"case:{case.pk}:{title}")
    messages.success(request, "Document request added to the client dashboard.")
    return _after_action(request, tab="documents", case_id=case.pk)


@require_POST
@portal_required(PARTNER, STAFF)
def document_request_status(request, request_id):
    item = get_object_or_404(DocRequest, pk=request_id, case__in=cases_for(request.user))
    status = _clean(request, "status", 10)
    if status not in DocRequest.Status.values:
        return HttpResponseBadRequest("Invalid status")
    item.status = status
    item.save(update_fields=["status"])
    log(request, request.user, "document_request_updated", f"{request_id}:{status}")
    messages.success(request, "Document checklist updated.")
    return _after_action(request, tab="documents", case_id=item.case_id)


@require_POST
@portal_required(PARTNER)
def case_status(request, case_id):
    case = get_case(request.user, case_id)
    status = _clean(request, "status", 20)
    if status not in Case.Status.values:
        messages.error(request, "Invalid case status.")
        return _after_action(request, tab="progress", case_id=case.pk)
    hearing_raw = _clean(request, "hearing_date", 10)
    if hearing_raw:
        try:
            case.hearing_date = date.fromisoformat(hearing_raw)
        except ValueError:
            messages.error(request, "Invalid hearing date.")
            return _after_action(request, tab="progress", case_id=case.pk)
    billing = _clean(request, "billing_note", 200)
    if billing:
        case.billing_note = billing
    case.status = status
    case.save(update_fields=["status", "hearing_date", "billing_note"])
    log(request, request.user, "status_update", f"case:{case.pk}:{status}")
    messages.success(request, "Case updated on portal (§3.1 / §3.3).")
    return _after_action(request, tab="progress", case_id=case.pk)


def _review_draft(request, draft_id, new_status):
    draft = get_object_or_404(Draft, pk=draft_id, case__partner=request.user)
    if draft.status != Draft.Status.PENDING:
        messages.error(request, "This draft has already been reviewed.")
        return _after_action(request, tab="drafts", case_id=draft.case_id)
    draft.status = new_status
    draft.reviewed_by = request.user
    draft.reviewed_at = timezone.now()
    draft.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    log(request, request.user, f"draft_{new_status}", draft.title)
    messages.success(request, f"Draft {new_status}: {draft.title}")
    return _after_action(request, tab="drafts", case_id=draft.case_id)


@require_POST
@portal_required(PARTNER)
def draft_approve(request, draft_id):
    return _review_draft(request, draft_id, Draft.Status.APPROVED)


@require_POST
@portal_required(PARTNER)
def draft_reject(request, draft_id):
    return _review_draft(request, draft_id, Draft.Status.REJECTED)


@require_POST
@portal_required(PARTNER)
def conflict_disclose(request):
    client_name = _clean(request, "prospective_client", 200)
    note = _clean(request, "note")
    if not client_name or not note:
        messages.error(request, "Conflict disclosure requires client and note.")
        return redirect("portal_dashboard")
    Conflict.objects.create(partner=request.user, prospective_client=client_name, note=note)
    log(request, request.user, "conflict_disclosure", client_name)
    messages.success(request, "Conflict disclosure recorded for Compliance review (§3.2).")
    return redirect("portal_dashboard")


# ------------------------------------------------------------- staff actions


@require_POST
@portal_required(STAFF)
def comms_log(request):
    case = get_case(request.user, _int(request.POST.get("case_id")))
    ctype = _clean(request, "type", 20) or "Call"
    note = _clean(request, "note")
    if not note:
        messages.error(request, "Communication note is required.")
        return _after_action(request, panel="cases")
    Communication.objects.create(case=case, staff=request.user, type=ctype, note=note)
    log(request, request.user, "comms_logged", f"{case.pk}/{ctype}")
    messages.success(request, f"{ctype} logged on case file (§2.2).")
    return _after_action(request, panel="cases", case_id=case.pk)


@require_POST
@portal_required(STAFF)
def enquiry_whatsapp(request, enquiry_id):
    enquiry = get_object_or_404(Enquiry, pk=enquiry_id)
    EnquiryOutreach.objects.create(
        enquiry=enquiry, staff=request.user, channel="whatsapp", note="WhatsApp follow-up initiated"
    )
    enquiry.status = Enquiry.Status.WHATSAPP_SENT
    enquiry.save(update_fields=["status"])
    log(request, request.user, "enquiry_whatsapp_logged", enquiry.pk)
    if _is_fetch(request):
        return HttpResponse(status=204)
    messages.success(request, f"WhatsApp outreach logged for {enquiry.name}.")
    return _after_action(request, panel="leads")


@require_POST
@portal_required(STAFF)
def enquiry_status(request, enquiry_id):
    enquiry = get_object_or_404(Enquiry, pk=enquiry_id)
    status = _clean(request, "status", 14)
    if status not in Enquiry.Status.values:
        return HttpResponseBadRequest("Invalid status")
    enquiry.status = status
    enquiry.save(update_fields=["status"])
    log(request, request.user, "enquiry_status_updated", f"{enquiry_id}:{status}")
    if _is_fetch(request):
        return HttpResponse(status=204)
    messages.success(request, "Lead status updated.")
    return _after_action(request, panel="leads")


@require_POST
@portal_required(STAFF)
def partner_message(request):
    case = get_case(request.user, _int(request.POST.get("case_id")))
    body = _clean(request, "body")
    if not body:
        messages.error(request, "Message cannot be empty.")
        return _after_action(request, panel="cases", tab="partner", case_id=case.pk)
    from .models import StaffMessage

    StaffMessage.objects.create(case=case, staff=request.user, partner=case.partner, body=body)
    log(request, request.user, "staff_message_to_partner", case.pk)
    messages.success(request, "Message sent to partner.")
    return _after_action(request, panel="cases", tab="partner", case_id=case.pk)


@require_POST
@portal_required(STAFF)
def escalate(request):
    case_id = _int(request.POST.get("case_id")) or None
    case = get_case(request.user, case_id) if case_id else None
    note = _clean(request, "note") or "Client requested legal advice/opinion — escalated to Partner (§2.4)."
    Incident.objects.create(reporter=request.user, kind=Incident.Kind.ESCALATION, note=note, case=case)
    log(request, request.user, "escalation_to_partner", case.pk if case else "n/a")
    messages.success(request, "Escalated to assigned Partner. Do not advise the client directly (§2.4).")
    return _after_action(request, panel="escalate")


@require_POST
@portal_required(STAFF)
def breach_report(request):
    note = _clean(request, "note") or "Suspected breach / phishing / unauthorised access reported to Compliance/IT."
    Incident.objects.create(reporter=request.user, kind=Incident.Kind.BREACH, note=note)
    log(request, request.user, "breach_report", "escalated")
    messages.success(request, "Incident reported to Compliance / IT Officer (§2.3).")
    return _after_action(request, panel="escalate")


# ----------------------------------------------------------------- documents


def _validate_upload(upload):
    """Return (clean_filename, ext, error)."""
    name = Path(upload.name).name.replace("\x00", "")[:255]
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXT:
        return None, None, "Format not allowed. Use PDF, JPEG or PNG (§4.3)."
    if upload.size > settings.MAX_UPLOAD_BYTES:
        return None, None, "File exceeds 10 MB limit (§4.3)."
    head = upload.read(16)
    upload.seek(0)
    if not any(head.startswith(sig) for sig in MAGIC[ext]):
        return None, None, "File content does not match its extension."
    return name, ext, None


@require_POST
@portal_required(CLIENT, PARTNER, STAFF)
def document_upload(request):
    case = get_case(request.user, _int(request.POST.get("case_id")))
    upload = request.FILES.get("file")
    if not upload:
        messages.error(request, "No file selected.")
        return _after_action(request, tab="documents", case_id=case.pk)
    name, ext, error = _validate_upload(upload)
    if error:
        messages.error(request, error)
        return _after_action(request, tab="documents", case_id=case.pk)
    with transaction.atomic():
        doc = Document(case=case, uploaded_by=request.user, filename=name, mime=CONTENT_TYPES[ext], size=upload.size)
        doc.file.save(name, upload, save=False)
        doc.save()
        if request.user.role == CLIENT:
            needed_qs = case.doc_requests.filter(status=DocRequest.Status.NEEDED).order_by("sort_order", "id")
            request_id = _int(request.POST.get("request_id"))
            needed = needed_qs.filter(pk=request_id).first() if request_id else needed_qs.first()
            if needed:
                needed.status = DocRequest.Status.UPLOADED
                needed.save(update_fields=["status"])
    log(request, request.user, "document_upload", name)
    if request.user.role == PARTNER:
        messages.success(request, f"{name} uploaded — client can view it on their dashboard.")
    else:
        messages.success(request, f"{name} uploaded. Action logged for audit.")
    return _after_action(request, tab="documents", case_id=case.pk, view="documents")


@require_safe
@portal_required()
def document_download(request, doc_id):
    doc = get_object_or_404(Document, pk=doc_id, case__in=cases_for(request.user))
    try:
        handle = doc.file.open("rb")
    except FileNotFoundError:
        messages.error(request, "File not found on server. Please re-upload the document.")
        return redirect(_dashboard_url(view="documents"))
    log(request, request.user, "document_view", doc.filename)
    ext = Path(doc.filename).suffix.lower()
    response = FileResponse(handle, as_attachment=True, filename=doc.filename, content_type=CONTENT_TYPES.get(ext, "application/octet-stream"))
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


MAX_INVOICE = Decimal("1000000")


@require_POST
@portal_required(PARTNER, STAFF)
def invoice_create(request, case_id):
    """Raise a case invoice; the client then pays it online (amount fixed server-side from here on)."""
    case = get_case(request.user, case_id)
    description = _clean(request, "description", 200)
    try:
        amount = Decimal(_clean(request, "amount", 12)).quantize(Decimal("0.01"))
    except InvalidOperation:
        amount = None
    due_raw = _clean(request, "due_date", 10)
    due_ok = True
    due_date = None
    if due_raw:
        try:
            due_date = date.fromisoformat(due_raw)
        except ValueError:
            due_ok = False
    if not description or amount is None or not (Decimal("0") < amount <= MAX_INVOICE) or not due_ok:
        messages.error(request, "Enter a description, an amount between ₹1 and ₹10,00,000, and a valid due date.")
    else:
        invoice = create_invoice(
            client=case.client, kind=Invoice.Kind.CASE, amount=amount, description=description,
            case=case, due_date=due_date,
        )
        CaseUpdate.objects.create(
            case=case, author=request.user,
            body=f"[Payment update] Invoice {invoice.invoice_no} for ₹{amount:.0f} raised — pay online from your dashboard.",
        )
        log(request, request.user, "invoice_created", f"{invoice.invoice_no}:{case.pk}:{amount}")
        messages.success(request, f"Invoice {invoice.invoice_no} raised. The client can pay it online.")
    return _after_action(request, tab="payments", case_id=case.pk, panel="cases" if request.user.role == STAFF else None)


@require_POST
@portal_required(PARTNER)
def milestone_add(request, case_id):
    """Partners define the steps the client sees on their checklist."""
    case = get_case(request.user, case_id)
    title = _clean(request, "title", 200)
    if not title:
        messages.error(request, "Milestone name is required.")
        return _after_action(request, tab="progress", case_id=case.pk)
    with transaction.atomic():
        next_order = (case.milestones.aggregate(m=Max("sort_order"))["m"] or 0) + 1
        Milestone.objects.create(case=case, title=title, detail=_clean(request, "detail", 300), sort_order=next_order)
    log(request, request.user, "milestone_added", f"case:{case.pk}:{title}")
    messages.success(request, "Milestone added to the client's checklist.")
    return _after_action(request, tab="progress", case_id=case.pk)
