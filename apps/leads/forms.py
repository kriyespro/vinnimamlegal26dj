import re

from django import forms

from .models import Enquiry


class EnquiryForm(forms.ModelForm):
    # Honeypot: real users leave it empty.
    website = forms.CharField(required=False)

    class Meta:
        model = Enquiry
        fields = ["name", "phone", "email", "city", "service", "message", "extra"]

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        digits = re.sub(r"\D", "", phone)
        if not 7 <= len(digits) <= 15:
            raise forms.ValidationError("Enter a valid phone number.")
        return phone

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("spam")
        return ""
