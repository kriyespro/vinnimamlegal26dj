from django.contrib.sitemaps.views import sitemap
from django.urls import path

from . import views
from .sitemaps import StaticPages

PAGES = [
    ("", "index", "index.html"),
    ("about", "about", "about.html"),
    ("adoption", "adoption", "adoption.html"),
    ("blog", "blog", "blog.html"),
    ("business-registration", "business-registration", "business-registration.html"),
    ("contact", "contact", "contact.html"),
    ("contracts", "contracts", "contracts.html"),
    ("deadlines", "deadlines", "deadlines.html"),
    ("expert-portal", "expert-portal", "expert-portal.html"),
    ("faq", "faq", "faq.html"),
    ("legal-glossary", "legal-glossary", "legal-glossary.html"),
    ("marriage-certificate", "marriage-certificate", "marriage-certificate.html"),
    ("msme", "msme", "msme.html"),
    ("partnership", "partnership", "partnership.html"),
    ("portal-usage-policy", "portal-usage-policy", "portal-usage-policy.html"),
    ("services", "services", "services.html"),
    ("trademark", "trademark", "trademark.html"),
]

urlpatterns = [
    path("pricing", views.pricing, name="pricing"),
] + [path(route, views.page(tpl, name), name=name) for route, name, tpl in PAGES] + [
    path("robots.txt", views.robots_txt, name="robots"),
    path("healthz", views.healthz, name="healthz"),
    path(".well-known/security.txt", views.security_txt, name="security_txt"),
    path("sitemap.xml", sitemap, {"sitemaps": {"pages": StaticPages}}, name="sitemap"),
    path("search", views.site_search, name="site_search"),
    path("gst-compliance", views.gst_compliance, name="gst-compliance"),
    path("services-by-state", views.services_by_state, name="services-by-state"),
    path("services-by-state/<slug:state_slug>", views.services_by_state, name="services-by-state"),
]
