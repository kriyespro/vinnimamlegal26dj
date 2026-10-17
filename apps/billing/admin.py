from django.contrib import admin

from .models import Invoice, Offering, Payment, RazorpayEvent


@admin.register(Offering)
class OfferingAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "amount", "active")
    list_filter = ("kind", "active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_no", "client", "kind", "amount", "status", "due_date")
    list_filter = ("status", "kind")
    search_fields = ("invoice_no", "client__email")


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(ReadOnlyAdmin):
    list_display = ("razorpay_order_id", "invoice", "amount_paise", "status", "needs_review", "created_at")
    list_filter = ("status", "needs_review")


@admin.register(RazorpayEvent)
class RazorpayEventAdmin(ReadOnlyAdmin):
    list_display = ("event_id", "event_type", "handled", "created_at")
