import secrets
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateStorage(FileSystemStorage):
    """Files are stored outside static/media roots; only an authorised view serves them."""

    def __init__(self):
        super().__init__(location=None)

    @property
    def base_location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self):
        return str(Path(settings.PRIVATE_MEDIA_ROOT).resolve())

    def url(self, name):
        raise ValueError("Private files have no public URL")


def document_path(instance, filename):
    ext = Path(filename).suffix.lower()
    return f"case_{instance.case_id}/{secrets.token_hex(16)}{ext}"


User = settings.AUTH_USER_MODEL


class Case(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "In Progress", "In Progress"
        AWAITING_CLIENT = "Awaiting Client", "Awaiting Client"
        UNDER_REVIEW = "Under Review", "Under Review"
        ON_HOLD = "On Hold", "On Hold"
        COMPLETED = "Completed", "Completed"

    case_no = models.CharField(max_length=30, unique=True)
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    client = models.ForeignKey(User, on_delete=models.PROTECT, related_name="client_cases")
    partner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="partner_cases")
    staff = models.ManyToManyField(User, blank=True, related_name="staff_cases")
    hearing_date = models.DateField(null=True, blank=True)
    billing_note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"], name="case_status"),
        ]
        ordering = ["-id"]

    def __str__(self):
        return f"{self.case_no} — {self.title}"


class Milestone(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In progress"
        DONE = "done", "Done"

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="milestones")
    title = models.CharField(max_length=200)
    detail = models.CharField(max_length=300, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "id"]


class CaseUpdate(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="updates")
    author = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class DocRequest(models.Model):
    class Status(models.TextChoices):
        NEEDED = "needed", "Needed"
        UPLOADED = "uploaded", "Uploaded"
        VERIFIED = "verified", "Verified"

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="doc_requests")
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEEDED)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]


class Document(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="documents")
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    filename = models.CharField(max_length=255)
    file = models.FileField(upload_to=document_path, storage=PrivateStorage(), max_length=200)
    mime = models.CharField(max_length=100)
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class CaseMessage(models.Model):
    """Client ↔ legal team thread on a case (Flask table `queries`)."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class Communication(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="communications")
    staff = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    type = models.CharField(max_length=20)
    note = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class Draft(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="drafts")
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    submitted_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"], name="draft_status"),
        ]
        ordering = ["-id"]


class Conflict(models.Model):
    partner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    prospective_client = models.CharField(max_length=200)
    note = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)


class Incident(models.Model):
    class Kind(models.TextChoices):
        BREACH = "breach", "Breach"
        ESCALATION = "escalation", "Escalation"

    reporter = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    note = models.TextField(max_length=2000)
    case = models.ForeignKey(Case, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class Consultation(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "Requested", "Requested"
        CONFIRMED = "Confirmed", "Confirmed"
        COMPLETED = "Completed", "Completed"
        CANCELLED = "Cancelled", "Cancelled"

    class Mode(models.TextChoices):
        VIDEO = "Video", "Video"
        PHONE = "Phone", "Phone"

    client = models.ForeignKey(User, on_delete=models.PROTECT, related_name="consultations")
    case = models.ForeignKey(Case, null=True, blank=True, on_delete=models.SET_NULL, related_name="consultations")
    practice_area = models.CharField(max_length=80)
    preferred_date = models.DateField()
    preferred_time = models.CharField(max_length=20)
    mode = models.CharField(max_length=6, choices=Mode.choices, default=Mode.VIDEO)
    note = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "preferred_date"], name="consult_status_date"),
        ]
        ordering = ["preferred_date", "preferred_time"]


class ComplianceAlert(models.Model):
    class Status(models.TextChoices):
        UPCOMING = "upcoming", "Upcoming"
        ACTION_NEEDED = "action_needed", "Action needed"
        COMPLETED = "completed", "Completed"

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="alerts")
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=60)
    due_date = models.DateField()
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.UPCOMING)

    class Meta:
        ordering = ["due_date", "id"]


class StaffMessage(models.Model):
    """Staff → partner note on a case."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="staff_messages")
    staff = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    partner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
