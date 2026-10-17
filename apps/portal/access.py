"""Object-level access control. Every case-scoped read/write goes through here."""
from django.shortcuts import get_object_or_404

from apps.accounts.models import User

from .models import Case


def cases_for(user):
    """Cases this user may see. CEO has org-wide read access."""
    if user.role == User.Role.CLIENT:
        return Case.objects.filter(client=user)
    if user.role == User.Role.PARTNER:
        return Case.objects.filter(partner=user)
    if user.role == User.Role.STAFF:
        return Case.objects.filter(staff=user)
    if user.role == User.Role.CEO:
        return Case.objects.all()
    return Case.objects.none()


def get_case(user, case_id):
    """404 (never 403) for cases the user cannot access, so IDs can't be probed."""
    return get_object_or_404(cases_for(user), pk=case_id)
