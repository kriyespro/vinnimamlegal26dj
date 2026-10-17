"""Build the dict-shaped context the dashboard templates expect.

Templates were written against Flask/sqlite rows (row["x"] / row.x), so these
helpers return plain dicts with the same keys.
"""
from datetime import datetime

from django.db.models import Count, Prefetch, Q, Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.billing.models import Invoice
from apps.leads.models import Enquiry

from .access import cases_for
from .models import Case, Consultation, Draft, DocRequest, Milestone


def _fmt(value):
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")
    return value


def row(obj, **extra):
    data = {}
    for field in obj._meta.concrete_fields:
        if field.get_internal_type() == "FileField":
            continue
        data[field.attname] = _fmt(getattr(obj, field.attname))
    data.update(extra)
    return data


def _progress(milestones):
    total = len(milestones) or 1
    done = sum(1 for m in milestones if m.status == "done")
    in_progress = sum(1 for m in milestones if m.status == "in_progress")
    return int(round((done + 0.5 * in_progress) / total * 100))


def _current_step(milestones):
    return next((m for m in milestones if m.status == "in_progress"), None) or next(
        (m for m in milestones if m.status == "pending"), None
    )


def _case_queryset(user):
    return (
        cases_for(user)
        .select_related("client", "partner")
        .prefetch_related(
            "staff",
            "milestones",
            Prefetch("updates", queryset=_with_author("updates")),
            "doc_requests",
            "documents__uploaded_by",
            "invoices",
            "messages__author",
            "alerts",
            "drafts",
            "staff_messages__staff",
            "communications__staff",
        )
        .order_by("-id")
    )


def _with_author(rel):
    from .models import CaseUpdate

    return CaseUpdate.objects.select_related("author").order_by("-id")


def _update_rows(updates, limit):
    return [
        row(u, author_name=u.author.name if u.author else None, author_role=u.author.role if u.author else None)
        for u in list(updates.all())[:limit]
    ]


def _message_rows(messages, limit=None, newest_first=False):
    items = list(messages.all())
    if newest_first:
        items.reverse()
    if limit:
        items = items[:limit]
    return [row(m, author_name=m.author.name, author_role=m.author.role) for m in items]


def _doc_rows(documents, limit=None):
    items = list(documents.all())[:limit]
    return [
        row(d, uploader_name=d.uploaded_by.name, uploader_role=d.uploaded_by.role)
        for d in items
    ]


def build_client_jobs(user):
    jobs = []
    for c in _case_queryset(user):
        milestones = list(c.milestones.all())
        doc_reqs = list(c.doc_requests.all())
        jobs.append(
            {
                "case": row(c, partner_name=c.partner.name, partner_email=c.partner.email),
                "staff": [{"name": s.name, "email": s.email} for s in c.staff.all()],
                "milestones": [row(m) for m in milestones],
                "updates": _update_rows(c.updates, 8),
                "doc_requests": [row(d) for d in doc_reqs],
                "documents": [row(d) for d in list(c.documents.all())],
                "invoices": [row(i) for i in c.invoices.all()],
                "queries": _message_rows(c.messages, 20),
                "alerts": [row(a) for a in c.alerts.all()],
                "progress": _progress(milestones),
                "current_step": row(_current_step(milestones)) if _current_step(milestones) else None,
                "needed_docs": [row(d) for d in doc_reqs if d.status == "needed"],
            }
        )
    return jobs


def _unanswered(messages):
    """Client messages after the last reply from the firm."""
    count = 0
    for m in reversed(messages):
        if m["author_role"] != "client":
            break
        count += 1
    return count


def build_partner_jobs(user):
    jobs = []
    for c in _case_queryset(user):
        milestones = list(c.milestones.all())
        messages = _message_rows(c.messages)
        step = _current_step(milestones)
        jobs.append(
            {
                "case": row(c, client_name=c.client.name, client_email=c.client.email),
                "staff": [{"name": s.name, "email": s.email} for s in c.staff.all()],
                "milestones": [row(m) for m in milestones],
                "updates": _update_rows(c.updates, 10),
                "doc_requests": [row(d) for d in c.doc_requests.all()],
                "documents": _doc_rows(c.documents),
                "queries": messages,
                "drafts": [row(d) for d in list(c.drafts.all())[:10]],
                "pending_drafts": sum(1 for d in c.drafts.all() if d.status == "pending"),
                "invoices": [row(i) for i in c.invoices.all()],
                "communications": [row(cm, staff_name=cm.staff.name) for cm in list(c.communications.all())[:8]],
                "needed_docs": [row(d) for d in c.doc_requests.all() if d.status == "needed"],
                "progress": _progress(milestones),
                "current_step": row(step) if step else None,
                "pending_replies": _unanswered(messages),
            }
        )
    return jobs


def build_staff_jobs(user):
    jobs = []
    for c in _case_queryset(user):
        milestones = list(c.milestones.all())
        updates = _update_rows(c.updates, 12)
        doc_reqs = list(c.doc_requests.all())
        invoices = [row(i) for i in c.invoices.all()]
        queries = _message_rows(c.messages, 8, newest_first=True)
        step = _current_step(milestones)
        jobs.append(
            {
                "case": row(c, client_name=c.client.name, partner_name=c.partner.name),
                "partner": {"id": c.partner.id, "name": c.partner.name, "email": c.partner.email},
                "client": {"name": c.client.name, "email": c.client.email},
                "milestones": [row(m) for m in milestones],
                "updates": updates,
                "partner_updates": [u for u in updates if u["author_role"] == "partner"],
                "doc_requests": [row(d) for d in doc_reqs],
                "needed_docs": [row(d) for d in doc_reqs if d.status == "needed"],
                "documents": _doc_rows(c.documents, 10),
                "queries": queries,
                "client_queries": [q for q in queries if q["author_role"] == "client"],
                "invoices": invoices,
                "due_invoices": [i for i in invoices if i["status"] != "Paid"],
                "due_total": float(sum(i["amount"] for i in invoices if i["status"] == "Pending")),
                "communications": [row(cm, staff_name=cm.staff.name) for cm in list(c.communications.all())[:10]],
                "partner_messages": [
                    row(m, staff_name=m.staff.name) for m in list(c.staff_messages.all())[:10]
                ],
                "progress": _progress(milestones),
                "current_step": row(step) if step else None,
            }
        )
    return jobs


def consultations_for(user):
    qs = Consultation.objects.select_related("case", "client")
    if user.role == User.Role.CLIENT:
        qs = qs.filter(client=user)
    elif user.role == User.Role.PARTNER:
        qs = qs.filter(Q(case__isnull=True) | Q(case__partner=user))
    return [
        row(
            co,
            case_no=co.case.case_no if co.case else None,
            client_name=co.client.name,
        )
        for co in qs.order_by("preferred_date", "preferred_time")
    ]


def pending_drafts_count(user):
    return Draft.objects.filter(case__partner=user, status="pending").count()


def enquiry_rows(limit=30):
    qs = Enquiry.objects.annotate(outreach_count=Count("outreach")).order_by("-id")[:limit]
    return [row(e, outreach_count=e.outreach_count) for e in qs]


def build_ceo_dashboard():
    role_counts = {r["role"]: r["c"] for r in User.objects.filter(is_active=True).values("role").annotate(c=Count("id"))}
    cases = (
        Case.objects.select_related("client", "partner")
        .prefetch_related("milestones", "staff", "invoices")
        .order_by("-id")
    )
    case_rows, status_counts = [], {}
    for c in cases:
        milestones = list(c.milestones.all())
        invoices = list(c.invoices.all())
        status_counts[c.status] = status_counts.get(c.status, 0) + 1
        case_rows.append(
            {
                "case": row(
                    c,
                    client_name=c.client.name,
                    client_email=c.client.email,
                    partner_name=c.partner.name,
                    partner_email=c.partner.email,
                ),
                "progress": _progress(milestones),
                "paid": float(sum(i.amount for i in invoices if i.status == "Paid")),
                "due": float(sum(i.amount for i in invoices if i.status == "Pending")),
                "staff_names": [s.name for s in c.staff.all()],
            }
        )

    invoices = Invoice.objects.select_related("case", "client").prefetch_related("payments").order_by("-id")
    invoice_rows = [
        row(
            i,
            case_no=i.case.case_no if i.case else None,
            case_title=i.case.title if i.case else i.description,
            client_name=i.client.name,
            captured_payment_id=next((p.pk for p in i.payments.all() if p.status == "captured"), None),
        )
        for i in invoices
    ]
    revenue_paid = float(sum(i.amount for i in invoices if i.status == "Paid"))
    revenue_due = float(sum(i.amount for i in invoices if i.status == "Pending"))

    lead_counts = {r["status"]: r["c"] for r in Enquiry.objects.values("status").annotate(c=Count("id"))}
    lead_total = sum(lead_counts.values())
    lead_new = lead_counts.get("new", 0)
    lead_contacted = lead_counts.get("whatsapp_sent", 0)
    lead_converted = lead_counts.get("converted", 0)
    lead_closed = lead_counts.get("closed", 0)
    lead_satisfied = lead_converted + lead_closed
    conversion_rate = round(100.0 * lead_converted / lead_total, 1) if lead_total else 0.0
    satisfaction_rate = round(100.0 * lead_satisfied / lead_total, 1) if lead_total else 0.0

    partners = User.objects.filter(role="partner", is_active=True).annotate(
        case_count=Count("partner_cases", distinct=True),
        pending_drafts=Count("partner_cases__drafts", filter=Q(partner_cases__drafts__status="pending"), distinct=True),
    )
    partner_rows = []
    for p in partners:
        revenue = Invoice.objects.filter(case__partner=p, status="Paid").aggregate(s=Sum("amount"))["s"] or 0
        updates = p.partner_cases.filter(updates__author=p).values("updates").count()
        partner_rows.append(
            {
                "id": p.id,
                "name": p.name,
                "email": p.email,
                "case_count": p.case_count,
                "pending_drafts": p.pending_drafts,
                "revenue": float(revenue),
                "updates_posted": updates,
            }
        )

    staff_rows = [
        {
            "id": s.id,
            "name": s.name,
            "email": s.email,
            "cases_assigned": s.staff_cases.count(),
            "whatsapp_outreach": _outreach_count(s),
            "partner_messages": _staff_message_count(s),
            "client_updates": _update_count(s),
        }
        for s in User.objects.filter(role="staff", is_active=True)
    ]

    from .models import CaseUpdate

    recent_updates = [
        row(u, author_name=u.author.name if u.author else None, author_role=u.author.role if u.author else None, case_no=u.case.case_no)
        for u in CaseUpdate.objects.select_related("author", "case").order_by("-id")[:12]
    ]
    recent_audit = [
        row(a, user_name=a.user.name if a.user else None, user_role=a.user.role if a.user else None)
        for a in AuditLog.objects.select_related("user").order_by("-id")[:20]
    ]
    consultations = [
        row(co, client_name=co.client.name, case_no=co.case.case_no if co.case else None)
        for co in Consultation.objects.select_related("client", "case").order_by("-id")[:10]
    ]
    source_rows = list(Enquiry.objects.values("source_page").annotate(c=Count("id")).order_by("-c"))

    return {
        "role_counts": role_counts,
        "cases": case_rows,
        "status_counts": status_counts,
        "invoices": invoice_rows,
        "revenue_paid": revenue_paid,
        "revenue_due": revenue_due,
        "enquiries": [row(e) for e in Enquiry.objects.order_by("-id")[:40]],
        "lead_total": lead_total,
        "lead_new": lead_new,
        "lead_contacted": lead_contacted,
        "lead_converted": lead_converted,
        "lead_closed": lead_closed,
        "lead_satisfied": lead_satisfied,
        "conversion_rate": conversion_rate,
        "satisfaction_rate": satisfaction_rate,
        "partners": partner_rows,
        "staff": staff_rows,
        "recent_updates": recent_updates,
        "recent_audit": recent_audit,
        "consultations": consultations,
        "drafts_pending": Draft.objects.filter(status="pending").count(),
        "docs_needed": DocRequest.objects.filter(status="needed").count(),
        "overdue_invoices": [
            row(i, client_name=i.client.name)
            for i in invoices
            if i.status == "Pending" and i.due_date and i.due_date < timezone.localdate()
        ],
        "consult_requested": Consultation.objects.filter(status="Requested").count(),
        "avg_progress": int(round(sum(r["progress"] for r in case_rows) / len(case_rows))) if case_rows else 0,
        "chart_case_status": {
            "labels": list(status_counts.keys()) or ["No cases"],
            "data": list(status_counts.values()) or [0],
        },
        "chart_leads": {
            "labels": ["New", "Contacted", "Converted", "Closed"],
            "data": [lead_new, lead_contacted, lead_converted, lead_closed],
        },
        "chart_revenue": {"labels": ["Received", "Outstanding"], "data": [round(revenue_paid), round(revenue_due)]},
        "chart_sources": {
            "labels": [r["source_page"] or "other" for r in source_rows] or ["none"],
            "data": [r["c"] for r in source_rows] or [0],
        },
        "chart_partner_load": {
            "labels": [p["name"].split("—")[0].strip()[:20] for p in partner_rows] or ["None"],
            "cases": [p["case_count"] for p in partner_rows] or [0],
            "revenue": [p["revenue"] for p in partner_rows] or [0],
        },
    }


def _outreach_count(staff_user):
    from apps.leads.models import EnquiryOutreach

    return EnquiryOutreach.objects.filter(staff=staff_user).count()


def _staff_message_count(staff_user):
    from .models import StaffMessage

    return StaffMessage.objects.filter(staff=staff_user).count()


def _update_count(user):
    from .models import CaseUpdate

    return CaseUpdate.objects.filter(author=user).count()


def payable_invoices_for(user):
    """Pending invoices for a client, including service/consultation ones with no case."""
    return [
        row(i, case_no=i.case.case_no if i.case else None, kind_label=i.get_kind_display())
        for i in Invoice.objects.filter(client=user, status=Invoice.Status.PENDING).select_related("case")
    ]
