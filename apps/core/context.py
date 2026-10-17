from django.conf import settings

from apps.catalog.data import FEATURED_STATES, STATE_CATALOG

from .search import build_search_items


def site_context(request):
    featured_slugs = {s["slug"] for s in FEATURED_STATES}
    from datetime import date

    return {
        "now_year": date.today().year,
        "site": {
            "email": settings.SITE_EMAIL,
            "phone": settings.SITE_PHONE,
            "phone_e164": "+" + "".join(ch for ch in settings.SITE_WHATSAPP if ch.isdigit()),
            "whatsapp": "".join(ch for ch in settings.SITE_WHATSAPP if ch.isdigit()),
            "social": settings.SOCIAL_LINKS,
        },
        "featured_states": FEATURED_STATES,
        "more_states": [s for s in STATE_CATALOG if s["slug"] not in featured_slugs],
        "site_search_items": build_search_items(),
    }
