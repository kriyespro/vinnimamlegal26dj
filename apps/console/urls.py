from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="console"),
    path("users/", views.users_list, name="console_users"),
    path("users/new/", views.user_create, name="console_user_create"),
    path("users/<int:user_id>/", views.user_edit, name="console_user_edit"),
    path("users/<int:user_id>/quick/", views.user_quick, name="console_user_quick"),
    path("users/<int:user_id>/reset/", views.user_reset, name="console_user_reset"),
    path("cases/", views.cases_list, name="console_cases"),
    path("cases/new/", views.case_create, name="console_case_create"),
    path("cases/<int:case_id>/", views.case_edit, name="console_case_edit"),
    path("cases/<int:case_id>/status/", views.case_quick_status, name="console_case_status"),
    path("leads/", views.leads_list, name="console_leads"),
    path("leads/<int:enquiry_id>/status/", views.lead_status, name="console_lead_status"),
    path("billing/", views.billing_overview, name="console_billing"),
    path("billing/offerings/new/", views.offering_create, name="console_offering_create"),
    path("billing/offerings/<int:offering_id>/", views.offering_edit, name="console_offering_edit"),
    path("billing/offerings/<int:offering_id>/toggle/", views.offering_toggle, name="console_offering_toggle"),
    path("billing/payments/<int:payment_id>/reviewed/", views.payment_reviewed, name="console_payment_reviewed"),
    path("audit/", views.audit_list, name="console_audit"),
]
