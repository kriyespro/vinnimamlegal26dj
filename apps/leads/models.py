from django.db import models


class Enquiry(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        WHATSAPP_SENT = "whatsapp_sent", "WhatsApp sent"
        CONVERTED = "converted", "Converted"
        CLOSED = "closed", "Closed"

    source_page = models.CharField(max_length=100, default="unknown")
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    city = models.CharField(max_length=80, blank=True)
    service = models.CharField(max_length=120, blank=True)
    message = models.TextField(blank=True, max_length=2000)
    extra = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "-created_at"], name="enq_status_created"),
        ]
        ordering = ["-created_at"]
        verbose_name_plural = "enquiries"

    def __str__(self):
        return f"{self.name} ({self.phone}) — {self.source_page}"


class EnquiryOutreach(models.Model):
    enquiry = models.ForeignKey(Enquiry, on_delete=models.CASCADE, related_name="outreach")
    staff = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    channel = models.CharField(max_length=20, default="whatsapp")
    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
