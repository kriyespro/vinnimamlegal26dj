from django.contrib import admin

from . import models


class MilestoneInline(admin.TabularInline):
    model = models.Milestone
    extra = 0


class DocRequestInline(admin.TabularInline):
    model = models.DocRequest
    extra = 0


@admin.register(models.Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("case_no", "title", "status", "client", "partner")
    list_filter = ("status",)
    search_fields = ("case_no", "title", "client__email")
    filter_horizontal = ("staff",)
    inlines = [MilestoneInline, DocRequestInline]


for model in (
    models.CaseUpdate,
    models.Document,
    models.CaseMessage,
    models.Communication,
    models.Draft,
    models.Conflict,
    models.Incident,
    models.Consultation,
    models.ComplianceAlert,
    models.StaffMessage,
):
    admin.site.register(model)
