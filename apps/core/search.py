from functools import lru_cache

from django.urls import reverse


def _u(name, **kwargs):
    return reverse(name, kwargs=kwargs or None)


@lru_cache(maxsize=1)
def _cached_items():
    return tuple(_build())


def build_search_items():
    return list(_cached_items())


def _build():
    items = [
        {
            "title": "Client Portal",
            "blurb": "Login to track cases, documents & payments",
            "keywords": "portal login signin sign in client dashboard account access my cases",
            "url": _u("portal"),
            "portal": True,
        },
        {
            "title": "Create client account",
            "blurb": "Sign up for a new client portal account",
            "keywords": "register signup sign up create account new client",
            "url": _u("portal"),
            "portal": True,
        },
        {
            "title": "Business Registration",
            "blurb": "Pvt Ltd, LLP, OPC, Proprietorship",
            "keywords": "company registration incorporation spice",
            "url": _u("business-registration"),
        },
        {
            "title": "Trademark Registration",
            "blurb": "Search, file and protect your brand",
            "keywords": "trademark brand ip tm",
            "url": _u("trademark"),
        },
        {
            "title": "Partnership Firm",
            "blurb": "Deed drafting and registrar filing",
            "keywords": "partnership firm deed",
            "url": _u("partnership"),
        },
        {
            "title": "MSME / Udyam",
            "blurb": "Udyam certificate and benefits",
            "keywords": "msme udyam udyog",
            "url": _u("msme"),
        },
        {
            "title": "Legal Contracts",
            "blurb": "NDA, MoU, employment & SHA drafting",
            "keywords": "contracts nda documents drafting",
            "url": _u("contracts"),
        },
        {
            "title": "Marriage Certificate",
            "blurb": "Registration assistance in Gujarat",
            "keywords": "marriage certificate wedding",
            "url": _u("marriage-certificate"),
        },
        {
            "title": "All Services",
            "blurb": "Browse legal document services",
            "keywords": "services catalog list",
            "url": _u("services"),
        },
        {
            "title": "Services by State — Gujarat",
            "blurb": "Local filing support in Gujarat",
            "keywords": "gujarat state ahmedabad",
            "url": _u("services-by-state", state_slug="gujarat"),
        },
        {
            "title": "Pricing",
            "blurb": "Transparent professional fees",
            "keywords": "pricing cost fees package",
            "url": _u("pricing"),
        },
        {
            "title": "Contact / Consultation",
            "blurb": "Talk to an expert — free consultation",
            "keywords": "contact enquiry consult help phone",
            "url": _u("contact"),
        },
        {
            "title": "About VinnitaLegal",
            "blurb": "Founded by Vinnita Maheshwari",
            "keywords": "about founder vinnita",
            "url": _u("about"),
        },
        {
            "title": "FAQ",
            "blurb": "Common questions answered",
            "keywords": "faq help questions",
            "url": _u("faq"),
        },
        {
            "title": "Deadline Calendar",
            "blurb": "MCA/ROC filing dates",
            "keywords": "deadlines calendar roc mca compliance",
            "url": _u("deadlines"),
        },
        {
            "title": "Expert Portal",
            "blurb": "CA, CS and lawyer matching",
            "keywords": "expert lawyer ca cs advocate",
            "url": _u("expert-portal"),
        },
        {
            "title": "Blog & Resources",
            "blurb": "Guides and legal updates",
            "keywords": "blog resources articles guides",
            "url": _u("blog"),
        },
        {
            "title": "Portal Usage Policy",
            "blurb": "Rules for portal access",
            "keywords": "policy terms portal usage",
            "url": _u("portal-usage-policy"),
        },
    ]
    return items


def search(items, q):
    q_l = q.strip().lower()
    if not q_l:
        return [i for i in items if i.get("portal")][:1] + [i for i in items if not i.get("portal")][:8]
    results = []
    for item in items:
        hay = f"{item['title']} {item.get('blurb', '')} {item.get('keywords', '')}".lower()
        score = 0
        if item.get("portal") and any(t in q_l for t in ("portal", "login", "dashboard", "sign", "account", "client")):
            score += 100
        if item["title"].lower().startswith(q_l):
            score += 50
        if q_l in item["title"].lower():
            score += 30
        if q_l in hay:
            score += 10
        for t in q_l.split():
            if t in hay:
                score += 5
        if score:
            results.append({**item, "score": score})
    results.sort(key=lambda r: (-r["score"], 0 if r.get("portal") else 1))
    return results
