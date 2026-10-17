from django.contrib import admin

from .models import Enquiry


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "service", "source_page", "status", "created_at")
    list_filter = ("status", "source_page")
    search_fields = ("name", "phone", "email")
