from django.urls import path

from . import views

urlpatterns = [
    path("billing/buy/<slug:slug>", views.buy, name="billing_buy"),
    path("billing/invoices/<int:invoice_id>", views.invoice_detail, name="billing_invoice"),
    path("billing/invoices/<int:invoice_id>/pay", views.invoice_pay, name="billing_pay"),
    path("billing/verify", views.checkout_verify, name="billing_verify"),
    path("billing/webhook/razorpay", views.webhook, name="billing_webhook"),
    path("billing/payments/<int:payment_id>/refund", views.refund, name="billing_refund"),
]
