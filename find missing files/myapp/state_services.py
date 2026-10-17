"""State-wise legal services catalog for Vinnita Legal Consultancy."""

from __future__ import annotations

SERVICE_CATALOG: list[dict] = [
    {
        "slug": "business-registration",
        "name": "Company Registration",
        "desc": "Pvt Ltd, LLP, OPC & Proprietorship",
        "endpoint": "business-registration",
        "icon": "building",
    },
    {
        "slug": "partnership",
        "name": "Partnership Firm",
        "desc": "Deed drafting & Registrar filing",
        "endpoint": "partnership",
        "icon": "users",
    },
    {
        "slug": "msme",
        "name": "MSME / Udyam",
        "desc": "Udyam registration certificate",
        "endpoint": "msme",
        "icon": "shield",
    },
    {
        "slug": "gst-compliance",
        "name": "GST Registration & Filing",
        "desc": "New GSTIN, returns & compliance",
        "endpoint": "gst-compliance",
        "icon": "receipt",
    },
    {
        "slug": "trademark",
        "name": "Trademark Registration",
        "desc": "Search, file & protect your brand",
        "endpoint": "trademark",
        "icon": "badge",
    },
    {
        "slug": "contracts",
        "name": "Legal Contracts",
        "desc": "NDA, SHA, employment & vendor agreements",
        "endpoint": "contracts",
        "icon": "file",
    },
    {
        "slug": "marriage-certificate",
        "name": "Marriage Certificate",
        "desc": "Registration under Special / Hindu Marriage Act",
        "endpoint": "marriage-certificate",
        "icon": "heart",
    },
    {
        "slug": "deadlines",
        "name": "Compliance Deadlines",
        "desc": "ROC, GST, TDS & renewal reminders",
        "endpoint": "deadlines",
        "icon": "calendar",
    },
]

STATE_CATALOG: list[dict] = [
    {
        "slug": "delhi",
        "name": "Delhi NCR",
        "region": "North",
        "cities": "New Delhi · Noida · Gurgaon · Faridabad",
        "featured": True,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "mumbai",
        "name": "Mumbai & Maharashtra",
        "region": "West",
        "cities": "Mumbai · Pune · Nagpur · Thane",
        "featured": True,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "gujarat",
        "name": "Gujarat",
        "region": "West",
        "cities": "Ahmedabad · Surat · Vadodara · Rajkot",
        "featured": True,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "uttar-pradesh",
        "name": "Uttar Pradesh",
        "region": "North",
        "cities": "Lucknow · Noida · Kanpur · Ghaziabad · Varanasi",
        "featured": True,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "bihar",
        "name": "Bihar",
        "region": "East",
        "cities": "Patna · Gaya · Muzaffarpur · Bhagalpur",
        "featured": True,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "karnataka",
        "name": "Karnataka",
        "region": "South",
        "cities": "Bangalore · Mysore · Mangalore · Hubli",
        "featured": True,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "tamil-nadu",
        "name": "Tamil Nadu",
        "region": "South",
        "cities": "Chennai · Coimbatore · Madurai · Trichy",
        "featured": True,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "west-bengal",
        "name": "West Bengal",
        "region": "East",
        "cities": "Kolkata · Howrah · Siliguri · Durgapur",
        "featured": False,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "rajasthan",
        "name": "Rajasthan",
        "region": "North",
        "cities": "Jaipur · Jodhpur · Udaipur · Kota",
        "featured": False,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "telangana",
        "name": "Telangana",
        "region": "South",
        "cities": "Hyderabad · Warangal · Nizamabad",
        "featured": False,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "punjab",
        "name": "Punjab",
        "region": "North",
        "cities": "Chandigarh · Ludhiana · Amritsar · Jalandhar",
        "featured": False,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "haryana",
        "name": "Haryana",
        "region": "North",
        "cities": "Gurgaon · Faridabad · Panipat · Ambala",
        "featured": False,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "madhya-pradesh",
        "name": "Madhya Pradesh",
        "region": "Central",
        "cities": "Bhopal · Indore · Gwalior · Jabalpur",
        "featured": False,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "kerala",
        "name": "Kerala",
        "region": "South",
        "cities": "Kochi · Thiruvananthapuram · Kozhikode · Thrissur",
        "featured": False,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "andhra-pradesh",
        "name": "Andhra Pradesh",
        "region": "South",
        "cities": "Visakhapatnam · Vijayawada · Guntur · Tirupati",
        "featured": False,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "odisha",
        "name": "Odisha",
        "region": "East",
        "cities": "Bhubaneswar · Cuttack · Rourkela · Puri",
        "featured": False,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "jharkhand",
        "name": "Jharkhand",
        "region": "East",
        "cities": "Ranchi · Jamshedpur · Dhanbad · Bokaro",
        "featured": False,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "assam",
        "name": "Assam & North-East",
        "region": "East",
        "cities": "Guwahati · Shillong · Imphal · Agartala",
        "featured": False,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
    {
        "slug": "chhattisgarh",
        "name": "Chhattisgarh",
        "region": "Central",
        "cities": "Raipur · Bilaspur · Durg · Bhilai",
        "featured": False,
        "services": [
            "business-registration",
            "partnership",
            "msme",
            "gst-compliance",
            "trademark",
            "contracts",
            "marriage-certificate",
            "deadlines",
        ],
    },
]

# Visibility filtering: show only Gujarat + legal-document services
# (Hides GST/accounting service + other states from the UI.)
VISIBLE_STATE_SLUGS = {"gujarat"}
VISIBLE_SERVICE_SLUGS = {
    "business-registration",
    "partnership",
    "msme",
    "trademark",
    "contracts",
    "marriage-certificate",
}

SERVICE_CATALOG = [s for s in SERVICE_CATALOG if s["slug"] in VISIBLE_SERVICE_SLUGS]
STATE_CATALOG = [s for s in STATE_CATALOG if s["slug"] in VISIBLE_STATE_SLUGS]
for _state in STATE_CATALOG:
    _state["services"] = [slug for slug in _state["services"] if slug in VISIBLE_SERVICE_SLUGS]

# Build the region filter buttons from the visible states only.
REGIONS = ["All"] + sorted({s["region"] for s in STATE_CATALOG})

SERVICE_BY_SLUG = {s["slug"]: s for s in SERVICE_CATALOG}
STATE_BY_SLUG = {s["slug"]: s for s in STATE_CATALOG}
FEATURED_STATES = [s for s in STATE_CATALOG if s.get("featured")]


def services_for_state(state_slug: str) -> list[dict]:
    state = STATE_BY_SLUG.get(state_slug)
    if not state:
        return []
    return [SERVICE_BY_SLUG[slug] for slug in state["services"] if slug in SERVICE_BY_SLUG]


def states_in_region(region: str) -> list[dict]:
    if region == "All":
        return STATE_CATALOG
    return [s for s in STATE_CATALOG if s["region"] == region]
