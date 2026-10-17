"""SQLite helpers for Vinnita Legal Consultancy portal."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "lexassist.db"
UPLOAD_DIR = BASE_DIR / "uploads"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('client', 'partner', 'staff', 'ceo')),
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_no TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'In Progress',
                client_id INTEGER NOT NULL REFERENCES users(id),
                partner_id INTEGER NOT NULL REFERENCES users(id),
                hearing_date TEXT,
                billing_note TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS case_staff (
                case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                staff_id INTEGER NOT NULL REFERENCES users(id),
                PRIMARY KEY (case_id, staff_id)
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                uploaded_by INTEGER NOT NULL REFERENCES users(id),
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                mime TEXT,
                size INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS communications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                staff_id INTEGER NOT NULL REFERENCES users(id),
                type TEXT NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'approved', 'rejected')),
                submitted_by INTEGER NOT NULL REFERENCES users(id),
                reviewed_by INTEGER REFERENCES users(id),
                reviewed_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conflicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                partner_id INTEGER NOT NULL REFERENCES users(id),
                prospective_client TEXT NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                invoice_no TEXT NOT NULL UNIQUE,
                amount REAL NOT NULL,
                status TEXT NOT NULL,
                due_date TEXT
            );

            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter_id INTEGER NOT NULL REFERENCES users(id),
                kind TEXT NOT NULL CHECK(kind IN ('breach', 'escalation')),
                note TEXT NOT NULL,
                case_id INTEGER REFERENCES cases(id),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                action TEXT NOT NULL,
                ref TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS enquiries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_page TEXT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT,
                city TEXT,
                service TEXT,
                message TEXT,
                extra TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS case_milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                detail TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'in_progress', 'done')),
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS case_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                author_id INTEGER REFERENCES users(id),
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS doc_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'needed'
                    CHECK(status IN ('needed', 'uploaded', 'verified')),
                sort_order INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS consultations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL REFERENCES users(id),
                case_id INTEGER REFERENCES cases(id) ON DELETE SET NULL,
                practice_area TEXT NOT NULL,
                preferred_date TEXT NOT NULL,
                preferred_time TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'Video',
                note TEXT,
                status TEXT NOT NULL DEFAULT 'Requested'
                    CHECK(status IN ('Requested', 'Confirmed', 'Completed', 'Cancelled')),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS compliance_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                due_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'upcoming'
                    CHECK(status IN ('upcoming', 'action_needed', 'completed'))
            );

            CREATE TABLE IF NOT EXISTS staff_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                staff_id INTEGER NOT NULL REFERENCES users(id),
                partner_id INTEGER NOT NULL REFERENCES users(id),
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS enquiry_outreach (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enquiry_id INTEGER NOT NULL REFERENCES enquiries(id) ON DELETE CASCADE,
                staff_id INTEGER NOT NULL REFERENCES users(id),
                channel TEXT NOT NULL DEFAULT 'whatsapp',
                note TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
        _ensure_staff_schema_migrations(conn)
    finally:
        conn.close()


def _ensure_staff_schema_migrations(conn: sqlite3.Connection) -> None:
    """Add columns/tables for existing databases."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(enquiries)").fetchall()}
    if "status" not in cols:
        conn.execute(
            "ALTER TABLE enquiries ADD COLUMN status TEXT NOT NULL DEFAULT 'new'"
        )
    _ensure_ceo_role_allowed(conn)
    conn.commit()


def _ensure_ceo_role_allowed(conn: sqlite3.Connection) -> None:
    """Rebuild users table if CHECK constraint blocks the ceo role."""
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if not sql or not sql["sql"]:
        return
    create_sql = sql["sql"]
    if "ceo" in create_sql:
        return
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        """
        CREATE TABLE users_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('client', 'partner', 'staff', 'ceo')),
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO users_new (id, email, password_hash, name, role, active, created_at) "
        "SELECT id, email, password_hash, name, role, active, created_at FROM users"
    )
    conn.execute("DROP TABLE users")
    conn.execute("ALTER TABLE users_new RENAME TO users")
    conn.execute("PRAGMA foreign_keys = ON")


def ensure_ceo_user() -> None:
    """Ensure founder/CEO demo account exists on existing databases."""
    conn = get_db()
    try:
        _ensure_ceo_role_allowed(conn)
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("ceo@lexassist.in",)
        ).fetchone()
        if row:
            conn.commit()
            return
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        conn.execute(
            "INSERT INTO users (email, password_hash, name, role, active, created_at) "
            "VALUES (?, ?, ?, 'ceo', 1, ?)",
            (
                "ceo@lexassist.in",
                generate_password_hash("demo123"),
                "Founder / CEO — Vinnita Legal Consultancy",
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def save_enquiry(
    *,
    source_page: str,
    name: str,
    phone: str,
    email: str | None = None,
    city: str | None = None,
    service: str | None = None,
    message: str | None = None,
    extra: str | None = None,
) -> int:
    conn = get_db()
    try:
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        cur = conn.execute(
            "INSERT INTO enquiries "
            "(source_page, name, phone, email, city, service, message, extra, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source_page,
                name.strip(),
                phone.strip(),
                (email or "").strip() or None,
                (city or "").strip() or None,
                (service or "").strip() or None,
                (message or "").strip() or None,
                (extra or "").strip() or None,
                now,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def seed_if_empty() -> None:
    conn = get_db()
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if count:
            return

        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        pwd = generate_password_hash("demo123")

        users = [
            ("client@lexassist.in", pwd, "Demo Client", "client", 1, now),
            ("partner@lexassist.in", pwd, "Adv. Vikram Malhotra", "partner", 1, now),
            ("staff@lexassist.in", pwd, "Office Staff — Priya", "staff", 1, now),
            ("ceo@lexassist.in", pwd, "Founder / CEO — Vinnita Legal Consultancy", "ceo", 1, now),
            ("client2@lexassist.in", pwd, "Other Client", "client", 1, now),
        ]
        conn.executemany(
            "INSERT INTO users (email, password_hash, name, role, active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            users,
        )

        client_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("client@lexassist.in",)
        ).fetchone()["id"]
        client2_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("client2@lexassist.in",)
        ).fetchone()["id"]
        partner_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("partner@lexassist.in",)
        ).fetchone()["id"]
        staff_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("staff@lexassist.in",)
        ).fetchone()["id"]

        hearing = (datetime.utcnow() + timedelta(days=7)).date().isoformat()
        conn.execute(
            "INSERT INTO cases (case_no, title, status, client_id, partner_id, "
            "hearing_date, billing_note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "LA-2026-0142",
                "Pvt Ltd Incorporation — TechStart",
                "In Progress",
                client_id,
                partner_id,
                hearing,
                "Professional fee ₹7,999",
                now,
            ),
        )
        conn.execute(
            "INSERT INTO cases (case_no, title, status, client_id, partner_id, "
            "hearing_date, billing_note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "LA-2026-0188",
                "Trademark Class 9 — Brand Protection",
                "Awaiting Client",
                client_id,
                partner_id,
                None,
                "Professional fee ₹12,500",
                now,
            ),
        )
        # Other client's case — must NOT appear for demo client
        conn.execute(
            "INSERT INTO cases (case_no, title, status, client_id, partner_id, "
            "hearing_date, billing_note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "LA-2026-0999",
                "GST Registration — OtherCo",
                "In Progress",
                client2_id,
                partner_id,
                None,
                None,
                now,
            ),
        )

        case142 = conn.execute(
            "SELECT id FROM cases WHERE case_no = ?", ("LA-2026-0142",)
        ).fetchone()["id"]
        case188 = conn.execute(
            "SELECT id FROM cases WHERE case_no = ?", ("LA-2026-0188",)
        ).fetchone()["id"]

        conn.execute(
            "INSERT INTO case_staff (case_id, staff_id) VALUES (?, ?)",
            (case142, staff_id),
        )
        conn.execute(
            "INSERT INTO case_staff (case_id, staff_id) VALUES (?, ?)",
            (case188, staff_id),
        )

        conn.execute(
            "INSERT INTO drafts (case_id, title, status, submitted_by, created_at) "
            "VALUES (?, ?, 'pending', ?, ?)",
            (case188, "NDA — Vendor Agreement draft", staff_id, now),
        )

        conn.execute(
            "INSERT INTO invoices (case_id, invoice_no, amount, status, due_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (case142, "INV-8821", 7999.0, "Paid", None),
        )
        due = (datetime.utcnow() + timedelta(days=7)).date().isoformat()
        conn.execute(
            "INSERT INTO invoices (case_id, invoice_no, amount, status, due_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (case188, "INV-8910", 12500.0, "Due", due),
        )

        conn.execute(
            "INSERT INTO queries (case_id, user_id, body, created_at) VALUES (?, ?, ?, ?)",
            (
                case142,
                client_id,
                "Please confirm MCA name approval timeline for TechStart.",
                now,
            ),
        )

        # Progress milestones for client dashboard
        milestones_142 = [
            (case142, "Kick-off & checklist shared", "Engagement confirmed", 1, "done", now),
            (case142, "KYC & documents collected", "PAN, address, photos verified", 2, "done", now),
            (case142, "Name reservation (RUN/SPICe+)", "Name filed with MCA", 3, "done", now),
            (case142, "SPICe+ / incorporation filing", "Forms under preparation/filing", 4, "in_progress", None),
            (case142, "Certificate & CIN delivery", "Awaiting MCA approval", 5, "pending", None),
        ]
        milestones_188 = [
            (case188, "Brand search brief", "Search scope agreed", 1, "done", now),
            (case188, "Client documents", "Logo / user affidavit needed", 2, "in_progress", None),
            (case188, "TM application draft", "Awaiting partner approval", 3, "pending", None),
            (case188, "Filing with Trademark Registry", "Submit after approval", 4, "pending", None),
            (case188, "Acknowledgement & tracking", "Application number shared", 5, "pending", None),
        ]
        conn.executemany(
            "INSERT INTO case_milestones "
            "(case_id, title, detail, sort_order, status, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            milestones_142 + milestones_188,
        )

        updates = [
            (case142, partner_id, "Name reservation accepted. Preparing SPICe+ package.", now),
            (case142, staff_id, "Collected DSC documents from client. Logged on file.", now),
            (case188, partner_id, "Awaiting logo file and user affidavit from client.", now),
            (case188, staff_id, "Draft TM-A prepared — pending partner review.", now),
        ]
        conn.executemany(
            "INSERT INTO case_updates (case_id, author_id, body, created_at) VALUES (?, ?, ?, ?)",
            updates,
        )

        docs_needed = [
            (case142, "Director PAN (PDF)", "verified", 1),
            (case142, "Address proof", "verified", 2),
            (case142, "Passport photo", "uploaded", 3),
            (case188, "Brand logo (JPEG/PNG)", "needed", 1),
            (case188, "User affidavit", "needed", 2),
            (case188, "ID proof of applicant", "uploaded", 3),
        ]
        conn.executemany(
            "INSERT INTO doc_requests (case_id, title, status, sort_order) VALUES (?, ?, ?, ?)",
            docs_needed,
        )

        conn.execute(
            "INSERT INTO audit_logs (user_id, action, ref, created_at) VALUES (?, ?, ?, ?)",
            (None, "database_seeded", "initial", now),
        )
        conn.commit()
    finally:
        conn.close()


def ensure_client_dashboard_seed() -> None:
    """Backfill milestones for existing DBs created before client dashboard."""
    conn = get_db()
    try:
        n = conn.execute("SELECT COUNT(*) AS c FROM case_milestones").fetchone()["c"]
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        rows = conn.execute("SELECT id, case_no FROM cases").fetchall()
        if not n:
            for row in rows:
                cid, cno = row["id"], row["case_no"]
                if cno == "LA-2026-0142":
                    data = [
                        (cid, "Kick-off & checklist shared", "Engagement confirmed", 1, "done", now),
                        (cid, "KYC & documents collected", "PAN, address verified", 2, "done", now),
                        (cid, "Name reservation", "Filed with MCA", 3, "done", now),
                        (cid, "SPICe+ filing", "In progress", 4, "in_progress", None),
                        (cid, "Certificate delivery", "Pending", 5, "pending", None),
                    ]
                elif cno == "LA-2026-0188":
                    data = [
                        (cid, "Brand search brief", "Scope agreed", 1, "done", now),
                        (cid, "Client documents", "Logo / affidavit needed", 2, "in_progress", None),
                        (cid, "TM draft", "Pending approval", 3, "pending", None),
                        (cid, "Registry filing", "Pending", 4, "pending", None),
                        (cid, "Acknowledgement", "Pending", 5, "pending", None),
                    ]
                else:
                    continue
                conn.executemany(
                    "INSERT INTO case_milestones "
                    "(case_id, title, detail, sort_order, status, completed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    data,
                )
                if cno == "LA-2026-0188":
                    conn.executemany(
                        "INSERT INTO doc_requests (case_id, title, status, sort_order) VALUES (?, ?, ?, ?)",
                        [
                            (cid, "Brand logo (JPEG/PNG)", "needed", 1),
                            (cid, "User affidavit", "needed", 2),
                        ],
                    )

        alert_count = conn.execute(
            "SELECT COUNT(*) AS c FROM compliance_alerts"
        ).fetchone()["c"]
        if not alert_count:
            today = datetime.utcnow().date()
            for row in rows:
                cid, cno = row["id"], row["case_no"]
                if cno == "LA-2026-0142":
                    conn.executemany(
                        "INSERT INTO compliance_alerts "
                        "(case_id, title, category, due_date, status) VALUES (?, ?, ?, ?, ?)",
                        [
                            (
                                cid,
                                "Submit signed SPICe+ declarations",
                                "MCA",
                                (today + timedelta(days=3)).isoformat(),
                                "action_needed",
                            ),
                            (
                                cid,
                                "Director KYC review",
                                "MCA",
                                (today + timedelta(days=30)).isoformat(),
                                "upcoming",
                            ),
                        ],
                    )
                elif cno == "LA-2026-0188":
                    conn.execute(
                        "INSERT INTO compliance_alerts "
                        "(case_id, title, category, due_date, status) VALUES (?, ?, ?, ?, ?)",
                        (
                            cid,
                            "Upload brand logo and user affidavit",
                            "Trademark",
                            (today + timedelta(days=5)).isoformat(),
                            "action_needed",
                        ),
                    )
        conn.commit()
    finally:
        conn.close()


def audit(user_id: int | None, action: str, ref: str | None = None) -> None:
    conn = get_db()
    try:
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        conn.execute(
            "INSERT INTO audit_logs (user_id, action, ref, created_at) VALUES (?, ?, ?, ?)",
            (user_id, action, ref, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_by_email(email: str) -> sqlite3.Row | None:
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()
    finally:
        conn.close()


def create_client_user(
    *, email: str, password: str, name: str
) -> tuple[int | None, str | None]:
    """Public client registration. Returns (user_id, error_message)."""
    email_n = (email or "").lower().strip()
    name_n = (name or "").strip()
    password = password or ""
    if not email_n or "@" not in email_n:
        return None, "Enter a valid email address."
    if not name_n or len(name_n) < 2:
        return None, "Enter your full name."
    if len(password) < 6:
        return None, "Password must be at least 6 characters."
    if get_user_by_email(email_n):
        return None, "An account with this email already exists. Sign in instead."
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, name, role, active, created_at) "
            "VALUES (?, ?, ?, 'client', 1, ?)",
            (email_n, generate_password_hash(password), name_n, now),
        )
        conn.commit()
        return int(cur.lastrowid), None
    except sqlite3.IntegrityError:
        return None, "An account with this email already exists. Sign in instead."
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()


def update_user_password(user_id: int, password: str) -> str | None:
    """Set a new password. Returns error message or None on success."""
    password = password or ""
    if len(password) < 6:
        return "Password must be at least 6 characters."
    conn = get_db()
    try:
        cur = conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ? AND active = 1",
            (generate_password_hash(password), user_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return "Account not found or inactive."
        return None
    finally:
        conn.close()


def ensure_demo_documents() -> None:
    """Ensure demo/uploaded document rows have real files on disk.

    Stops dashboard View links returning 404 when the DB has a documents
    row but the file under uploads/ is missing (common after restarts,
    moves, or partial seeds).
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    try:
        # Repair any existing rows with a missing payload
        rows = conn.execute(
            "SELECT id, filename, stored_path FROM documents"
        ).fetchall()
        for doc in rows:
            path = UPLOAD_DIR / doc["stored_path"]
            if not path.exists():
                path.write_bytes(_placeholder_bytes(doc["filename"] or "document.pdf"))

        case = conn.execute(
            "SELECT id FROM cases WHERE case_no = ?", ("LA-2026-0142",)
        ).fetchone()
        partner = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("partner@lexassist.in",)
        ).fetchone()
        client = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("client@lexassist.in",)
        ).fetchone()
        if not case or not partner or not client:
            conn.commit()
            return

        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        demos = [
            (
                case["id"],
                partner["id"],
                "Incorporation-Checklist.pdf",
                f"{case['id']}_{partner['id']}_seed_checklist.pdf",
                "application/pdf",
            ),
            (
                case["id"],
                client["id"],
                "Director-PAN.pdf",
                f"{case['id']}_{client['id']}_seed_pan.pdf",
                "application/pdf",
            ),
        ]
        for case_id, uploader, filename, stored, mime in demos:
            exists = conn.execute(
                "SELECT id FROM documents WHERE case_id = ? AND filename = ?",
                (case_id, filename),
            ).fetchone()
            if exists:
                continue
            path = UPLOAD_DIR / stored
            data = _placeholder_bytes(filename)
            path.write_bytes(data)
            conn.execute(
                "INSERT INTO documents (case_id, uploaded_by, filename, stored_path, mime, size, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (case_id, uploader, filename, stored, mime, len(data), now),
            )
        conn.commit()
    finally:
        conn.close()


def _placeholder_bytes(filename: str) -> bytes:
    """Minimal readable PDF (or text) so demo downloads never 404."""
    name = (filename or "document").replace("\\", "/").split("/")[-1]
    if name.lower().endswith((".jpg", ".jpeg", ".png")):
        # 1x1 PNG
        import base64

        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
    # Tiny valid-ish PDF
    body = f"""%PDF-1.4
1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj
3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144]
/Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj
4 0 obj<< /Length 68 >>stream
BT /F1 12 Tf 40 100 Td ({name[:40]}) Tj ET
endstream
endobj
5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000385 00000 n 
trailer<< /Size 6 /Root 1 0 R >>
startxref
462
%%EOF
""".encode(
        "latin-1", errors="replace"
    )
    return body


def ensure_document_file(stored_path: str, filename: str | None = None) -> Path:
    """Return absolute path for a stored document, recreating missing demo bytes."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = (UPLOAD_DIR / stored_path).resolve()
    if not str(path).startswith(str(UPLOAD_DIR.resolve())):
        raise ValueError("Invalid stored path")
    if not path.exists():
        path.write_bytes(_placeholder_bytes(filename or path.name))
    return path


def user_can_access_case(user: sqlite3.Row, case_id: int) -> bool:
    conn = get_db()
    try:
        case = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if not case:
            return False
        if user["role"] == "client":
            return case["client_id"] == user["id"]
        if user["role"] == "partner":
            return case["partner_id"] == user["id"]
        if user["role"] == "staff":
            row = conn.execute(
                "SELECT 1 FROM case_staff WHERE case_id = ? AND staff_id = ?",
                (case_id, user["id"]),
            ).fetchone()
            return row is not None
        # CEO has org-wide read access for progress / finance oversight
        if user["role"] == "ceo":
            return True
        return False
    finally:
        conn.close()


def cases_for_user(user: sqlite3.Row) -> list[sqlite3.Row]:
    conn = get_db()
    try:
        if user["role"] == "client":
            return conn.execute(
                "SELECT c.*, u.name AS partner_name, u.email AS partner_email "
                "FROM cases c "
                "JOIN users u ON u.id = c.partner_id "
                "WHERE c.client_id = ? ORDER BY c.id DESC",
                (user["id"],),
            ).fetchall()
        if user["role"] == "partner":
            return conn.execute(
                "SELECT c.*, cl.name AS client_name, cl.email AS client_email "
                "FROM cases c "
                "JOIN users cl ON cl.id = c.client_id "
                "WHERE c.partner_id = ? ORDER BY c.id DESC",
                (user["id"],),
            ).fetchall()
        return conn.execute(
            "SELECT c.*, cl.name AS client_name, p.name AS partner_name "
            "FROM cases c "
            "JOIN case_staff cs ON cs.case_id = c.id "
            "JOIN users cl ON cl.id = c.client_id "
            "JOIN users p ON p.id = c.partner_id "
            "WHERE cs.staff_id = ? ORDER BY c.id DESC",
            (user["id"],),
        ).fetchall()
    finally:
        conn.close()


def build_client_jobs(user: sqlite3.Row) -> list[dict]:
    """Rich job cards for the client dashboard."""
    cases = cases_for_user(user)
    if not cases:
        return []
    conn = get_db()
    jobs: list[dict] = []
    try:
        for c in cases:
            cid = c["id"]
            staff = conn.execute(
                "SELECT u.name, u.email FROM case_staff cs "
                "JOIN users u ON u.id = cs.staff_id WHERE cs.case_id = ?",
                (cid,),
            ).fetchall()
            milestones = conn.execute(
                "SELECT * FROM case_milestones WHERE case_id = ? ORDER BY sort_order",
                (cid,),
            ).fetchall()
            updates = conn.execute(
                "SELECT cu.*, u.name AS author_name, u.role AS author_role "
                "FROM case_updates cu LEFT JOIN users u ON u.id = cu.author_id "
                "WHERE cu.case_id = ? ORDER BY cu.id DESC LIMIT 8",
                (cid,),
            ).fetchall()
            doc_reqs = conn.execute(
                "SELECT * FROM doc_requests WHERE case_id = ? ORDER BY sort_order",
                (cid,),
            ).fetchall()
            docs = conn.execute(
                "SELECT * FROM documents WHERE case_id = ? ORDER BY id DESC",
                (cid,),
            ).fetchall()
            invoices = conn.execute(
                "SELECT * FROM invoices WHERE case_id = ? ORDER BY id DESC",
                (cid,),
            ).fetchall()
            queries = conn.execute(
                "SELECT q.*, u.name AS author_name, u.role AS author_role "
                "FROM queries q JOIN users u ON u.id = q.user_id "
                "WHERE q.case_id = ? ORDER BY q.id ASC LIMIT 20",
                (cid,),
            ).fetchall()
            alerts = conn.execute(
                "SELECT * FROM compliance_alerts WHERE case_id = ? "
                "ORDER BY due_date, id",
                (cid,),
            ).fetchall()

            total = len(milestones) or 1
            done = sum(1 for m in milestones if m["status"] == "done")
            in_prog = sum(1 for m in milestones if m["status"] == "in_progress")
            progress = int(round((done + 0.5 * in_prog) / total * 100))
            current = next(
                (m for m in milestones if m["status"] == "in_progress"),
                None,
            )
            if not current:
                current = next(
                    (m for m in milestones if m["status"] == "pending"),
                    None,
                )
            needed_docs = [d for d in doc_reqs if d["status"] == "needed"]

            jobs.append(
                {
                    "case": c,
                    "staff": staff,
                    "milestones": milestones,
                    "updates": updates,
                    "doc_requests": doc_reqs,
                    "documents": docs,
                    "invoices": invoices,
                    "queries": queries,
                    "alerts": alerts,
                    "progress": progress,
                    "current_step": current,
                    "needed_docs": needed_docs,
                }
            )
    finally:
        conn.close()
    return jobs


def build_partner_jobs(user: sqlite3.Row) -> list[dict]:
    """Rich case cards for the partner dashboard."""
    cases = cases_for_user(user)
    if not cases:
        return []
    conn = get_db()
    jobs: list[dict] = []
    try:
        for c in cases:
            cid = c["id"]
            milestones = conn.execute(
                "SELECT * FROM case_milestones WHERE case_id = ? ORDER BY sort_order",
                (cid,),
            ).fetchall()
            updates = conn.execute(
                "SELECT cu.*, u.name AS author_name, u.role AS author_role "
                "FROM case_updates cu LEFT JOIN users u ON u.id = cu.author_id "
                "WHERE cu.case_id = ? ORDER BY cu.id DESC LIMIT 10",
                (cid,),
            ).fetchall()
            doc_reqs = conn.execute(
                "SELECT * FROM doc_requests WHERE case_id = ? ORDER BY sort_order",
                (cid,),
            ).fetchall()
            docs = conn.execute(
                "SELECT d.*, u.name AS uploader_name, u.role AS uploader_role "
                "FROM documents d JOIN users u ON u.id = d.uploaded_by "
                "WHERE d.case_id = ? ORDER BY d.id DESC",
                (cid,),
            ).fetchall()
            queries = conn.execute(
                "SELECT q.*, u.name AS author_name, u.role AS author_role "
                "FROM queries q JOIN users u ON u.id = q.user_id "
                "WHERE q.case_id = ? ORDER BY q.id ASC",
                (cid,),
            ).fetchall()
            staff = conn.execute(
                "SELECT u.name, u.email FROM case_staff cs "
                "JOIN users u ON u.id = cs.staff_id WHERE cs.case_id = ?",
                (cid,),
            ).fetchall()
            drafts = conn.execute(
                "SELECT * FROM drafts WHERE case_id = ? ORDER BY id DESC LIMIT 5",
                (cid,),
            ).fetchall()

            total = len(milestones) or 1
            done = sum(1 for m in milestones if m["status"] == "done")
            in_prog = sum(1 for m in milestones if m["status"] == "in_progress")
            progress = int(round((done + 0.5 * in_prog) / total * 100))
            current = next(
                (m for m in milestones if m["status"] == "in_progress"),
                None,
            )
            if not current:
                current = next(
                    (m for m in milestones if m["status"] == "pending"),
                    None,
                )
            client_messages = [q for q in queries if q["author_role"] == "client"]
            pending_replies = len(client_messages)

            jobs.append(
                {
                    "case": c,
                    "staff": staff,
                    "milestones": milestones,
                    "updates": updates,
                    "doc_requests": doc_reqs,
                    "documents": docs,
                    "queries": queries,
                    "drafts": drafts,
                    "progress": progress,
                    "current_step": current,
                    "pending_replies": pending_replies,
                }
            )
    finally:
        conn.close()
    return jobs


def ensure_staff_dashboard_seed() -> None:
    """Sample website enquiries for staff dashboard demo."""
    conn = get_db()
    try:
        _ensure_staff_schema_migrations(conn)
        n = conn.execute("SELECT COUNT(*) AS c FROM enquiries").fetchone()["c"]
        if n:
            return
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        samples = [
            ("contact", "Rahul Verma", "9876543210", "rahul@techstart.in", "Delhi NCR",
             "Pvt Ltd Registration", "Need company registration for SaaS startup", "new"),
            ("business-registration", "Anita Desai", "9123456780", None, "Mumbai",
             "Business Registration", "Want OPC for consulting practice", "new"),
            ("gst-compliance", "Suresh Kumar", "9988776655", "suresh@gst.in", "Ahmedabad, Gujarat",
             "GST Registration", "New GSTIN for trading firm", "new"),
            ("trademark", "Meera Iyer", "9090909090", "meera@brand.co", "Bangalore",
             "Trademark", "Class 35 trademark for retail brand", "converted"),
            ("partnership", "Imran Khan", "9812345678", None, "Lucknow, UP",
             "Partnership Firm", "Two partners — deed and filing", "closed"),
            ("contact", "Neha Gupta", "9000011111", "neha@co.in", "Delhi NCR",
             "GST Registration", "Want GST + MSME together", "converted"),
        ]
        conn.executemany(
            "INSERT INTO enquiries "
            "(source_page, name, phone, email, city, service, message, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7], now) for s in samples],
        )
        conn.commit()
    finally:
        conn.close()


def whatsapp_url(phone: str, message: str) -> str:
    """Build wa.me link for Indian numbers."""
    from urllib.parse import quote

    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    elif digits.startswith("0") and len(digits) == 11:
        digits = "91" + digits[1:]
    return f"https://wa.me/{digits}?text={quote(message)}"


def build_staff_jobs(user: sqlite3.Row) -> list[dict]:
    """Rich case cards for the office staff dashboard."""
    cases = cases_for_user(user)
    if not cases:
        return []
    conn = get_db()
    jobs: list[dict] = []
    try:
        for c in cases:
            cid = c["id"]
            partner_id = c["partner_id"]
            milestones = conn.execute(
                "SELECT * FROM case_milestones WHERE case_id = ? ORDER BY sort_order",
                (cid,),
            ).fetchall()
            updates = conn.execute(
                "SELECT cu.*, u.name AS author_name, u.role AS author_role "
                "FROM case_updates cu LEFT JOIN users u ON u.id = cu.author_id "
                "WHERE cu.case_id = ? ORDER BY cu.id DESC LIMIT 12",
                (cid,),
            ).fetchall()
            partner_updates = [u for u in updates if u["author_role"] == "partner"]
            doc_reqs = conn.execute(
                "SELECT * FROM doc_requests WHERE case_id = ? ORDER BY sort_order",
                (cid,),
            ).fetchall()
            docs = conn.execute(
                "SELECT d.*, u.name AS uploader_name, u.role AS uploader_role "
                "FROM documents d JOIN users u ON u.id = d.uploaded_by "
                "WHERE d.case_id = ? ORDER BY d.id DESC LIMIT 10",
                (cid,),
            ).fetchall()
            queries = conn.execute(
                "SELECT q.*, u.name AS author_name, u.role AS author_role "
                "FROM queries q JOIN users u ON u.id = q.user_id "
                "WHERE q.case_id = ? ORDER BY q.id DESC LIMIT 8",
                (cid,),
            ).fetchall()
            invoices = conn.execute(
                "SELECT * FROM invoices WHERE case_id = ? ORDER BY id DESC",
                (cid,),
            ).fetchall()
            partner_messages = conn.execute(
                "SELECT sm.*, u.name AS staff_name "
                "FROM staff_messages sm JOIN users u ON u.id = sm.staff_id "
                "WHERE sm.case_id = ? ORDER BY sm.id DESC LIMIT 10",
                (cid,),
            ).fetchall()
            partner = conn.execute(
                "SELECT id, name, email FROM users WHERE id = ?", (partner_id,)
            ).fetchone()
            client = conn.execute(
                "SELECT name, email FROM users WHERE id = ?", (c["client_id"],)
            ).fetchone()

            total = len(milestones) or 1
            done = sum(1 for m in milestones if m["status"] == "done")
            in_prog = sum(1 for m in milestones if m["status"] == "in_progress")
            progress = int(round((done + 0.5 * in_prog) / total * 100))
            current = next(
                (m for m in milestones if m["status"] == "in_progress"),
                None,
            ) or next((m for m in milestones if m["status"] == "pending"), None)
            due_invoices = [i for i in invoices if i["status"] != "Paid"]
            needed_docs = [d for d in doc_reqs if d["status"] == "needed"]
            client_queries = [q for q in queries if q["author_role"] == "client"]

            jobs.append(
                {
                    "case": c,
                    "partner": partner,
                    "client": client,
                    "milestones": milestones,
                    "updates": updates,
                    "partner_updates": partner_updates,
                    "doc_requests": doc_reqs,
                    "needed_docs": needed_docs,
                    "documents": docs,
                    "queries": queries,
                    "client_queries": client_queries,
                    "invoices": invoices,
                    "due_invoices": due_invoices,
                    "partner_messages": partner_messages,
                    "progress": progress,
                    "current_step": current,
                }
            )
    finally:
        conn.close()
    return jobs


def enquiries_for_staff(limit: int = 30) -> list[sqlite3.Row]:
    conn = get_db()
    try:
        return conn.execute(
            "SELECT e.*, "
            "(SELECT COUNT(*) FROM enquiry_outreach eo WHERE eo.enquiry_id = e.id) AS outreach_count "
            "FROM enquiries e ORDER BY e.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()


def _case_progress(conn: sqlite3.Connection, case_id: int) -> int:
    milestones = conn.execute(
        "SELECT status FROM case_milestones WHERE case_id = ?", (case_id,)
    ).fetchall()
    if not milestones:
        return 0
    total = len(milestones)
    done = sum(1 for m in milestones if m["status"] == "done")
    in_prog = sum(1 for m in milestones if m["status"] == "in_progress")
    return int(round((done + 0.5 * in_prog) / total * 100))


def build_ceo_dashboard() -> dict:
    """Org-wide founder metrics: people, cases, revenue, leads, activity."""
    conn = get_db()
    try:
        role_counts = {
            r["role"]: r["c"]
            for r in conn.execute(
                "SELECT role, COUNT(*) AS c FROM users WHERE active = 1 GROUP BY role"
            ).fetchall()
        }
        cases = conn.execute(
            "SELECT c.*, cl.name AS client_name, cl.email AS client_email, "
            "p.name AS partner_name, p.email AS partner_email "
            "FROM cases c "
            "JOIN users cl ON cl.id = c.client_id "
            "JOIN users p ON p.id = c.partner_id "
            "ORDER BY c.id DESC"
        ).fetchall()

        case_rows = []
        status_counts: dict[str, int] = {}
        for c in cases:
            progress = _case_progress(conn, c["id"])
            status_counts[c["status"]] = status_counts.get(c["status"], 0) + 1
            paid = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS s FROM invoices "
                "WHERE case_id = ? AND status = 'Paid'",
                (c["id"],),
            ).fetchone()["s"]
            due = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS s FROM invoices "
                "WHERE case_id = ? AND status != 'Paid'",
                (c["id"],),
            ).fetchone()["s"]
            staff = conn.execute(
                "SELECT u.name FROM case_staff cs JOIN users u ON u.id = cs.staff_id "
                "WHERE cs.case_id = ?",
                (c["id"],),
            ).fetchall()
            case_rows.append(
                {
                    "case": c,
                    "progress": progress,
                    "paid": float(paid or 0),
                    "due": float(due or 0),
                    "staff_names": [s["name"] for s in staff],
                }
            )

        invoices = conn.execute(
            "SELECT i.*, c.case_no, c.title AS case_title, cl.name AS client_name "
            "FROM invoices i "
            "JOIN cases c ON c.id = i.case_id "
            "JOIN users cl ON cl.id = c.client_id "
            "ORDER BY i.id DESC"
        ).fetchall()
        revenue_paid = sum(float(i["amount"]) for i in invoices if i["status"] == "Paid")
        revenue_due = sum(float(i["amount"]) for i in invoices if i["status"] != "Paid")

        enquiries = conn.execute(
            "SELECT * FROM enquiries ORDER BY id DESC LIMIT 40"
        ).fetchall()
        lead_total = conn.execute("SELECT COUNT(*) AS c FROM enquiries").fetchone()["c"]
        lead_new = conn.execute(
            "SELECT COUNT(*) AS c FROM enquiries WHERE status = 'new'"
        ).fetchone()["c"]
        lead_contacted = conn.execute(
            "SELECT COUNT(*) AS c FROM enquiries WHERE status = 'whatsapp_sent'"
        ).fetchone()["c"]
        lead_converted = conn.execute(
            "SELECT COUNT(*) AS c FROM enquiries WHERE status = 'converted'"
        ).fetchone()["c"]
        lead_closed = conn.execute(
            "SELECT COUNT(*) AS c FROM enquiries WHERE status = 'closed'"
        ).fetchone()["c"]
        # Satisfied ≈ converted + closed (requirement handled / not pursued)
        lead_satisfied = lead_converted + lead_closed
        conversion_rate = (
            round(100.0 * lead_converted / lead_total, 1) if lead_total else 0.0
        )
        satisfaction_rate = (
            round(100.0 * lead_satisfied / lead_total, 1) if lead_total else 0.0
        )

        partners = conn.execute(
            "SELECT u.id, u.name, u.email, "
            "(SELECT COUNT(*) FROM cases c WHERE c.partner_id = u.id) AS case_count, "
            "(SELECT COUNT(*) FROM drafts d JOIN cases c ON c.id = d.case_id "
            " WHERE c.partner_id = u.id AND d.status = 'pending') AS pending_drafts "
            "FROM users u WHERE u.role = 'partner' AND u.active = 1"
        ).fetchall()
        partner_rows = []
        for p in partners:
            paid = conn.execute(
                "SELECT COALESCE(SUM(i.amount), 0) AS s FROM invoices i "
                "JOIN cases c ON c.id = i.case_id "
                "WHERE c.partner_id = ? AND i.status = 'Paid'",
                (p["id"],),
            ).fetchone()["s"]
            updates = conn.execute(
                "SELECT COUNT(*) AS c FROM case_updates cu "
                "JOIN cases c ON c.id = cu.case_id "
                "WHERE c.partner_id = ? AND cu.author_id = ?",
                (p["id"], p["id"]),
            ).fetchone()["c"]
            partner_rows.append(
                {
                    **dict(p),
                    "revenue": float(paid or 0),
                    "updates_posted": updates,
                }
            )

        staff_users = conn.execute(
            "SELECT u.id, u.name, u.email FROM users u "
            "WHERE u.role = 'staff' AND u.active = 1"
        ).fetchall()
        staff_rows = []
        for s in staff_users:
            assigned = conn.execute(
                "SELECT COUNT(*) AS c FROM case_staff WHERE staff_id = ?",
                (s["id"],),
            ).fetchone()["c"]
            outreach = conn.execute(
                "SELECT COUNT(*) AS c FROM enquiry_outreach WHERE staff_id = ?",
                (s["id"],),
            ).fetchone()["c"]
            msgs = conn.execute(
                "SELECT COUNT(*) AS c FROM staff_messages WHERE staff_id = ?",
                (s["id"],),
            ).fetchone()["c"]
            updates = conn.execute(
                "SELECT COUNT(*) AS c FROM case_updates WHERE author_id = ?",
                (s["id"],),
            ).fetchone()["c"]
            staff_rows.append(
                {
                    **dict(s),
                    "cases_assigned": assigned,
                    "whatsapp_outreach": outreach,
                    "partner_messages": msgs,
                    "client_updates": updates,
                }
            )

        recent_updates = conn.execute(
            "SELECT cu.*, u.name AS author_name, u.role AS author_role, c.case_no "
            "FROM case_updates cu "
            "LEFT JOIN users u ON u.id = cu.author_id "
            "JOIN cases c ON c.id = cu.case_id "
            "ORDER BY cu.id DESC LIMIT 12"
        ).fetchall()
        recent_audit = conn.execute(
            "SELECT a.*, u.name AS user_name, u.role AS user_role "
            "FROM audit_logs a LEFT JOIN users u ON u.id = a.user_id "
            "ORDER BY a.id DESC LIMIT 20"
        ).fetchall()
        consultations = conn.execute(
            "SELECT co.*, cl.name AS client_name, c.case_no "
            "FROM consultations co "
            "JOIN users cl ON cl.id = co.client_id "
            "LEFT JOIN cases c ON c.id = co.case_id "
            "ORDER BY co.id DESC LIMIT 10"
        ).fetchall()
        drafts_pending = conn.execute(
            "SELECT COUNT(*) AS c FROM drafts WHERE status = 'pending'"
        ).fetchone()["c"]
        docs_needed = conn.execute(
            "SELECT COUNT(*) AS c FROM doc_requests WHERE status = 'needed'"
        ).fetchone()["c"]

        # Simple monthly-ish buckets from invoice/enquiry created_at if present
        # Enquiries by source for pie chart
        source_rows = conn.execute(
            "SELECT COALESCE(source_page, 'other') AS source, COUNT(*) AS c "
            "FROM enquiries GROUP BY source ORDER BY c DESC"
        ).fetchall()

        return {
            "role_counts": role_counts,
            "cases": case_rows,
            "status_counts": status_counts,
            "invoices": [dict(i) for i in invoices],
            "revenue_paid": revenue_paid,
            "revenue_due": revenue_due,
            "enquiries": [dict(e) for e in enquiries],
            "lead_total": lead_total,
            "lead_new": lead_new,
            "lead_contacted": lead_contacted,
            "lead_converted": lead_converted,
            "lead_closed": lead_closed,
            "lead_satisfied": lead_satisfied,
            "conversion_rate": conversion_rate,
            "satisfaction_rate": satisfaction_rate,
            "partners": partner_rows,
            "staff": staff_rows,
            "recent_updates": [dict(u) for u in recent_updates],
            "recent_audit": [dict(a) for a in recent_audit],
            "consultations": [dict(co) for co in consultations],
            "drafts_pending": drafts_pending,
            "docs_needed": docs_needed,
            "avg_progress": (
                int(round(sum(r["progress"] for r in case_rows) / len(case_rows)))
                if case_rows
                else 0
            ),
            "chart_case_status": {
                "labels": list(status_counts.keys()) or ["No cases"],
                "data": list(status_counts.values()) or [0],
            },
            "chart_leads": {
                "labels": ["New", "Contacted", "Converted", "Closed"],
                "data": [lead_new, lead_contacted, lead_converted, lead_closed],
            },
            "chart_revenue": {
                "labels": ["Received", "Outstanding"],
                "data": [round(revenue_paid), round(revenue_due)],
            },
            "chart_sources": {
                "labels": [r["source"] for r in source_rows] or ["none"],
                "data": [r["c"] for r in source_rows] or [0],
            },
            "chart_partner_load": {
                "labels": [p["name"].split("—")[0].strip()[:20] for p in partner_rows]
                or ["None"],
                "cases": [p["case_count"] for p in partner_rows] or [0],
                "revenue": [p["revenue"] for p in partner_rows] or [0],
            },
        }
    finally:
        conn.close()
