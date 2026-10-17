from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.catalog.data import STATE_CATALOG

PUBLIC_PAGES = [
    "index", "about", "services", "services-by-state", "pricing", "business-registration", "partnership",
    "msme", "trademark", "contracts", "marriage-certificate", "adoption", "expert-portal", "deadlines",
    "legal-glossary", "faq", "blog", "contact", "portal-usage-policy",
]


class StaticPages(Sitemap):
    changefreq = "monthly"
    priority = 0.7

    def items(self):
        return [(name, None) for name in PUBLIC_PAGES] + [("services-by-state", s["slug"]) for s in STATE_CATALOG]

    def lastmod(self, item):
        """Last time the page's template changed (falls back to None -> omitted)."""
        from datetime import datetime, timezone
        from pathlib import Path

        from django.conf import settings

        name, slug = item
        template = {"index": "index", "services-by-state": "services-by-state"}.get(name, name) + ".html"
        path = Path(settings.BASE_DIR) / "templates" / template
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc) if path.exists() else None

    def location(self, item):
        name, slug = item
        return reverse(name, kwargs={"state_slug": slug}) if slug else reverse(name)
