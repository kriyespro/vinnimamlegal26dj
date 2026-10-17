from django.urls import path

from . import views

urlpatterns = [
    path("portal/dashboard", views.dashboard, name="portal_dashboard"),
    path("portal/consultations", views.consultation_book, name="portal_consultation_book"),
    path("portal/consultations/<int:consultation_id>", views.consultation_status, name="portal_consultation_status"),
    path("portal/queries", views.client_query, name="portal_queries"),
    path("portal/messages", views.message_reply, name="portal_message_reply"),
    path("portal/documents", views.document_upload, name="portal_documents_upload"),
    path("portal/documents/<int:doc_id>", views.document_download, name="portal_document_download"),
    path("portal/cases/<int:case_id>/updates", views.case_update, name="portal_case_update"),
    path("portal/cases/<int:case_id>/milestones", views.milestone_add, name="portal_milestone_add"),
    path("portal/milestones/<int:milestone_id>", views.milestone_update, name="portal_milestone_update"),
    path("portal/cases/<int:case_id>/document-requests", views.document_request_add, name="portal_document_request"),
    path("portal/document-requests/<int:request_id>", views.document_request_status, name="portal_document_request_status"),
    path("portal/cases/<int:case_id>/status", views.case_status, name="portal_case_status"),
    path("portal/cases/<int:case_id>/invoices", views.invoice_create, name="portal_invoice_create"),
    path("portal/drafts/<int:draft_id>/approve", views.draft_approve, name="portal_draft_approve"),
    path("portal/drafts/<int:draft_id>/reject", views.draft_reject, name="portal_draft_reject"),
    path("portal/conflicts", views.conflict_disclose, name="portal_conflicts"),
    path("portal/comms", views.comms_log, name="portal_comms"),
    path("portal/enquiries/<int:enquiry_id>/whatsapp", views.enquiry_whatsapp, name="portal_enquiry_whatsapp"),
    path("portal/enquiries/<int:enquiry_id>/status", views.enquiry_status, name="portal_enquiry_status"),
    path("portal/partner-messages", views.partner_message, name="portal_partner_message"),
    path("portal/escalate", views.escalate, name="portal_escalate"),
    path("portal/breach", views.breach_report, name="portal_breach"),
]
