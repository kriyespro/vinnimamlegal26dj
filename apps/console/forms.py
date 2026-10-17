from django import forms
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import Offering
from apps.portal.models import Case

INPUT = "db-in"
CHECK = "rounded border-slate-300 text-royal focus:ring-royal h-4 w-4"


class StyledForm(forms.ModelForm):
    """Adds the site's Tailwind classes to every widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = CHECK
            elif isinstance(widget, forms.SelectMultiple):
                widget.attrs["class"] = INPUT + " min-h-[7rem]"
            else:
                widget.attrs["class"] = INPUT


class UserCreateForm(StyledForm):
    class Meta:
        model = User
        fields = ["name", "email", "role"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email


class UserEditForm(StyledForm):
    class Meta:
        model = User
        fields = ["name", "role", "is_active"]
        labels = {"is_active": "Account active (can sign in)"}


class CaseForm(StyledForm):
    hearing_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    class Meta:
        model = Case
        fields = ["title", "case_no", "client", "partner", "status", "hearing_date", "staff", "billing_note"]
        help_texts = {"case_no": "Leave blank to auto-number (VL-YYYY-NNNN)."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["case_no"].required = False
        self.fields["client"].queryset = User.objects.filter(role=User.Role.CLIENT, is_active=True).order_by("name")
        self.fields["partner"].queryset = User.objects.filter(role=User.Role.PARTNER, is_active=True).order_by("name")
        self.fields["staff"].queryset = User.objects.filter(role=User.Role.STAFF, is_active=True).order_by("name")
        self.fields["staff"].required = False

    def clean_case_no(self):
        value = (self.cleaned_data.get("case_no") or "").strip()
        if value and Case.objects.filter(case_no__iexact=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This case number is already used.")
        return value

    def save(self, commit=True):
        case = super().save(commit=False)
        if not case.case_no:
            case.case_no = f"TMP-{timezone.now().timestamp()}"
        case.save()
        self.save_m2m()
        if case.case_no.startswith("TMP-"):
            case.case_no = f"VL-{timezone.localdate().year}-{case.pk:04d}"
            case.save(update_fields=["case_no"])
        return case


class OfferingForm(StyledForm):
    class Meta:
        model = Offering
        fields = ["name", "slug", "kind", "amount", "description", "active"]
        help_texts = {
            "slug": "Pricing-page keys: pvt-ltd, llp, trademark, msme, partnership, marriage-certificate.",
            "amount": "INR charged to the client (professional fee; government/stamp fees excluded).",
        }
