"""Structured data (JSON-LD) helpers. Output is escaped so it is safe inside <script>."""
import json

from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse

SERVICE_PAGES = {
    "business-registration": ("Business registration", "Private Limited, LLP, OPC and proprietorship registration with expert CA/CS support."),
    "partnership": ("Partnership firm registration", "Partnership deed drafting, stamp duty guidance and Registrar of Firms filing."),
    "msme": ("MSME / Udyam registration", "Udyam (MSME) certificate registration for micro, small and medium enterprises."),
    "trademark": ("Trademark registration", "Trademark search, filing, objection replies and renewals across all 45 classes."),
    "contracts": ("Contract and agreement drafting", "NDAs, employment, shareholder and vendor agreements, MoUs and more."),
    "marriage-certificate": ("Marriage certificate registration", "Registration support under the Hindu Marriage Act and Special Marriage Act."),
    "adoption": ("Adoption legal assistance", "Adoption documentation, deed drafting and court petition guidance."),
}

FAQS = [
    ("What services does VinnitaLegal offer?", "Business registration (Pvt Ltd, LLP, OPC, partnership), trademark, MSME/Udyam, contracts, compliance deadlines, marriage certificate, adoption documentation and expert consultations."),
    ("Is the process fully online?", "Most business filings are 100% online. Some state partnership filings, marriage registration appointments or court steps may need physical presence — we guide you either way."),
    ("Are government fees included in the price?", "Listed prices are VinnitaLegal professional fees unless marked all-inclusive. Stamp duty, MCA and registrar fees are usually extra and shown transparently before you pay."),
    ("How do I track my application?", "Sign in to the client portal to see every step, upload documents, message your legal team and pay invoices. You can also reach us at {email} or {phone}."),
    ("Do you help with personal legal work?", "Yes — marriage certificate registration, adoption documentation assistance, wills and related family-law drafting via our Expert Portal."),
    ("How do I pay?", "Pay securely online by UPI, card or netbanking from your client dashboard. The amount is always set by VinnitaLegal on your invoice."),
]


def faqs():
    return [(q, a.format(email=settings.SITE_EMAIL, phone=settings.SITE_PHONE)) for q, a in FAQS]


def dumps(obj):
    return (
        json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    )


def _abs(request, path):
    return request.build_absolute_uri(path)


def organization(request):
    org = {
        "@context": "https://schema.org",
        "@type": ["LegalService", "Organization"],
        "@id": _abs(request, "/#organization"),
        "name": "VinnitaLegal",
        "url": _abs(request, "/"),
        "logo": _abs(request, static("img/icon-512.png")),
        "image": _abs(request, static("img/og-default.jpg")),
        "description": "Legal and compliance services in Gujarat: business registration, trademark, contracts, MSME and marriage certificate support.",
        "telephone": settings.SITE_PHONE,
        "email": settings.SITE_EMAIL,
        "areaServed": {"@type": "AdministrativeArea", "name": "Gujarat, India"},
        "founder": {"@type": "Person", "name": "Vinnita Maheshwari"},
        "contactPoint": [{"@type": "ContactPoint", "contactType": "customer support", "telephone": settings.SITE_PHONE,
                          "email": settings.SITE_EMAIL, "areaServed": "IN", "availableLanguage": ["English"],
                          "hoursAvailable": {"@type": "OpeningHoursSpecification", "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"], "opens": "09:00", "closes": "19:00"}}],
    }
    same_as = [u for u in settings.SOCIAL_LINKS.values() if u]
    if same_as:
        org["sameAs"] = same_as
    return org


def website(request):
    return {
        "@context": "https://schema.org", "@type": "WebSite", "name": "VinnitaLegal", "url": _abs(request, "/"),
        "inLanguage": "en-IN", "publisher": {"@id": _abs(request, "/#organization")},
        "potentialAction": {"@type": "SearchAction", "target": _abs(request, reverse("site_search")) + "?q={search_term_string}", "query-input": "required name=search_term_string"},
    }


def faq_page():
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs()]}


def service(request, url_name):
    name, desc = SERVICE_PAGES[url_name]
    return {"@context": "https://schema.org", "@type": "Service", "name": name, "description": desc,
            "serviceType": name, "url": _abs(request, reverse(url_name)),
            "provider": {"@id": _abs(request, "/#organization")}, "areaServed": {"@type": "Country", "name": "India"}}


def for_page(request, url_name):
    """JSON-LD documents (as safe strings) for a named page."""
    docs = []
    if url_name == "index":
        docs = [organization(request), website(request)]
    elif url_name == "faq":
        docs = [faq_page()]
    elif url_name in SERVICE_PAGES:
        docs = [service(request, url_name)]
    return [dumps(d) for d in docs]
