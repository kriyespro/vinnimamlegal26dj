"""Vinnita Legal Consultancy Flask app — marketing site + portal backend."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from auth import current_user, login_required, role_required
from db import (
    UPLOAD_DIR,
    audit,
    build_ceo_dashboard,
    build_client_jobs,
    build_partner_jobs,
    build_staff_jobs,
    cases_for_user,
    create_client_user,
    enquiries_for_staff,
    ensure_ceo_user,
    ensure_client_dashboard_seed,
    ensure_demo_documents,
    ensure_staff_dashboard_seed,
    get_db,
    get_user_by_email,
    init_schema,
    save_enquiry,
    seed_if_empty,
    update_user_password,
    user_can_access_case,
    ensure_document_file,
    whatsapp_url,
)
from state_services import (
    FEATURED_STATES,
    REGIONS,
    SERVICE_CATALOG,
    STATE_CATALOG,
    services_for_state,
    states_in_region,
)

BASE_DIR = Path(__file__).resolve().parent
MAX_UPLOAD = 10 * 1024 * 1024
ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or "vinnita-dev-secret-change-me"
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD + 1024


@app.context_processor
def inject_state_menu():
    featured = FEATURED_STATES
    featured_slugs = {s["slug"] for s in featured}
    # Site-wide search catalog (portal first for client access)
    site_search_items = [
        {
            "title": "Client Portal",
            "blurb": "Login to track cases, documents & payments",
            "keywords": "portal login signin sign in client dashboard account access my cases",
            "url": url_for("portal"),
            "portal": True,
        },
        {
            "title": "Create client account",
            "blurb": "Sign up for a new client portal account",
            "keywords": "register signup sign up create account new client",
            "url": url_for("portal"),
            "portal": True,
        },
        {
            "title": "Business Registration",
            "blurb": "Pvt Ltd, LLP, OPC, Proprietorship",
            "keywords": "company registration incorporation spice",
            "url": url_for("business-registration"),
        },
        {
            "title": "Trademark Registration",
            "blurb": "Search, file and protect your brand",
            "keywords": "trademark brand ip tm",
            "url": url_for("trademark"),
        },
        {
            "title": "Partnership Firm",
            "blurb": "Deed drafting and registrar filing",
            "keywords": "partnership firm deed",
            "url": url_for("partnership"),
        },
        {
            "title": "MSME / Udyam",
            "blurb": "Udyam certificate and benefits",
            "keywords": "msme udyam udyog",
            "url": url_for("msme"),
        },
        {
            "title": "Legal Contracts",
            "blurb": "NDA, MoU, employment & SHA drafting",
            "keywords": "contracts nda documents drafting",
            "url": url_for("contracts"),
        },
        {
            "title": "Marriage Certificate",
            "blurb": "Registration assistance in Gujarat",
            "keywords": "marriage certificate wedding",
            "url": url_for("marriage-certificate"),
        },
        {
            "title": "All Services",
            "blurb": "Browse legal document services",
            "keywords": "services catalog list",
            "url": url_for("services"),
        },
        {
            "title": "Services by State — Gujarat",
            "blurb": "Local filing support in Gujarat",
            "keywords": "gujarat state ahmedabad",
            "url": url_for("services-by-state", state_slug="gujarat"),
        },
        {
            "title": "Pricing",
            "blurb": "Transparent professional fees",
            "keywords": "pricing cost fees package",
            "url": url_for("pricing"),
        },
        {
            "title": "Contact / Consultation",
            "blurb": "Talk to an expert — free consultation",
            "keywords": "contact enquiry consult help phone",
            "url": url_for("contact"),
        },
        {
            "title": "About Vinnita Legal Consultancy",
            "blurb": "Founded by Vinnita Maheshwari",
            "keywords": "about founder vinnita",
            "url": url_for("about"),
        },
        {
            "title": "FAQ",
            "blurb": "Common questions answered",
            "keywords": "faq help questions",
            "url": url_for("faq"),
        },
        {
            "title": "Deadline Calendar",
            "blurb": "MCA/ROC filing dates",
            "keywords": "deadlines calendar roc mca compliance",
            "url": url_for("deadlines"),
        },
        {
            "title": "Expert Portal",
            "blurb": "CA, CS and lawyer matching",
            "keywords": "expert lawyer ca cs advocate",
            "url": url_for("expert-portal"),
        },
        {
            "title": "Blog & Resources",
            "blurb": "Guides and legal updates",
            "keywords": "blog resources articles guides",
            "url": url_for("blog"),
        },
        {
            "title": "Portal Usage Policy",
            "blurb": "Rules for portal access",
            "keywords": "policy terms portal usage",
            "url": url_for("portal-usage-policy"),
        },
    ]
    return {
        "featured_states": featured,
        "more_states": [s for s in STATE_CATALOG if s["slug"] not in featured_slugs],
        "site_search_items": site_search_items,
    }


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _portal_redirect(
    user,
    *,
    tab: str | None = None,
    case_id: int | str | None = None,
    view: str | None = None,
    panel: str | None = None,
):
    """Return to the correct dashboard after an action."""
    if user["role"] == "partner":
        kwargs: dict[str, str | int] = {}
        rc = request.form.get("redirect_case") or case_id
        rt = request.form.get("redirect_tab") or tab
        if rc:
            kwargs["case"] = int(rc)
        if rt:
            kwargs["tab"] = rt
        return redirect(url_for("portal_dashboard", **kwargs))
    if user["role"] == "staff":
        kwargs: dict[str, str | int] = {}
        rp = request.form.get("redirect_panel") or panel
        rc = request.form.get("redirect_case") or case_id
        rt = request.form.get("redirect_tab") or tab
        if not rp and rc:
            rp = "cases"
        if rp:
            kwargs["panel"] = rp
        if rc:
            kwargs["case"] = int(rc)
        if rt:
            kwargs["tab"] = rt
        return redirect(url_for("portal_dashboard", **kwargs))
    kwargs = {}
    if view:
        kwargs["view"] = view
    return redirect(url_for("portal_dashboard", **kwargs))


def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


# ----- Marketing pages -----

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search")
def site_search():
    """Marketing site search — highlights Client Portal when relevant."""
    q = (request.args.get("q") or "").strip()
    q_l = q.lower()
    items = inject_state_menu()["site_search_items"]
    results = []
    if q_l:
        for item in items:
            hay = f"{item['title']} {item.get('blurb', '')} {item.get('keywords', '')}".lower()
            score = 0
            if item.get("portal") and any(
                t in q_l
                for t in ("portal", "login", "dashboard", "sign", "account", "client")
            ):
                score += 100
            if item["title"].lower().startswith(q_l):
                score += 50
            if q_l in item["title"].lower():
                score += 30
            if q_l in hay:
                score += 10
            for t in q_l.split():
                if t and t in hay:
                    score += 5
            if score:
                results.append({**item, "score": score})
        results.sort(key=lambda r: (-r["score"], 0 if r.get("portal") else 1))
    else:
        results = [i for i in items if i.get("portal")][:1] + [
            i for i in items if not i.get("portal")
        ][:8]

    return render_template("search.html", q=q, results=results)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/adoption")
def adoption():
    return render_template("adoption.html")


@app.route("/blog")
def blog():
    return render_template("blog.html")


@app.route("/business-registration", endpoint="business-registration")
def business_registration():
    return render_template("business-registration.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/enquire", methods=["POST"])
def enquire():
    """Public service enquiry forms (contact + service page hero panels)."""
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    email = (request.form.get("email") or "").strip()
    city = (request.form.get("city") or "").strip()
    service = (request.form.get("service") or "").strip()
    message = (request.form.get("message") or "").strip()
    source = (request.form.get("source") or "unknown").strip()
    extra = (request.form.get("extra") or "").strip()
    next_url = (request.form.get("next") or "").strip() or url_for("contact")
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = url_for("contact")

    if not name or not phone:
        flash("Please enter your name and phone number.", "error")
        return redirect(next_url)

    eid = save_enquiry(
        source_page=source,
        name=name,
        phone=phone,
        email=email,
        city=city,
        service=service,
        message=message,
        extra=extra,
    )
    audit(None, "enquiry_submitted", f"{source}:{eid}")
    flash(
        "Request received! Our expert will call you within 30 minutes during business hours.",
        "success",
    )
    return redirect(next_url)


@app.route("/contracts")
def contracts():
    return render_template("contracts.html")


@app.route("/deadlines")
def deadlines():
    return render_template("deadlines.html")


@app.route("/expert-portal", endpoint="expert-portal")
def expert_portal():
    return render_template("expert-portal.html")


@app.route("/faq")
def faq():
    return render_template("faq.html")


@app.route("/gst-compliance", endpoint="gst-compliance")
def gst_compliance():
    # GST / accounts service is hidden — send visitors to legal services.
    return redirect(url_for("services"))


@app.route("/legal-glossary", endpoint="legal-glossary")
def legal_glossary():
    return render_template("legal-glossary.html")


@app.route("/marriage-certificate", endpoint="marriage-certificate")
def marriage_certificate():
    return render_template("marriage-certificate.html")


@app.route("/msme")
def msme():
    return render_template("msme.html")


@app.route("/partnership")
def partnership():
    return render_template("partnership.html")


@app.route("/portal-usage-policy", endpoint="portal-usage-policy")
def portal_usage_policy():
    return render_template("portal-usage-policy.html")


@app.route("/pricing")
def pricing():
    return render_template("pricing.html")


@app.route("/services")
def services():
    return render_template("services.html")


@app.route("/trademark")
def trademark():
    return render_template("trademark.html")


@app.route("/services-by-state", defaults={"state_slug": None}, endpoint="services-by-state")
@app.route("/services-by-state/<state_slug>", endpoint="services-by-state")
def services_by_state(state_slug: str | None = None):
    active = None
    state_services_list: list[dict] = []
    if state_slug:
        active = next((s for s in STATE_CATALOG if s["slug"] == state_slug), None)
        if not active:
            abort(404)
        state_services_list = services_for_state(state_slug)
    return render_template(
        "services-by-state.html",
        states=STATE_CATALOG,
        regions=REGIONS,
        active_state=active,
        state_services=state_services_list,
        all_services=SERVICE_CATALOG,
        featured_states=FEATURED_STATES,
    )


# ----- Portal auth -----

@app.route("/portal", methods=["GET", "POST"])
def portal():
    user = current_user()
    if user and session.get("policy_accepted"):
        return redirect(url_for("portal_dashboard"))

    if request.method == "GET":
        if request.args.get("restart") == "1":
            session.pop("reset_user_id", None)
            session.pop("reset_code_hash", None)
            session.pop("demo_reset_code", None)
            session.pop("reset_email", None)
            return redirect(url_for("portal", mode="forgot"))
        return render_template(
            "portal.html",
            reset_pending=bool(session.get("reset_user_id")),
            reset_email=session.get("reset_email") or "",
            demo_reset_code=session.get("demo_reset_code"),
        )

    action = request.form.get("action", "login")

    if action == "signup":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""
        if not request.form.get("policy"):
            flash("You must accept the Portal Usage Policy to create an account.", "error")
            return redirect(url_for("portal"))
        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("portal"))
        user_id, err = create_client_user(email=email, password=password, name=name)
        if err or not user_id:
            flash(err or "Could not create account.", "error")
            return redirect(url_for("portal"))
        # Log the new client in immediately — no OTP required.
        session["user_id"] = user_id
        session["policy_accepted"] = True
        audit(user_id, "signup", email)
        audit(user_id, "login", "client")
        flash("Account created. Welcome!", "success")
        return redirect(url_for("portal_dashboard"))

    if action == "forgot_request":
        email = (request.form.get("email") or "").strip().lower()
        if not email or "@" not in email:
            flash("Enter a valid email address.", "error")
            return redirect(url_for("portal", mode="forgot"))
        db_user = get_user_by_email(email)
        # Always return a neutral message if account missing (avoid email enumeration).
        if not db_user or not db_user["active"]:
            flash(
                "If an account exists for that email, a reset code has been issued. "
                "Check your inbox (demo: use a registered portal email).",
                "success",
            )
            return redirect(url_for("portal", mode="forgot"))
        code = f"{secrets.randbelow(1000000):06d}"
        session["reset_user_id"] = db_user["id"]
        session["reset_email"] = email
        session["reset_code_hash"] = _hash_otp(code)
        session["demo_reset_code"] = code  # demo only — shown on screen
        audit(db_user["id"], "password_reset_requested", email)
        flash(
            f"Reset code issued. Demo code: {code} — enter it below with your new password.",
            "success",
        )
        return redirect(url_for("portal", mode="forgot"))

    if action == "forgot_reset":
        email = (request.form.get("email") or "").strip().lower()
        code = (request.form.get("reset_code") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""
        pending_id = session.get("reset_user_id")
        code_hash = session.get("reset_code_hash")
        if not pending_id or not code_hash:
            flash("Request a reset code first.", "error")
            return redirect(url_for("portal", mode="forgot"))
        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("portal", mode="forgot"))
        if not code or _hash_otp(code) != code_hash:
            flash("Invalid or expired reset code.", "error")
            audit(pending_id, "password_reset_failed", email)
            return redirect(url_for("portal", mode="forgot"))
        db_user = get_user_by_email(email)
        if not db_user or db_user["id"] != pending_id or not db_user["active"]:
            flash("Reset session expired. Request a new code.", "error")
            session.pop("reset_user_id", None)
            session.pop("reset_code_hash", None)
            session.pop("demo_reset_code", None)
            session.pop("reset_email", None)
            return redirect(url_for("portal", mode="forgot"))
        err = update_user_password(db_user["id"], password)
        if err:
            flash(err, "error")
            return redirect(url_for("portal", mode="forgot"))
        session.pop("reset_user_id", None)
        session.pop("reset_code_hash", None)
        session.pop("demo_reset_code", None)
        session.pop("reset_email", None)
        audit(db_user["id"], "password_reset", email)
        flash("Password updated. Sign in with your new password.", "success")
        return redirect(url_for("portal"))

    # login
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    role = request.form.get("role") or ""
    if not request.form.get("policy"):
        flash("You must accept the Portal Usage Policy as a condition of access.", "error")
        return redirect(url_for("portal"))

    db_user = get_user_by_email(email)
    if (
        not db_user
        or not db_user["active"]
        or not check_password_hash(db_user["password_hash"], password)
    ):
        flash("Invalid email or password, or account revoked.", "error")
        audit(None, "login_failed", email)
        return redirect(url_for("portal"))

    if role and db_user["role"] != role:
        flash(f"This account is registered as {db_user['role']}, not {role}.", "error")
        return redirect(url_for("portal"))

    session["user_id"] = db_user["id"]
    session["policy_accepted"] = True
    audit(db_user["id"], "login", db_user["role"])
    flash(f"Welcome, {db_user['name']}.", "success")
    return redirect(url_for("portal_dashboard"))


@app.route("/portal/logout", methods=["POST"])
def portal_logout():
    uid = session.get("user_id")
    if uid:
        audit(uid, "logout", None)
    session.clear()
    flash("Signed out.", "success")
    return redirect(url_for("portal"))


# ----- Dashboard -----

@app.route("/portal/dashboard")
@login_required
def portal_dashboard():
    user = current_user()
    view = request.args.get("view") or "overview"

    if user["role"] == "client":
        jobs = build_client_jobs(user)
        needed_docs_total = sum(len(j["needed_docs"]) for j in jobs)
        action_alerts_total = sum(
            1
            for job in jobs
            for alert in job["alerts"]
            if alert["status"] == "action_needed"
        )
        due_total = 0.0
        for j in jobs:
            for inv in j["invoices"]:
                if inv["status"] != "Paid":
                    due_total += float(inv["amount"])
        conn = get_db()
        try:
            consultations = conn.execute(
                "SELECT co.*, c.case_no FROM consultations co "
                "LEFT JOIN cases c ON c.id = co.case_id "
                "WHERE co.client_id = ? ORDER BY co.preferred_date, co.preferred_time",
                (user["id"],),
            ).fetchall()
        finally:
            conn.close()
        return render_template(
            "client_dashboard.html",
            user=user,
            jobs=jobs,
            needed_docs_total=needed_docs_total,
            action_alerts_total=action_alerts_total,
            due_total=due_total,
            consultations=consultations,
            view=view,
        )

    if user["role"] == "partner":
        jobs = build_partner_jobs(user)
        client_messages_total = sum(job["pending_replies"] for job in jobs)
        conn = get_db()
        try:
            consultations = conn.execute(
                "SELECT co.*, c.case_no, cl.name AS client_name "
                "FROM consultations co "
                "LEFT JOIN cases c ON c.id = co.case_id "
                "JOIN users cl ON cl.id = co.client_id "
                "WHERE co.case_id IS NULL OR c.partner_id = ? "
                "ORDER BY co.preferred_date, co.preferred_time",
                (user["id"],),
            ).fetchall()
            pending_drafts = conn.execute(
                "SELECT COUNT(*) AS c FROM drafts d "
                "JOIN cases c ON c.id = d.case_id "
                "WHERE c.partner_id = ? AND d.status = 'pending'",
                (user["id"],),
            ).fetchone()["c"]
        finally:
            conn.close()
        open_case = request.args.get("case", type=int)
        active_tab = request.args.get("tab") or "progress"
        if not open_case and jobs:
            open_case = jobs[0]["case"]["id"]
        return render_template(
            "partner_dashboard.html",
            user=user,
            jobs=jobs,
            consultations=consultations,
            client_messages_total=client_messages_total,
            pending_drafts=pending_drafts,
            open_case=open_case,
            active_tab=active_tab,
        )

    if user["role"] == "staff":
        jobs = build_staff_jobs(user)
        raw_enquiries = enquiries_for_staff()
        enriched_enquiries = []
        for eq in raw_enquiries:
            service = eq["service"] or "your enquiry"
            wa_msg = (
                f"Hi {eq['name']}, thank you for reaching out to Vinnita Legal Consultancy "
                f"regarding {service}. This is {user['name']} from our office. "
                f"Happy to help — when is a good time to speak?"
            )
            enriched_enquiries.append(
                {
                    **dict(eq),
                    "whatsapp_link": whatsapp_url(eq["phone"], wa_msg),
                }
            )
        new_leads = sum(1 for eq in raw_enquiries if eq["status"] == "new")
        docs_pending_total = sum(len(j["needed_docs"]) for j in jobs)
        due_invoices_total = sum(len(j["due_invoices"]) for j in jobs)
        active_panel = request.args.get("panel") or "leads"
        open_case = request.args.get("case", type=int)
        active_tab = request.args.get("tab") or "progress"
        if not open_case and jobs:
            open_case = jobs[0]["case"]["id"]
        if active_panel == "cases" and not request.args.get("case") and jobs:
            active_tab = request.args.get("tab") or "progress"
        return render_template(
            "staff_dashboard.html",
            user=user,
            jobs=jobs,
            enquiries=enriched_enquiries,
            new_leads=new_leads,
            docs_pending_total=docs_pending_total,
            due_invoices_total=due_invoices_total,
            active_panel=active_panel,
            open_case=open_case,
            active_tab=active_tab,
        )

    if user["role"] == "ceo":
        m = build_ceo_dashboard()
        charts_json = json.dumps(
            {
                "case_status": m["chart_case_status"],
                "revenue": m["chart_revenue"],
                "leads": m["chart_leads"],
                "sources": m["chart_sources"],
                "partners": m["chart_partner_load"],
            }
        )
        return render_template(
            "ceo_dashboard.html",
            user=user,
            m=m,
            charts_json=charts_json,
            active_panel=request.args.get("panel") or "overview",
        )

    cases = cases_for_user(user)
    conn = get_db()
    try:
        case_ids = [c["id"] for c in cases]
        invoices = []
        queries = []
        drafts = []
        audit_logs = []
        documents = []
        communications = []
        incidents = []
        case_ops = {}
        consultations = []

        if case_ids:
            placeholders = ",".join("?" * len(case_ids))
            invoices = conn.execute(
                f"SELECT i.*, c.case_no, c.title AS case_title FROM invoices i "
                f"JOIN cases c ON c.id = i.case_id "
                f"WHERE i.case_id IN ({placeholders}) ORDER BY i.id DESC",
                case_ids,
            ).fetchall()
            queries = conn.execute(
                f"SELECT q.*, c.case_no FROM queries q "
                f"JOIN cases c ON c.id = q.case_id "
                f"WHERE q.case_id IN ({placeholders}) ORDER BY q.id DESC LIMIT 20",
                case_ids,
            ).fetchall()
            documents = conn.execute(
                f"SELECT d.*, c.case_no FROM documents d "
                f"JOIN cases c ON c.id = d.case_id "
                f"WHERE d.case_id IN ({placeholders}) ORDER BY d.id DESC",
                case_ids,
            ).fetchall()
            communications = conn.execute(
                f"SELECT cm.*, c.case_no, u.name AS staff_name FROM communications cm "
                f"JOIN cases c ON c.id = cm.case_id "
                f"JOIN users u ON u.id = cm.staff_id "
                f"WHERE cm.case_id IN ({placeholders}) ORDER BY cm.id DESC LIMIT 20",
                case_ids,
            ).fetchall()

        if user["role"] == "partner":
            drafts = conn.execute(
                "SELECT d.*, c.case_no FROM drafts d "
                "JOIN cases c ON c.id = d.case_id "
                "WHERE c.partner_id = ? ORDER BY d.id DESC",
                (user["id"],),
            ).fetchall()
            audit_logs = conn.execute(
                "SELECT * FROM audit_logs WHERE user_id = ? ORDER BY id DESC LIMIT 30",
                (user["id"],),
            ).fetchall()
            consultations = conn.execute(
                "SELECT co.*, c.case_no, cl.name AS client_name "
                "FROM consultations co "
                "LEFT JOIN cases c ON c.id = co.case_id "
                "JOIN users cl ON cl.id = co.client_id "
                "WHERE co.case_id IS NULL OR c.partner_id = ? "
                "ORDER BY co.preferred_date, co.preferred_time",
                (user["id"],),
            ).fetchall()
            for case in cases:
                case_ops[case["id"]] = {
                    "milestones": conn.execute(
                        "SELECT * FROM case_milestones WHERE case_id = ? ORDER BY sort_order",
                        (case["id"],),
                    ).fetchall(),
                    "doc_requests": conn.execute(
                        "SELECT * FROM doc_requests WHERE case_id = ? ORDER BY sort_order",
                        (case["id"],),
                    ).fetchall(),
                    "updates": conn.execute(
                        "SELECT cu.*, u.name AS author_name FROM case_updates cu "
                        "LEFT JOIN users u ON u.id = cu.author_id "
                        "WHERE cu.case_id = ? ORDER BY cu.id DESC LIMIT 5",
                        (case["id"],),
                    ).fetchall(),
                    "alerts": conn.execute(
                        "SELECT * FROM compliance_alerts WHERE case_id = ? "
                        "ORDER BY due_date, id",
                        (case["id"],),
                    ).fetchall(),
                }
        else:
            audit_logs = conn.execute(
                "SELECT * FROM audit_logs WHERE user_id = ? ORDER BY id DESC LIMIT 30",
                (user["id"],),
            ).fetchall()
            incidents = conn.execute(
                "SELECT * FROM incidents WHERE reporter_id = ? ORDER BY id DESC LIMIT 10",
                (user["id"],),
            ).fetchall()
            drafts = conn.execute(
                "SELECT d.*, c.case_no FROM drafts d "
                "JOIN cases c ON c.id = d.case_id "
                "JOIN case_staff cs ON cs.case_id = c.id "
                "WHERE cs.staff_id = ? ORDER BY d.id DESC",
                (user["id"],),
            ).fetchall()

        pending_count = sum(1 for d in drafts if d["status"] == "pending")
        due_total = sum(
            float(i["amount"]) for i in invoices if i["status"] != "Paid"
        )
    finally:
        conn.close()

    return render_template(
        "portal_dashboard.html",
        user=user,
        cases=cases,
        invoices=invoices,
        queries=queries,
        drafts=drafts,
        documents=documents,
        communications=communications,
        audit_logs=audit_logs,
        incidents=incidents,
        view=view,
        pending_count=pending_count,
        due_total=due_total,
        case_ops=case_ops,
        consultations=consultations,
    )


# ----- Client actions -----

@app.route("/portal/consultations", methods=["POST"])
@role_required("client")
def portal_consultation_book():
    user = current_user()
    case_id = int(request.form.get("case_id") or 0) or None
    if case_id and not user_can_access_case(user, case_id):
        abort(403)
    practice_area = (request.form.get("practice_area") or "").strip()
    preferred_date = (request.form.get("preferred_date") or "").strip()
    preferred_time = (request.form.get("preferred_time") or "").strip()
    mode = (request.form.get("mode") or "Video").strip()
    note = (request.form.get("note") or "").strip() or None
    if not practice_area or not preferred_date or not preferred_time:
        flash("Practice area, date and time are required.", "error")
        return redirect(url_for("portal_dashboard"))
    if mode not in {"Video", "Phone"}:
        abort(400)
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO consultations "
            "(client_id, case_id, practice_area, preferred_date, preferred_time, "
            "mode, note, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'Requested', ?)",
            (
                user["id"],
                case_id,
                practice_area,
                preferred_date,
                preferred_time,
                mode,
                note,
                _now(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    audit(user["id"], "consultation_requested", f"{preferred_date}:{preferred_time}")
    flash("Consultation requested. Your assigned expert will confirm the slot.", "success")
    return redirect(url_for("portal_dashboard"))


@app.route("/portal/consultations/<int:consultation_id>", methods=["POST"])
@role_required("partner")
def portal_consultation_status(consultation_id: int):
    user = current_user()
    status = (request.form.get("status") or "").strip()
    if status not in {"Requested", "Confirmed", "Completed", "Cancelled"}:
        abort(400)
    conn = get_db()
    try:
        consultation = conn.execute(
            "SELECT co.*, c.partner_id FROM consultations co "
            "LEFT JOIN cases c ON c.id = co.case_id WHERE co.id = ?",
            (consultation_id,),
        ).fetchone()
        if not consultation:
            abort(404)
        if consultation["case_id"] and consultation["partner_id"] != user["id"]:
            abort(403)
        conn.execute(
            "UPDATE consultations SET status = ? WHERE id = ?",
            (status, consultation_id),
        )
        conn.commit()
    finally:
        conn.close()
    audit(user["id"], "consultation_updated", f"{consultation_id}:{status}")
    flash("Consultation status updated.", "success")
    return _portal_redirect(user)

@app.route("/portal/queries", methods=["POST"])
@role_required("client")
def portal_queries():
    user = current_user()
    case_id = int(request.form.get("case_id") or 0)
    body = (request.form.get("body") or "").strip()
    if not body or not user_can_access_case(user, case_id):
        flash("Invalid case or empty query.", "error")
        return redirect(url_for("portal_dashboard", view="messages"))
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO queries (case_id, user_id, body, created_at) VALUES (?, ?, ?, ?)",
            (case_id, user["id"], body, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    audit(user["id"], "client_query_submitted", str(case_id))
    flash("Message sent to your legal team.", "success")
    return redirect(url_for("portal_dashboard"))


@app.route("/portal/messages", methods=["POST"])
@role_required("partner", "staff")
def portal_message_reply():
    user = current_user()
    case_id = int(request.form.get("case_id") or 0)
    body = (request.form.get("body") or "").strip()
    if not body or not user_can_access_case(user, case_id):
        flash("Invalid case or empty message.", "error")
        return _portal_redirect(user, tab="messages", case_id=case_id)
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO queries (case_id, user_id, body, created_at) VALUES (?, ?, ?, ?)",
            (case_id, user["id"], body, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    audit(user["id"], "partner_message_sent", str(case_id))
    flash("Reply sent to client.", "success")
    return _portal_redirect(user, tab="messages", case_id=case_id)


@app.route("/portal/documents", methods=["GET", "POST"])
@login_required
def portal_documents_upload():
    user = current_user()
    # Browser GETs (or bookmark) land here — keep users on the dashboard docs tab.
    if request.method == "GET":
        return redirect(url_for("portal_dashboard", tab="docs", view="documents"))

    # POST requires role check
    if user["role"] not in ("client", "partner", "staff"):
        flash("You do not have permission for that action.", "error")
        return redirect(url_for("portal_dashboard"))

    case_id = int(request.form.get("case_id") or 0)
    if not user_can_access_case(user, case_id):
        flash("You can only upload to assigned cases.", "error")
        return _portal_redirect(user, tab="documents", case_id=case_id)
    f = request.files.get("file")
    if not f or not f.filename:
        flash("No file selected.", "error")
        return _portal_redirect(user, tab="documents", case_id=case_id)
    filename = secure_filename(f.filename)
    if not filename:
        flash("Invalid file name.", "error")
        return _portal_redirect(user, tab="documents", case_id=case_id)
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        flash("Format not allowed. Use PDF or JPEG only (§4.3).", "error")
        return _portal_redirect(user, tab="documents", case_id=case_id)
    data = f.read()
    if len(data) > MAX_UPLOAD:
        flash("File exceeds 10 MB limit (§4.3).", "error")
        return _portal_redirect(user, tab="documents", case_id=case_id)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored = f"{case_id}_{user['id']}_{secrets.token_hex(8)}{ext}"
    path = UPLOAD_DIR / stored
    path.write_bytes(data)
    mime = f.mimetype or "application/octet-stream"
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO documents (case_id, uploaded_by, filename, stored_path, mime, size, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (case_id, user["id"], filename, stored, mime, len(data), _now()),
        )
        conn.commit()
    finally:
        conn.close()
    audit(user["id"], "document_upload", filename)
    conn = get_db()
    try:
        if user["role"] == "client":
            needed = conn.execute(
                "SELECT id FROM doc_requests WHERE case_id = ? AND status = 'needed' "
                "ORDER BY sort_order LIMIT 1",
                (case_id,),
            ).fetchone()
            if needed:
                conn.execute(
                    "UPDATE doc_requests SET status = 'uploaded' WHERE id = ?",
                    (needed["id"],),
                )
                conn.commit()
    finally:
        conn.close()
    if user["role"] == "partner":
        flash(f"{filename} uploaded — client can view it on their dashboard.", "success")
    else:
        flash(f"{filename} uploaded. Action logged for audit.", "success")
    return _portal_redirect(user, tab="documents", case_id=case_id)


@app.route("/portal/documents/<int:doc_id>")
@login_required
def portal_document_download(doc_id: int):
    user = current_user()
    conn = get_db()
    try:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    finally:
        conn.close()
    if not doc or not user_can_access_case(user, doc["case_id"]):
        flash("File not found or you do not have access.", "error")
        return redirect(url_for("portal_dashboard", tab="docs", view="documents"))
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    try:
        path = ensure_document_file(doc["stored_path"], doc["filename"])
    except Exception:
        flash("File not found on server. Please re-upload the document.", "error")
        return redirect(url_for("portal_dashboard", tab="docs", view="documents"))
    audit(user["id"], "document_view", doc["filename"])
    return send_file(
        path,
        as_attachment=True,
        download_name=doc["filename"] or path.name,
        mimetype=doc["mime"] or "application/octet-stream",
    )


# ----- Partner actions -----

@app.route("/portal/cases/<int:case_id>/updates", methods=["POST"])
@role_required("partner", "staff")
def portal_case_update(case_id: int):
    user = current_user()
    if not user_can_access_case(user, case_id):
        flash("Case not assigned to you.", "error")
        return _portal_redirect(user, case_id=case_id, tab="client", panel="cases")
    body = (request.form.get("body") or "").strip()
    tab = request.form.get("redirect_tab") or "client"
    if not body:
        flash("Update cannot be empty.", "error")
        if user["role"] == "staff":
            return _portal_redirect(user, tab=tab, case_id=case_id, panel="cases")
        return _portal_redirect(user, tab=tab, case_id=case_id)
    kind = (request.form.get("update_kind") or "").strip()
    if kind == "document":
        body = f"[Document update] {body}"
    elif kind == "payment" or tab == "payments":
        body = f"[Payment update] {body}"
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO case_updates (case_id, author_id, body, created_at) "
            "VALUES (?, ?, ?, ?)",
            (case_id, user["id"], body, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    audit(user["id"], "client_update_posted", f"case:{case_id}")
    flash("Update posted on client dashboard.", "success")
    if user["role"] == "staff":
        return _portal_redirect(user, tab=tab, case_id=case_id, panel="cases")
    return _portal_redirect(user, tab="updates", case_id=case_id)


@app.route("/portal/milestones/<int:milestone_id>", methods=["POST"])
@role_required("partner")
def portal_milestone_update(milestone_id: int):
    user = current_user()
    status = (request.form.get("status") or "").strip()
    if status not in {"pending", "in_progress", "done"}:
        flash("Invalid milestone status.", "error")
        return _portal_redirect(user, tab="progress")
    conn = get_db()
    try:
        milestone = conn.execute(
            "SELECT m.*, c.partner_id, c.id AS case_id FROM case_milestones m "
            "JOIN cases c ON c.id = m.case_id WHERE m.id = ?",
            (milestone_id,),
        ).fetchone()
        if not milestone or milestone["partner_id"] != user["id"]:
            abort(403)
        completed = _now() if status == "done" else None
        conn.execute(
            "UPDATE case_milestones SET status = ?, completed_at = ? WHERE id = ?",
            (status, completed, milestone_id),
        )
        conn.commit()
        case_id = milestone["case_id"]
    finally:
        conn.close()
    audit(user["id"], "milestone_updated", f"{milestone_id}:{status}")
    flash("Progress milestone updated for the client.", "success")
    return _portal_redirect(user, tab="progress", case_id=case_id)


@app.route("/portal/cases/<int:case_id>/document-requests", methods=["POST"])
@role_required("partner", "staff")
def portal_document_request(case_id: int):
    user = current_user()
    if not user_can_access_case(user, case_id):
        abort(403)
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Document request name is required.", "error")
        return _portal_redirect(user, tab="documents", case_id=case_id)
    conn = get_db()
    try:
        next_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 AS n "
            "FROM doc_requests WHERE case_id = ?",
            (case_id,),
        ).fetchone()["n"]
        conn.execute(
            "INSERT INTO doc_requests (case_id, title, status, sort_order) "
            "VALUES (?, ?, 'needed', ?)",
            (case_id, title, next_order),
        )
        conn.commit()
    finally:
        conn.close()
    audit(user["id"], "document_requested", f"case:{case_id}:{title}")
    flash("Document request added to the client dashboard.", "success")
    return _portal_redirect(user, tab="documents", case_id=case_id)


@app.route("/portal/document-requests/<int:request_id>", methods=["POST"])
@role_required("partner", "staff")
def portal_document_request_status(request_id: int):
    user = current_user()
    status = (request.form.get("status") or "").strip()
    if status not in {"needed", "uploaded", "verified"}:
        abort(400)
    conn = get_db()
    try:
        item = conn.execute(
            "SELECT * FROM doc_requests WHERE id = ?", (request_id,)
        ).fetchone()
        if not item or not user_can_access_case(user, item["case_id"]):
            abort(403)
        conn.execute(
            "UPDATE doc_requests SET status = ? WHERE id = ?",
            (status, request_id),
        )
        conn.commit()
    finally:
        conn.close()
    audit(user["id"], "document_request_updated", f"{request_id}:{status}")
    flash("Document checklist updated.", "success")
    return _portal_redirect(user, tab="documents", case_id=item["case_id"])

@app.route("/portal/cases/<int:case_id>/status", methods=["POST"])
@role_required("partner")
def portal_case_status(case_id: int):
    user = current_user()
    if not user_can_access_case(user, case_id):
        flash("Case not assigned to you.", "error")
        return _portal_redirect(user, case_id=case_id)
    status = (request.form.get("status") or "").strip()
    hearing = (request.form.get("hearing_date") or "").strip() or None
    billing = (request.form.get("billing_note") or "").strip() or None
    conn = get_db()
    try:
        conn.execute(
            "UPDATE cases SET status = ?, hearing_date = COALESCE(?, hearing_date), "
            "billing_note = COALESCE(?, billing_note) WHERE id = ?",
            (status, hearing, billing, case_id),
        )
        conn.commit()
    finally:
        conn.close()
    audit(user["id"], "status_update", f"case:{case_id}:{status}")
    flash("Case updated on portal (§3.1 / §3.3).", "success")
    return _portal_redirect(user, tab="progress", case_id=case_id)


@app.route("/portal/drafts/<int:draft_id>/approve", methods=["POST"])
@role_required("partner")
def portal_draft_approve(draft_id: int):
    return _review_draft(draft_id, "approved")


@app.route("/portal/drafts/<int:draft_id>/reject", methods=["POST"])
@role_required("partner")
def portal_draft_reject(draft_id: int):
    return _review_draft(draft_id, "rejected")


def _review_draft(draft_id: int, new_status: str):
    user = current_user()
    conn = get_db()
    try:
        draft = conn.execute(
            "SELECT d.*, c.partner_id FROM drafts d "
            "JOIN cases c ON c.id = d.case_id WHERE d.id = ?",
            (draft_id,),
        ).fetchone()
        if not draft or draft["partner_id"] != user["id"]:
            flash("Draft not found or not assigned to you.", "error")
            return redirect(url_for("portal_dashboard", view="approvals"))
        conn.execute(
            "UPDATE drafts SET status = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?",
            (new_status, user["id"], _now(), draft_id),
        )
        conn.commit()
        title = draft["title"]
    finally:
        conn.close()
    audit(user["id"], f"draft_{new_status}", title)
    flash(f"Draft {new_status}: {title}", "success")
    return redirect(url_for("portal_dashboard", view="approvals"))


@app.route("/portal/conflicts", methods=["POST"])
@role_required("partner")
def portal_conflicts():
    user = current_user()
    client_name = (request.form.get("prospective_client") or "").strip()
    note = (request.form.get("note") or "").strip()
    if not client_name or not note:
        flash("Conflict disclosure requires client and note.", "error")
        return redirect(url_for("portal_dashboard", view="conflict"))
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO conflicts (partner_id, prospective_client, note, created_at) "
            "VALUES (?, ?, ?, ?)",
            (user["id"], client_name, note, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    audit(user["id"], "conflict_disclosure", client_name)
    flash("Conflict disclosure recorded for Compliance review (§3.2).", "success")
    return redirect(url_for("portal_dashboard", view="conflict"))


# ----- Staff actions -----

@app.route("/portal/comms", methods=["POST"])
@role_required("staff")
def portal_comms():
    user = current_user()
    case_id = int(request.form.get("case_id") or 0)
    ctype = (request.form.get("type") or "Call").strip()
    note = (request.form.get("note") or "").strip()
    if not note or not user_can_access_case(user, case_id):
        flash("Invalid case or empty communication note.", "error")
        return _portal_redirect(user, panel="cases")
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO communications (case_id, staff_id, type, note, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (case_id, user["id"], ctype, note, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    audit(user["id"], "comms_logged", f"{case_id}/{ctype}")
    flash(f"{ctype} logged on case file (§2.2).", "success")
    return _portal_redirect(user, panel="cases", case_id=case_id)


@app.route("/portal/enquiries/<int:enquiry_id>/whatsapp", methods=["POST"])
@role_required("staff")
def portal_enquiry_whatsapp(enquiry_id: int):
    user = current_user()
    conn = get_db()
    try:
        eq = conn.execute("SELECT * FROM enquiries WHERE id = ?", (enquiry_id,)).fetchone()
        if not eq:
            abort(404)
        conn.execute(
            "INSERT INTO enquiry_outreach (enquiry_id, staff_id, channel, note, created_at) "
            "VALUES (?, ?, 'whatsapp', ?, ?)",
            (enquiry_id, user["id"], "WhatsApp follow-up initiated", _now()),
        )
        conn.execute(
            "UPDATE enquiries SET status = 'whatsapp_sent' WHERE id = ?",
            (enquiry_id,),
        )
        conn.commit()
    finally:
        conn.close()
    audit(user["id"], "enquiry_whatsapp_logged", str(enquiry_id))
    flash(f"WhatsApp outreach logged for {eq['name']}.", "success")
    return _portal_redirect(user, panel="leads")


@app.route("/portal/enquiries/<int:enquiry_id>/status", methods=["POST"])
@role_required("staff")
def portal_enquiry_status(enquiry_id: int):
    user = current_user()
    status = (request.form.get("status") or "").strip()
    if status not in {"new", "whatsapp_sent", "converted", "closed"}:
        abort(400)
    conn = get_db()
    try:
        conn.execute("UPDATE enquiries SET status = ? WHERE id = ?", (status, enquiry_id))
        conn.commit()
    finally:
        conn.close()
    audit(user["id"], "enquiry_status_updated", f"{enquiry_id}:{status}")
    flash("Lead status updated.", "success")
    return _portal_redirect(user, panel="leads")


@app.route("/portal/partner-messages", methods=["POST"])
@role_required("staff")
def portal_partner_message():
    user = current_user()
    case_id = int(request.form.get("case_id") or 0)
    body = (request.form.get("body") or "").strip()
    if not body or not user_can_access_case(user, case_id):
        flash("Invalid case or empty message.", "error")
        return _portal_redirect(user, panel="cases", tab="partner", case_id=case_id)
    conn = get_db()
    try:
        case = conn.execute("SELECT partner_id FROM cases WHERE id = ?", (case_id,)).fetchone()
        if not case:
            abort(404)
        conn.execute(
            "INSERT INTO staff_messages (case_id, staff_id, partner_id, body, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (case_id, user["id"], case["partner_id"], body, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    audit(user["id"], "staff_message_to_partner", str(case_id))
    flash("Message sent to partner.", "success")
    return _portal_redirect(user, panel="cases", tab="partner", case_id=case_id)


@app.route("/portal/invoices/<int:invoice_id>/payment", methods=["POST"])
@role_required("staff")
def portal_invoice_payment(invoice_id: int):
    user = current_user()
    conn = get_db()
    try:
        inv = conn.execute(
            "SELECT i.*, c.case_no FROM invoices i "
            "JOIN cases c ON c.id = i.case_id WHERE i.id = ?",
            (invoice_id,),
        ).fetchone()
        if not inv or not user_can_access_case(user, inv["case_id"]):
            abort(403)
        conn.execute("UPDATE invoices SET status = 'Paid' WHERE id = ?", (invoice_id,))
        note = (
            f"[Payment received] Invoice {inv['invoice_no']} — "
            f"₹{inv['amount']:.0f} marked as paid. Thank you."
        )
        conn.execute(
            "INSERT INTO case_updates (case_id, author_id, body, created_at) "
            "VALUES (?, ?, ?, ?)",
            (inv["case_id"], user["id"], note, _now()),
        )
        conn.commit()
        case_id = inv["case_id"]
    finally:
        conn.close()
    audit(user["id"], "invoice_marked_paid", str(invoice_id))
    flash("Payment recorded and client notified on dashboard.", "success")
    return _portal_redirect(user, panel="cases", tab="payments", case_id=case_id)


@app.route("/portal/escalate", methods=["POST"])
@role_required("staff")
def portal_escalate():
    user = current_user()
    case_id = int(request.form.get("case_id") or 0) or None
    note = (request.form.get("note") or "").strip() or (
        "Client requested legal advice/opinion — escalated to Partner (§2.4)."
    )
    if case_id and not user_can_access_case(user, case_id):
        flash("Case not assigned to you.", "error")
        return _portal_redirect(user, panel="escalate")
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO incidents (reporter_id, kind, note, case_id, created_at) "
            "VALUES (?, 'escalation', ?, ?, ?)",
            (user["id"], note, case_id, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    audit(user["id"], "escalation_to_partner", str(case_id or "n/a"))
    flash("Escalated to assigned Partner. Do not advise the client directly (§2.4).", "success")
    return _portal_redirect(user, panel="escalate")


@app.route("/portal/breach", methods=["POST"])
@role_required("staff")
def portal_breach():
    user = current_user()
    note = (request.form.get("note") or "").strip() or (
        "Suspected breach / phishing / unauthorised access reported to Compliance/IT."
    )
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO incidents (reporter_id, kind, note, case_id, created_at) "
            "VALUES (?, 'breach', ?, NULL, ?)",
            (user["id"], note, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    audit(user["id"], "breach_report", "escalated")
    flash("Incident reported to Compliance / IT Officer (§2.3).", "success")
    return _portal_redirect(user, panel="escalate")


# ----- Boot -----

with app.app_context():
    init_schema()
    seed_if_empty()
    ensure_client_dashboard_seed()
    ensure_staff_dashboard_seed()
    ensure_ceo_user()
    ensure_demo_documents()


if __name__ == "__main__":
    app.run(debug=True)
