from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from jose import jwt
import bcrypt
import datetime
import socket
import sqlite3
import os
import re

# Load environment variables
load_dotenv()

# Import email service
from email_service import send_followup_email, send_test_email, generate_followup_copy, send_autoreply_lead
from email_service import SENDER_EMAIL, SENDER_NAME
from email_ingestion import fetch_unread_emails, mark_as_read
from lead_classifier import classify_leads
from message_service import send_followup_sms

DB_PATH = os.getenv("DATABASE_PATH", "leads.db")
DEFAULT_CLIENT_SLUG = "demo"
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7  # 1 week

# Security: test endpoints only when explicitly enabled; optional admin key
ENABLE_TEST_ENDPOINTS = os.getenv("ENABLE_TEST_ENDPOINTS", "").lower() == "true"
ADMIN_API_KEY = (os.getenv("ADMIN_API_KEY") or "").strip()
CORS_ORIGINS_RAW = os.getenv("CORS_ORIGINS", "*")
CORS_ORIGINS = [o.strip() for o in CORS_ORIGINS_RAW.split(",") if o.strip()] or ["*"]

# Weak JWT secrets (warn on startup)
WEAK_JWT_SECRETS = ("dev-secret-change-in-production", "your-random-secret-here")

security = HTTPBearer(auto_error=False)


def _require_admin_or_test_enabled(request: Request):
    """Test endpoints: enabled only when ENABLE_TEST_ENDPOINTS=true and (if ADMIN_API_KEY set) header matches."""
    if not ENABLE_TEST_ENDPOINTS:
        raise HTTPException(status_code=404, detail="Not Found")
    if ADMIN_API_KEY:
        key = request.headers.get("X-Admin-Key", "").strip()
        if key != ADMIN_API_KEY:
            raise HTTPException(status_code=403, detail="Admin key required")


def _hash_password(password: str) -> str:
    raw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

LEAD_COLS = "id, client_id, name, email, phone, status, created_at, last_contacted, followups_sent, source, revenue, inquiry_subject, inquiry_body"


# --- DB helpers (per-request connections) ---

def _slug_from_email(email: str) -> str:
    """Generate a unique-ish slug from email for new user's client."""
    local = email.split("@")[0] if "@" in email else email
    safe = re.sub(r"[^a-z0-9]", "", local.lower()) or "user"
    return safe[:32]


# Domains Resend won't let you send *from* (unverified). Use SENDER_EMAIL from .env instead.
FREE_EMAIL_DOMAINS = (
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "outlook.com",
    "hotmail.com", "live.com", "icloud.com", "me.com", "mac.com", "aol.com",
    "mail.com", "protonmail.com", "zoho.com", "yandex.com", "gmx.com",
)


def _is_free_email_domain(email: str | None) -> bool:
    """True if email is from a free provider we can't use as Resend sender."""
    if not email or "@" not in email:
        return False
    domain = email.strip().lower().split("@")[-1]
    return domain in FREE_EMAIL_DOMAINS


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT
        )
        """)
        try:
            c.execute("ALTER TABLE clients ADD COLUMN user_id INTEGER REFERENCES users(id)")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE clients ADD COLUMN signature_block TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE clients ADD COLUMN contact_phone TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE clients ADD COLUMN pricing TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE clients ADD COLUMN saved_info TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN imap_app_password TEXT")
        except sqlite3.OperationalError:
            pass
        c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            phone TEXT,
            status TEXT,
            created_at TEXT,
            last_contacted TEXT,
            followups_sent INTEGER,
            source TEXT DEFAULT 'Manual'
        )
        """)
        try:
            c.execute("ALTER TABLE leads ADD COLUMN source TEXT DEFAULT 'Manual'")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE leads ADD COLUMN client_id INTEGER REFERENCES clients(id)")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE leads ADD COLUMN revenue REAL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE leads ADD COLUMN inquiry_subject TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE leads ADD COLUMN inquiry_body TEXT")
        except sqlite3.OperationalError:
            pass
        conn.commit()

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM clients WHERE slug = ?", (DEFAULT_CLIENT_SLUG,))
        row = c.fetchone()
        if not row:
            now = datetime.datetime.now().isoformat()
            c.execute(
                "INSERT INTO clients (slug, name, created_at) VALUES (?, ?, ?)",
                (DEFAULT_CLIENT_SLUG, "Demo Client", now),
            )
            conn.commit()
            default_id = c.lastrowid
        else:
            default_id = row[0]
        c.execute("UPDATE leads SET client_id = ? WHERE client_id IS NULL", (default_id,))
        conn.commit()
        try:
            c.execute("CREATE INDEX IF NOT EXISTS idx_leads_client_id ON leads(client_id)")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        c.execute("""
            CREATE TABLE IF NOT EXISTS processed_email_ids (
                message_id TEXT PRIMARY KEY,
                lead_id INTEGER NOT NULL,
                client_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS processed_sms_ids (
                message_sid TEXT PRIMARY KEY,
                lead_id INTEGER NOT NULL,
                client_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        c = conn.cursor()
        yield (conn, c)
    finally:
        conn.close()


def _row_to_lead(row: tuple) -> dict:
    # ORDER: id, client_id, name, email, phone, status, created_at, last_contacted, followups_sent, source, revenue, inquiry_subject, inquiry_body
    return {
        "id": row[0],
        "client_id": row[1],
        "name": row[2],
        "email": row[3],
        "phone": row[4],
        "status": row[5],
        "created_at": row[6],
        "last_contacted": row[7],
        "followups_sent": row[8],
        "source": row[9] if len(row) > 9 else "Manual",
        "revenue": float(row[10]) if len(row) > 10 else 0.0,
        "inquiry_subject": row[11] if len(row) > 11 else None,
        "inquiry_body": row[12] if len(row) > 12 else None,
    }


def _row_to_client(r) -> dict:
    return {
        "id": r[0], "slug": r[1], "name": r[2], "created_at": r[3],
        "signature_block": r[4] if len(r) > 4 else None,
        "contact_phone": r[5] if len(r) > 5 else None,
        "pricing": r[6] if len(r) > 6 else None,
        "saved_info": r[7] if len(r) > 7 else None,
    }


def _fetch_clients(cursor) -> list[dict]:
    cursor.execute("SELECT id, slug, name, created_at, signature_block, contact_phone, pricing, saved_info FROM clients ORDER BY name")
    return [_row_to_client(r) for r in cursor.fetchall()]


def _get_client_by_slug(cursor, slug: str) -> dict | None:
    cursor.execute("SELECT id, slug, name, created_at, signature_block, contact_phone, pricing, saved_info FROM clients WHERE slug = ?", (slug,))
    r = cursor.fetchone()
    return _row_to_client(r) if r else None


def _get_client_by_id(cursor, client_id: int) -> dict | None:
    cursor.execute("SELECT id, slug, name, created_at, signature_block, contact_phone, pricing, saved_info FROM clients WHERE id = ?", (client_id,))
    r = cursor.fetchone()
    return _row_to_client(r) if r else None


def _get_user_by_id(cursor, user_id: int) -> dict | None:
    cursor.execute(
        "SELECT id, email, password_hash, created_at, imap_app_password FROM users WHERE id = ?",
        (user_id,),
    )
    r = cursor.fetchone()
    if not r:
        return None
    return {
        "id": r[0],
        "email": r[1],
        "password_hash": r[2],
        "created_at": r[3],
        "imap_app_password": r[4] if len(r) > 4 else None,
    }


def _get_user_by_email(cursor, email: str) -> dict | None:
    cursor.execute(
        "SELECT id, email, password_hash, created_at, imap_app_password FROM users WHERE email = ?",
        (email.lower().strip(),),
    )
    r = cursor.fetchone()
    if not r:
        return None
    return {
        "id": r[0],
        "email": r[1],
        "password_hash": r[2],
        "created_at": r[3],
        "imap_app_password": r[4] if len(r) > 4 else None,
    }


def _get_users_with_imap(cursor) -> list[dict]:
    """Users who have imap_app_password set, with their client id and slug for ingestion."""
    cursor.execute(
        """
        SELECT u.id, u.email, u.imap_app_password, c.id AS client_id, c.slug AS client_slug
        FROM users u
        JOIN clients c ON c.user_id = u.id
        WHERE u.imap_app_password IS NOT NULL AND TRIM(u.imap_app_password) != ''
        """
    )
    rows = cursor.fetchall()
    return [
        {
            "id": r[0],
            "email": r[1],
            "imap_app_password": r[2],
            "client_id": r[3],
            "client_slug": r[4],
        }
        for r in rows
    ]


def _get_client_by_user_id(cursor, user_id: int) -> dict | None:
    cursor.execute("SELECT id, slug, name, created_at, signature_block, contact_phone, pricing, saved_info FROM clients WHERE user_id = ?", (user_id,))
    r = cursor.fetchone()
    return _row_to_client(r) if r else None


def _get_user_by_client_id(cursor, client_id: int) -> dict | None:
    """Get the user who owns a client (via client.user_id)."""
    cursor.execute("SELECT user_id FROM clients WHERE id = ?", (client_id,))
    r = cursor.fetchone()
    if not r or not r[0]:
        return None
    user_id = r[0]
    return _get_user_by_id(cursor, user_id)


def _fetch_leads_by_client(cursor, client_id: int) -> list[dict]:
    cursor.execute(
        f"SELECT {LEAD_COLS} FROM leads WHERE client_id = ? ORDER BY id",
        (client_id,),
    )
    return [_row_to_lead(row) for row in cursor.fetchall()]


def _get_lead_by_id_and_client(cursor, lead_id: int, client_id: int) -> dict | None:
    cursor.execute(
        f"SELECT {LEAD_COLS} FROM leads WHERE id = ? AND client_id = ?",
        (lead_id, client_id),
    )
    row = cursor.fetchone()
    return _row_to_lead(row) if row else None


def _update_lead(lead: dict, conn: sqlite3.Connection):
    c = conn.cursor()
    c.execute("""
        UPDATE leads
        SET status = ?, last_contacted = ?, followups_sent = ?
        WHERE id = ?
    """, (
        lead["status"],
        lead["last_contacted"],
        lead["followups_sent"],
        lead["id"],
    ))
    conn.commit()


def _create_lead(
    client_id: int,
    name: str,
    email: str,
    phone: str,
    source: str,
    conn: sqlite3.Connection,
    cursor,
    inquiry_subject: str | None = None,
    inquiry_body: str | None = None,
) -> dict:
    """Create a lead for the given client. For email leads, pass inquiry_subject and inquiry_body."""
    now = datetime.datetime.now().isoformat()
    subj = (inquiry_subject or "")[:500] if inquiry_subject else None
    body = (inquiry_body or "")[:2000] if inquiry_body else None
    cursor.execute("""
        INSERT INTO leads (
            client_id, name, email, phone, status, created_at, last_contacted, followups_sent, source, revenue, inquiry_subject, inquiry_body
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (client_id, name, email, phone or "", "new", now, None, 0, source, 0.0, subj, body))
    conn.commit()
    lead_id = cursor.lastrowid
    return {
        "id": lead_id,
        "client_id": client_id,
        "name": name,
        "email": email,
        "phone": phone or "",
        "status": "new",
        "created_at": now,
        "last_contacted": None,
        "followups_sent": 0,
        "source": source,
        "revenue": 0.0,
        "inquiry_subject": subj,
        "inquiry_body": body,
    }


def _send_autoreply_for_new_lead(conn, c, client_id: int, lead: dict) -> None:
    """Send instant autoreply to the lead's email. From = verified sender + client name; Reply-To = client owner email. Best-effort; logs on failure."""
    email_addr = (lead.get("email") or "").strip()
    if not email_addr or "@" not in email_addr or "@lead.local" in email_addr.lower():
        return
    client = _get_client_by_id(c, client_id)
    if not client:
        return
    contact_phone = (client.get("contact_phone") or "").strip() or None
    # Display as from the client (business name); replies go to owner email
    display_name = (client.get("name") or "").strip() or SENDER_NAME
    user = _get_user_by_client_id(c, client_id)
    reply_to_email = (user.get("email") or "").strip() if user else None
    if reply_to_email and "@" not in reply_to_email:
        reply_to_email = None
    client_pricing = (client.get("pricing") or "").strip() or None
    client_saved_info = (client.get("saved_info") or "").strip() or None
    signature_block = (client.get("signature_block") or "").strip() or None
    try:
        result = send_autoreply_lead(
            email_addr,
            lead.get("name") or "there",
            contact_phone,
            sender_name=display_name,
            sender_email=SENDER_EMAIL,
            inquiry_subject=lead.get("inquiry_subject"),
            inquiry_body=lead.get("inquiry_body"),
            reply_to=reply_to_email,
            client_pricing=client_pricing,
            client_saved_info=client_saved_info,
            bcc=reply_to_email,
            signature_block=signature_block,
        )
        if not result.get("success"):
            print(f"[autoreply] Failed to send to {email_addr}: {result.get('error', 'unknown')}")
    except Exception as e:
        print(f"[autoreply] Error sending to {email_addr}: {e}")


# --- Follow-up logic ---

def _parse_created_at(created_at: str | None):
    """Parse created_at from DB (handles ISO with T or space, None). Returns datetime or None."""
    if created_at is None:
        return None
    s = (created_at.strip() if isinstance(created_at, str) else str(created_at)).strip()
    if not s:
        return None
    # SQLite / different locales may use space instead of T
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)
    try:
        return datetime.datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def is_older_than_24_hours(created_at: str | None) -> bool:
    """True if the given datetime (e.g. lead created_at) is at least 24 hours ago."""
    t = _parse_created_at(created_at)
    if t is None:
        return False
    return t <= datetime.datetime.now() - datetime.timedelta(hours=24)


def is_older_than_7_days_since(last_contacted: str | None) -> bool:
    """True if last_contacted is at least 7 days ago. Used for weekly follow-up."""
    if not last_contacted:
        return False
    t = datetime.datetime.fromisoformat(last_contacted) if isinstance(last_contacted, str) else last_contacted
    return t <= datetime.datetime.now() - datetime.timedelta(days=7)


def followup(lead: dict, conn: sqlite3.Connection, from_email: str | None = None, from_name: str | None = None, signature_block: str = "") -> bool:
    """
    Send the first (and only scheduled) follow-up: 24h after lead creation if the client
    hasn't already contacted. Sends via SMS for source=Messages (when phone present),
    otherwise via email. Content is AI-generated from the lead's inquiry when available.
    Further touchpoints are weekly follow-ups only (7 days after last contact).
    Returns True if message was sent, False otherwise.
    """
    followups_sent = lead.get("followups_sent")
    if followups_sent is None:
        followups_sent = 0
    # Only send the single 24h follow-up; no 24h-after-1st or 24h-after-2nd
    if followups_sent != 0:
        return False
    if lead.get("last_contacted"):
        contact = lead.get("phone") or lead.get("email") or "lead"
        print(f"[followup] Skip {contact}: client already contacted.")
        return False
    if not is_older_than_24_hours(lead.get("created_at")):
        contact = lead.get("phone") or lead.get("email") or "lead"
        print(f"[followup] Skip {contact}: created_at not old enough (created_at={lead.get('created_at')}).")
        return False

    sender_name = from_name or os.getenv("SENDER_NAME", "Your Business")
    use_sms = lead.get("source") == "Messages" and (lead.get("phone") or "").strip()

    if use_sms:
        to_contact = lead["phone"]
        print(f"[followup] Sending 24h SMS follow-up to {to_contact} (lead id={lead.get('id')})...")
        result = send_followup_sms(
            to_phone=lead["phone"],
            lead_name=lead["name"],
            followup_number=lead["followups_sent"],
            body=None,
            inquiry_body=lead.get("inquiry_body"),
            is_weekly=False,
        )
    else:
        to_contact = lead["email"]
        print(f"[followup] Sending 24h email follow-up to {to_contact} (lead id={lead.get('id')})...")
        ai_copy = generate_followup_copy(
            lead_name=lead["name"],
            followup_number=lead["followups_sent"],
            sender_name=sender_name,
            lead_source=lead.get("source"),
            inquiry_subject=lead.get("inquiry_subject"),
            inquiry_body=lead.get("inquiry_body"),
        )
        if ai_copy:
            result = send_followup_email(
                to_email=lead["email"],
                lead_name=lead["name"],
                followup_number=lead["followups_sent"],
                from_email=from_email,
                from_name=from_name,
                subject=ai_copy["subject"],
                body_plain=ai_copy["body"],
                signature_block=signature_block or None,
            )
        else:
            result = send_followup_email(
                to_email=lead["email"],
                lead_name=lead["name"],
                followup_number=lead["followups_sent"],
                from_email=from_email,
                from_name=from_name,
                signature_block=signature_block or None,
            )

    if result["success"]:
        lead["last_contacted"] = datetime.datetime.now().isoformat()
        lead["followups_sent"] += 1
        lead["status"] = "waiting"
        _update_lead(lead, conn)
        print(f"✅ Auto followup #{lead['followups_sent']} sent to {to_contact}")
        return True
    else:
        print(f"❌ Failed to send followup to {to_contact}: {result.get('error', 'Unknown error')}")
        return False


def reminder(lead: dict):
    if lead["status"] == "new":
        print("you have a new lead!")


def autofollow(lead: dict):
    if is_older_than_24_hours(lead["created_at"]):
        lead["status"] = "auto-followup"


def weekly_followup(
    lead: dict,
    conn: sqlite3.Connection,
    from_email: str | None = None,
    from_name: str | None = None,
    signature_block: str = "",
) -> bool:
    """
    Send a weekly check-in when it's been 7+ days since last_contacted.
    Sends via SMS for source=Messages (when phone present), otherwise via email.
    Returns True if sent.
    """
    sender_name = from_name or os.getenv("SENDER_NAME", "Your Business")
    use_sms = lead.get("source") == "Messages" and (lead.get("phone") or "").strip()

    if use_sms:
        result = send_followup_sms(
            to_phone=lead["phone"],
            lead_name=lead["name"],
            followup_number=2,
            body=None,
            inquiry_body=lead.get("inquiry_body"),
            is_weekly=True,
        )
    else:
        ai_copy = generate_followup_copy(
            lead_name=lead["name"],
            followup_number=2,
            sender_name=sender_name,
            lead_source=lead.get("source"),
            inquiry_subject=lead.get("inquiry_subject"),
            inquiry_body=lead.get("inquiry_body"),
            is_weekly=True,
        )
        if ai_copy:
            result = send_followup_email(
                to_email=lead["email"],
                lead_name=lead["name"],
                followup_number=2,
                from_email=from_email,
                from_name=from_name,
                subject=ai_copy["subject"],
                body_plain=ai_copy["body"],
                signature_block=signature_block or None,
            )
        else:
            result = send_followup_email(
                to_email=lead["email"],
                lead_name=lead["name"],
                followup_number=2,
                from_email=from_email,
                from_name=from_name,
                signature_block=signature_block or None,
            )
    if result["success"]:
        lead["last_contacted"] = datetime.datetime.now().isoformat()
        lead["followups_sent"] = lead.get("followups_sent", 0) + 1
        _update_lead(lead, conn)
        contact = lead.get("phone") or lead.get("email")
        print(f"✅ Weekly follow-up sent to {contact}")
        return True
    return False


def _run_followups_for_client(client_id: int, client_slug: str):
    """Run follow-up logic for a single client's leads. Uses the client's user email as sender."""
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        c = conn.cursor()
        leads = _fetch_leads_by_client(c, client_id)
        client = _get_client_by_id(c, client_id)
        client_name = client["name"] if client else None
        signature_block = (client.get("signature_block") or "").strip() if client else ""
        user = _get_user_by_client_id(c, client_id)
        from_email = user["email"] if user else None
        from_name = client_name or (user["email"].split("@")[0] if user else None)
        # Resend rejects sending *from* Gmail/Yahoo etc. Use SENDER_EMAIL from .env for those.
        if _is_free_email_domain(from_email):
            from_email = None  # fall back to SENDER_EMAIL (e.g. onboarding@resend.dev)
        # from_name is still used as display name

    eligible = [l for l in leads if (l.get("followups_sent") or 0) == 0 and l.get("status") != "recovered"]
    if eligible:
        print(f"[followup] Client '{client_slug}': {len(leads)} leads, {len(eligible)} eligible for 24h follow-up.")

    for lead in leads:
        if lead["status"] == "recovered":
            continue
        if lead["status"] == "new":
            reminder(lead)
        # One scheduled follow-up at 24h after lead creation (if client hasn't contacted)
        if (lead.get("followups_sent") or 0) == 0:
            with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
                if followup(lead, conn, from_email=from_email, from_name=from_name, signature_block=signature_block):
                    continue  # sent; followup() already updated lead
        # Weekly follow-up: 7+ days since last contact (any number of follow-ups already sent)
        if is_older_than_7_days_since(lead.get("last_contacted")):
            with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
                c2 = conn.cursor()
                lead_refresh = _get_lead_by_id_and_client(c2, lead["id"], client_id)
                if lead_refresh:
                    if weekly_followup(lead_refresh, conn, from_email=from_email, from_name=from_name, signature_block=signature_block):
                        pass  # already updated in weekly_followup


def central_loop():
    """Run follow-up logic for each client separately."""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        clients = _fetch_clients(c)
    for client in clients:
        _run_followups_for_client(client["id"], client["slug"])


def _run_ingestion_for_inbox(
    imap_email: str,
    imap_password: str,
    client_slug: str,
    timeout_s: int,
    max_messages: int | None = None,
) -> dict:
    """Ingest one inbox; returns {ok, error?, created, client_slug}. Never raises."""
    try:
        old_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(timeout_s)
            with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
                c = conn.cursor()
                client = _get_client_by_slug(c, client_slug)
                if not client:
                    print(f"[email_ingestion] Client '{client_slug}' not found. Skip.")
                    return {"ok": False, "error": f"Client '{client_slug}' not found", "created": 0}

                emails = fetch_unread_emails(
                    imap_email, imap_password, timeout=timeout_s,
                    max_messages=max_messages,
                )
                print(f"[email_ingestion] Fetched {len(emails)} unread email(s) for {client_slug}.")
                if os.getenv("OPENAI_API_KEY", "").strip():
                    n_before = len(emails)
                    pred = classify_leads(emails)
                    emails = [e for e, is_lead in zip(emails, pred) if is_lead]
                    print(f"[email_ingestion] Classifier kept {len(emails)} of {n_before} emails as leads.")
                    if pred and not all(pred):
                        print(f"[email_ingestion] AI classifier filtered to {len(emails)} likely lead(s).")
                created = 0
                processed_ids: list[str] = []

                for em in emails:
                    message_id = (em.get("message_id") or "").strip()
                    if not message_id:
                        continue
                    c.execute("SELECT 1 FROM processed_email_ids WHERE message_id = ?", (message_id,))
                    if c.fetchone():
                        continue
                    name = (em.get("name") or "Unknown").strip()[:200]
                    email_addr = (em.get("email") or "").strip()
                    phone = (em.get("phone") or "").strip()[:50]
                    if not email_addr or "@" not in email_addr:
                        email_addr = "unknown@email.invalid"
                    lead = _create_lead(
                        client["id"],
                        name,
                        email_addr,
                        phone,
                        "Email",
                        conn,
                        c,
                        inquiry_subject=em.get("subject"),
                        inquiry_body=em.get("body_snippet"),
                    )
                    _send_autoreply_for_new_lead(conn, c, client["id"], lead)
                    now = datetime.datetime.now().isoformat()
                    c.execute(
                        "INSERT INTO processed_email_ids (message_id, lead_id, client_id, created_at) VALUES (?, ?, ?, ?)",
                        (message_id, lead["id"], client["id"], now),
                    )
                    conn.commit()
                    created += 1
                    processed_ids.append(message_id)
                    print(f"[email_ingestion] Lead from email: {name} ({email_addr})")

                if processed_ids:
                    try:
                        mark_as_read(imap_email, imap_password, processed_ids, timeout=timeout_s)
                    except Exception as e:
                        print(f"[email_ingestion] Mark-as-read failed: {e}")

                return {"ok": True, "created": created, "client_slug": client_slug}
        finally:
            socket.setdefaulttimeout(old_timeout)
    except (socket.timeout, TimeoutError) as e:
        err = str(e)
        print(f"[email_ingestion] Timeout: {err}")
        return {"ok": False, "error": "IMAP connection timed out. Check network and Gmail access.", "created": 0}
    except Exception as e:
        err = str(e)
        print(f"[email_ingestion] Error: {err}")
        if "Authentication failed" in err or "LOGIN" in err.upper() or "invalid credentials" in err.lower():
            err = "IMAP login failed. Use a Gmail App Password (not your normal password)."
        elif "timed out" in err.lower() or "timeout" in err.lower():
            err = "IMAP connection timed out. Check network and Gmail access."
        return {"ok": False, "error": err, "created": 0}


def run_email_ingestion(
    request_timeout_s: int | None = None,
    client_slug_override: str | None = None,
    user_id_override: int | None = None,
) -> dict:
    """
    Ingest leads from IMAP (Gmail). Uses per-user credentials when available.

    - request_timeout_s: if set (e.g. 20), run in a thread and return within that time (manual "Check email").
    - client_slug_override + user_id_override: manual run for one user; uses that user's stored Gmail App Password.
    - When neither override: scheduler run; loops over all users with imap_app_password set and ingests each inbox.
    """
    timeout_s = 15
    try:
        t = os.getenv("IMAP_TIMEOUT", "15").strip()
        if t:
            timeout_s = max(5, min(120, int(t)))
    except (TypeError, ValueError):
        pass

    # Manual run: one user's inbox (dashboard "Check email" button)
    if (client_slug_override or "").strip() and user_id_override is not None:
        with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
            c = conn.cursor()
            user = _get_user_by_id(c, user_id_override)
            if not user or not (user.get("imap_app_password") or "").strip():
                return {"ok": False, "error": "Set your Gmail App Password in Settings to check email.", "created": 0}
            imap_email = user["email"]
            imap_password = (user.get("imap_app_password") or "").strip()
            client_slug = (client_slug_override or "").strip()

        def _do() -> dict:
            return _run_ingestion_for_inbox(
                imap_email, imap_password, client_slug, timeout_s,
                max_messages=20 if request_timeout_s is not None else None,
            )

        if request_timeout_s is not None and request_timeout_s > 0:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_do)
                try:
                    return fut.result(timeout=request_timeout_s)
                except FuturesTimeoutError:
                    print("[email_ingestion] Request timed out (thread).")
                    return {"ok": False, "error": "IMAP request timed out. Check network and Gmail (App Password, IMAP enabled).", "created": 0}
        return _do()

    # Scheduler run: all users who have IMAP configured
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        c = conn.cursor()
        users = _get_users_with_imap(c)
    if not users:
        print("[email_ingestion] No users with Gmail App Password set. Skip.")
        return {"ok": True, "created": 0}

    def _mask_email(e: str) -> str:
        if not e or "@" not in e:
            return "***"
        local, at, domain = e.partition("@")
        return (local[:2] + "***" + at + domain) if len(local) > 2 else ("***" + at + domain)

    masked = [_mask_email(u.get("email") or "") for u in users]
    print(f"[email_ingestion] Scheduler run: {len(users)} user(s) with IMAP configured: {masked}.")

    total_created = 0
    for u in users:
        result = _run_ingestion_for_inbox(
            u["email"], u["imap_app_password"], u["client_slug"], timeout_s, max_messages=None
        )
        total_created += result.get("created", 0)
        if not result.get("ok"):
            print(f"[email_ingestion] Inbox {u['email']}: {result.get('error', 'unknown')}")
    print(f"[email_ingestion] Email ingestion run finished. Total leads created: {total_created}.")
    return {"ok": True, "created": total_created}


# --- Pydantic model for POST /lead ---

class LeadCreate(BaseModel):
    name: str
    email: str
    phone: str = ""


class WebhookLeadCreate(BaseModel):
    name: str
    email: str
    phone: str = ""
    source: str = "Unknown"  # Track where the lead came from


class ClientCreate(BaseModel):
    slug: str
    name: str


class ClientUpdate(BaseModel):
    signature_block: str | None = None  # Contact/signature block appended to follow-up emails
    contact_phone: str | None = None  # Phone number shown in instant autoreply to new leads
    pricing: str | None = None  # Pricing info; included in instant autoreply when lead asks for it
    saved_info: str | None = None  # Saved info; AI may integrate in instant reply when relevant to inquiry


class ImapSettingsUpdate(BaseModel):
    imap_app_password: str | None = None  # Gmail App Password; empty/null clears it


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class LeadUpdate(BaseModel):
    status: str | None = None
    revenue: float | None = None
    mark_contacted: bool | None = None  # When True, set last_contacted to now (skips auto follow-up)


def _create_jwt(user_id: int) -> str:
    exp = datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": str(user_id), "exp": exp},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def _decode_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    db: tuple = Depends(get_db),
):
    if not creds or creds.scheme != "Bearer":
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = _decode_jwt(creds.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    conn, c = db
    user = _get_user_by_id(c, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    client = _get_client_by_user_id(c, user_id)
    if not client:
        raise HTTPException(status_code=403, detail="No client associated with account")
    safe_user = {
        "id": user["id"],
        "email": user["email"],
        "imap_configured": bool(user.get("imap_app_password")),
    }
    return {"user": safe_user, "client": client}


# --- Lifespan: init DB, start scheduler ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Database: {DB_PATH}")
    init_db()
    if JWT_SECRET in WEAK_JWT_SECRETS or len(JWT_SECRET) < 32:
        print("⚠️  SECURITY: Set a strong JWT_SECRET in .env (e.g. openssl rand -hex 32)")
    if ENABLE_TEST_ENDPOINTS:
        print("⚠️  TEST ENDPOINTS enabled. Set ENABLE_TEST_ENDPOINTS=false in production.")
    scheduler = BackgroundScheduler()
    scheduler.add_job(central_loop, "interval", hours=1)
    scheduler.add_job(run_email_ingestion, "interval", minutes=2)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Routes ---

@app.post("/auth/signup")
def signup(body: SignupRequest, db: tuple = Depends(get_db)):
    """
    Shared sign-up link: partner sends this to paying clients.
    Creates user + client, returns JWT. Frontend stores token and redirects to dashboard.
    """
    conn, c = db
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email required")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    existing = _get_user_by_email(c, email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    now = datetime.datetime.now().isoformat()
    password_hash = _hash_password(body.password)
    c.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
        (email, password_hash, now),
    )
    conn.commit()
    user_id = c.lastrowid
    base_slug = _slug_from_email(email)
    slug = f"{base_slug}-{user_id}"
    c.execute(
        "INSERT INTO clients (slug, name, created_at, user_id) VALUES (?, ?, ?, ?)",
        (slug, email, now, user_id),
    )
    conn.commit()
    token = _create_jwt(user_id)
    user = _get_user_by_id(c, user_id)
    client = _get_client_by_user_id(c, user_id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user["id"], "email": user["email"], "imap_configured": False},
        "client": {"id": client["id"], "slug": client["slug"], "name": client["name"], "signature_block": client.get("signature_block") or "", "contact_phone": client.get("contact_phone") or "", "pricing": client.get("pricing") or "", "saved_info": client.get("saved_info") or ""},
    }


@app.post("/auth/login")
def login(body: LoginRequest, db: tuple = Depends(get_db)):
    """Login with email + password. Returns JWT."""
    conn, c = db
    email = body.email.strip().lower()
    user = _get_user_by_email(c, email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not _verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    client = _get_client_by_user_id(c, user["id"])
    if not client:
        raise HTTPException(status_code=403, detail="No client associated with account")
    token = _create_jwt(user["id"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user["id"], "email": user["email"], "imap_configured": bool(user.get("imap_app_password"))},
        "client": {"id": client["id"], "slug": client["slug"], "name": client["name"], "signature_block": client.get("signature_block") or "", "contact_phone": client.get("contact_phone") or "", "pricing": client.get("pricing") or "", "saved_info": client.get("saved_info") or ""},
    }


@app.get("/me")
def me(current: dict = Depends(get_current_user)):
    """Current user + their client. Requires Authorization: Bearer <token>."""
    return current


@app.patch("/me/client")
def update_my_client(
    body: ClientUpdate,
    current: dict = Depends(get_current_user),
    db: tuple = Depends(get_db),
):
    """Update the authenticated user's client (signature block, contact phone, pricing, saved info for autoreply)."""
    conn, c = db
    client_id = current["client"]["id"]
    if body.signature_block is None and body.contact_phone is None and body.pricing is None and body.saved_info is None:
        return _client_safe(current["client"])
    if body.signature_block is not None:
        signature_block = (body.signature_block or "").strip()[:2000] or None
        c.execute("UPDATE clients SET signature_block = ? WHERE id = ?", (signature_block, client_id))
    if body.contact_phone is not None:
        contact_phone = (body.contact_phone or "").strip()[:50] or None
        c.execute("UPDATE clients SET contact_phone = ? WHERE id = ?", (contact_phone, client_id))
    if body.pricing is not None:
        pricing = (body.pricing or "").strip()[:2000] or None
        c.execute("UPDATE clients SET pricing = ? WHERE id = ?", (pricing, client_id))
    if body.saved_info is not None:
        saved_info = (body.saved_info or "").strip()[:2000] or None
        c.execute("UPDATE clients SET saved_info = ? WHERE id = ?", (saved_info, client_id))
    conn.commit()
    updated = _get_client_by_id(c, client_id)
    return _client_safe(updated) if updated else current["client"]


def _client_safe(client: dict) -> dict:
    """Return client dict with optional fields for API response."""
    return {
        "id": client["id"],
        "slug": client["slug"],
        "name": client["name"],
        "signature_block": client.get("signature_block") or "",
        "contact_phone": client.get("contact_phone") or "",
        "pricing": client.get("pricing") or "",
        "saved_info": client.get("saved_info") or "",
    }


@app.patch("/me/imap-settings")
def update_my_imap_settings(
    body: ImapSettingsUpdate,
    current: dict = Depends(get_current_user),
    db: tuple = Depends(get_db),
):
    """Store or clear the authenticated user's Gmail App Password for email lead ingestion."""
    conn, c = db
    user_id = current["user"]["id"]
    value = (body.imap_app_password or "").strip() or None
    c.execute("UPDATE users SET imap_app_password = ? WHERE id = ?", (value, user_id))
    conn.commit()
    return {"imap_configured": bool(value)}


@app.get("/me/ingestion-status")
def get_ingestion_status(current: dict = Depends(get_current_user)):
    """Return whether email ingestion is configured and a short message for the dashboard."""
    user = current.get("user") or {}
    client = current.get("client")
    imap_configured = bool(user.get("imap_configured"))
    client_slug = (client.get("slug") if client else None) or None
    if not client:
        message = "No client linked to your account. Contact support."
    elif not imap_configured:
        message = "Save your Gmail App Password in Settings to enable email lead ingestion."
    else:
        message = "Ingestion is active. Unread emails are checked every 2 minutes."
    return {"imap_configured": imap_configured, "client_slug": client_slug, "message": message}


@app.get("/me/leads")
def get_my_leads(
    current: dict = Depends(get_current_user),
    db: tuple = Depends(get_db),
):
    """Leads for the authenticated user's client."""
    conn, c = db
    return _fetch_leads_by_client(c, current["client"]["id"])


@app.post("/me/lead")
def add_my_lead(
    body: LeadCreate,
    current: dict = Depends(get_current_user),
    db: tuple = Depends(get_db),
):
    """Add a lead to the authenticated user's client."""
    conn, c = db
    lead = _create_lead(
        current["client"]["id"],
        body.name,
        body.email,
        body.phone,
        "Manual",
        conn,
        c,
    )
    _send_autoreply_for_new_lead(conn, c, current["client"]["id"], lead)
    return lead


@app.patch("/me/lead/{lead_id}")
def update_my_lead(
    lead_id: int,
    body: LeadUpdate,
    current: dict = Depends(get_current_user),
    db: tuple = Depends(get_db),
):
    """Update a lead's status and/or revenue (e.g. mark recovered). Lead must belong to user's client."""
    conn, c = db
    client_id = current["client"]["id"]
    lead = _get_lead_by_id_and_client(c, lead_id, client_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    updates = []
    params = []
    if body.status is not None:
        updates.append("status = ?")
        params.append(body.status)
    if body.revenue is not None:
        updates.append("revenue = ?")
        params.append(body.revenue)
    if body.mark_contacted is True:
        updates.append("last_contacted = ?")
        params.append(datetime.datetime.now().isoformat())
        # So the lead no longer shows as "new" — they've been contacted
        if body.status is None and lead.get("status") != "recovered":
            updates.append("status = ?")
            params.append("waiting")
    if not updates:
        return lead
    params.append(lead_id)
    c.execute(
        f"UPDATE leads SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
    return _get_lead_by_id_and_client(c, lead_id, client_id)


@app.delete("/me/lead/{lead_id}")
def delete_my_lead(
    lead_id: int,
    current: dict = Depends(get_current_user),
    db: tuple = Depends(get_db),
):
    """Delete a lead. Lead must belong to user's client."""
    conn, c = db
    client_id = current["client"]["id"]
    lead = _get_lead_by_id_and_client(c, lead_id, client_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    c.execute("DELETE FROM processed_email_ids WHERE lead_id = ?", (lead_id,))
    c.execute("DELETE FROM processed_sms_ids WHERE lead_id = ?", (lead_id,))
    c.execute("DELETE FROM leads WHERE id = ? AND client_id = ?", (lead_id, client_id))
    conn.commit()
    return {"ok": True, "deleted": lead_id}


@app.post("/me/test-followup")
def me_test_followup(
    current: dict = Depends(get_current_user),
    db: tuple = Depends(get_db),
):
    """
    Run the full follow-up test for the authenticated user's client: send test email
    to signup email, add an old lead, run follow-ups. No slug required.
    """
    conn, c = db
    client = current["client"]
    user = current["user"]
    to_email = user["email"]

    # 1. Send test email
    result = send_test_email(to_email)
    if not result.get("success"):
        raise HTTPException(
            status_code=502,
            detail=result.get("error", "Failed to send test email. Check RESEND_API_KEY."),
        )

    # 2. Add old lead (25h ago) with owner's email
    old_time = (datetime.datetime.now() - datetime.timedelta(hours=25)).isoformat()
    c.execute("""
        INSERT INTO leads (
            client_id, name, email, phone, status, created_at, last_contacted, followups_sent, source, revenue, inquiry_subject, inquiry_body
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        client["id"],
        "Test Old Lead",
        to_email,
        "",
        "new",
        old_time,
        None,
        0,
        "Test",
        0.0,
        None,
        None,
    ))
    conn.commit()
    print(f"Test: Added old lead for client {client['slug']}, email={to_email}")

    # 3. Run follow-up job for this client only
    _run_followups_for_client(client["id"], client["slug"])

    return {
        "success": True,
        "email": to_email,
        "message": "Test email and follow-up sent. Check your inbox.",
    }


@app.post("/me/run-email-ingestion")
def me_run_email_ingestion(current: dict = Depends(get_current_user)):
    """
    Trigger email lead ingestion (IMAP). Uses the logged-in user's stored Gmail App
    Password (set in Settings); leads go to their client. Returns within ~20s or times out.
    """
    slug = (current.get("client") or {}).get("slug") or ""
    user_id = (current.get("user") or {}).get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    out = run_email_ingestion(request_timeout_s=20, client_slug_override=slug, user_id_override=user_id)
    if not out.get("ok"):
        raise HTTPException(status_code=502, detail=out.get("error", "Email ingestion failed"))
    return out


@app.get("/clients")
def list_clients(db: tuple = Depends(get_db)):
    conn, c = db
    return _fetch_clients(c)


@app.get("/clients/{client_slug}")
def get_client(client_slug: str, db: tuple = Depends(get_db)):
    conn, c = db
    client = _get_client_by_slug(c, client_slug)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@app.post("/clients")
def create_client(body: ClientCreate, db: tuple = Depends(get_db)):
    """Create a new client (paying customer). Use slug in URLs: ?client=slug"""
    conn, c = db
    existing = _get_client_by_slug(c, body.slug)
    if existing:
        raise HTTPException(status_code=400, detail="Client slug already exists")
    now = datetime.datetime.now().isoformat()
    c.execute(
        "INSERT INTO clients (slug, name, created_at) VALUES (?, ?, ?)",
        (body.slug, body.name, now),
    )
    conn.commit()
    return {"id": c.lastrowid, "slug": body.slug, "name": body.name, "created_at": now}


@app.get("/clients/{client_slug}/leads")
def get_client_leads(client_slug: str, db: tuple = Depends(get_db)):
    conn, c = db
    client = _get_client_by_slug(c, client_slug)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return _fetch_leads_by_client(c, client["id"])


@app.post("/clients/{client_slug}/lead")
def add_client_lead(client_slug: str, body: LeadCreate, db: tuple = Depends(get_db)):
    conn, c = db
    client = _get_client_by_slug(c, client_slug)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    lead = _create_lead(client["id"], body.name, body.email, body.phone, "Manual", conn, c)
    _send_autoreply_for_new_lead(conn, c, client["id"], lead)
    return lead


@app.post("/webhook/lead/{client_slug}")
def webhook_add_lead(client_slug: str, body: WebhookLeadCreate, db: tuple = Depends(get_db)):
    """
    Per-client webhook for Google Forms, etc. Each paying client has their own URL:
    POST /webhook/lead/{client_slug}
    """
    conn, c = db
    client = _get_client_by_slug(c, client_slug)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    lead = _create_lead(
        client["id"],
        body.name,
        body.email,
        body.phone,
        body.source,
        conn,
        c,
    )
    _send_autoreply_for_new_lead(conn, c, client["id"], lead)
    print(f"Webhook [{client_slug}]: Lead from {body.source} - {body.name} ({body.email})")
    return lead


@app.post("/webhook/twilio/sms")
def webhook_twilio_sms(
    From: str = Form(..., alias="From"),
    Body: str = Form(..., alias="Body"),
    MessageSid: str = Form(..., alias="MessageSid"),
    db: tuple = Depends(get_db),
):
    """
    Twilio incoming SMS webhook. Creates a lead from the message.
    Configure this URL in Twilio: Phone Numbers → your number → Messaging → "A MESSAGE COMES IN" → Webhook.
    Set TWILIO_CLIENT_SLUG in .env to the client that should receive these leads.
    """
    conn, c = db
    client_slug = (os.getenv("TWILIO_CLIENT_SLUG") or os.getenv("IMAP_CLIENT_SLUG") or DEFAULT_CLIENT_SLUG).strip()
    client = _get_client_by_slug(c, client_slug)
    if not client:
        print(f"[twilio_sms] Client '{client_slug}' not found. Skipping.")
        return {"ok": False, "error": "Client not found"}

    # Dedupe by MessageSid
    c.execute("SELECT 1 FROM processed_sms_ids WHERE message_sid = ?", (MessageSid.strip(),))
    if c.fetchone():
        return {"ok": True, "created": False, "message": "Already processed"}

    # Normalize phone: Twilio sends E.164 e.g. +15551234567
    from_phone = (From or "").strip()
    body_text = (Body or "").strip()[:2000]
    name = "SMS Lead"  # Could parse "Name: ..." from body or use AI later
    # SMS-only leads may not have email; use placeholder so DB stays valid
    email_placeholder = f"sms-{from_phone.replace('+', '').replace(' ', '')}@lead.local"

    lead = _create_lead(
        client["id"],
        name,
        email_placeholder,
        from_phone,
        "Messages",
        conn,
        c,
        inquiry_subject=None,
        inquiry_body=body_text,
    )
    now = datetime.datetime.now().isoformat()
    c.execute(
        "INSERT INTO processed_sms_ids (message_sid, lead_id, client_id, created_at) VALUES (?, ?, ?, ?)",
        (MessageSid.strip(), lead["id"], client["id"], now),
    )
    conn.commit()
    print(f"[twilio_sms] Lead from message: {from_phone} -> client {client_slug} (lead_id={lead['id']})")
    return {"ok": True, "created": True, "lead_id": lead["id"]}


# ==============================================================================
# TEST ENDPOINTS - Require ENABLE_TEST_ENDPOINTS=true; optional X-Admin-Key header
# ==============================================================================

def _admin_dep(request: Request):
    _require_admin_or_test_enabled(request)


@app.post("/test/run-followups")
def test_run_followups(_: None = Depends(_admin_dep)):
    """
    Manually trigger the followup loop for testing.
    Run this after adding an old lead to see if followups work.
    """
    print("--- Running followup loop (manual trigger) ---")
    central_loop()
    print("--- Followup loop complete ---")
    return {"message": "Followup loop executed. Check the terminal for logs."}


@app.post("/test/run-followups-for-client")
def test_run_followups_for_client(
    client_slug: str = DEFAULT_CLIENT_SLUG,
    db: tuple = Depends(get_db),
    _: None = Depends(_admin_dep),
):
    """
    Run follow-ups for a single client only. Use after add-old-lead to test 24h follow-up.
    Usage: POST /test/run-followups-for-client?client_slug=hectorhernandez72607-2
    """
    conn, c = db
    client = _get_client_by_slug(c, client_slug)
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_slug}' not found")
    print(f"--- Running followup for client '{client_slug}' only ---")
    _run_followups_for_client(client["id"], client_slug)
    print("--- Done ---")
    return {"message": f"Followup run for client '{client_slug}'. Check the terminal for logs."}


@app.post("/test/run-email-ingestion")
def test_run_email_ingestion(_: None = Depends(_admin_dep)):
    """
    Manually trigger email lead ingestion. Reads unread emails from IMAP inbox,
    creates leads for the client in IMAP_CLIENT_SLUG. Requires IMAP_EMAIL and
    IMAP_APP_PASSWORD in .env.
    """
    print("--- Running email ingestion (manual trigger) ---")
    out = run_email_ingestion()
    print(f"--- Email ingestion complete: {out.get('created', 0)} created ---")
    return out


@app.post("/test/send-email")
def test_send_email(to_email: str, _: None = Depends(_admin_dep)):
    """
    Send a test email to verify Resend is configured correctly.
    Usage: POST /test/send-email?to_email=your@email.com
    """
    result = send_test_email(to_email)
    return result


@app.get("/test/client-slug-by-email")
def test_client_slug_by_email(
    email: str,
    db: tuple = Depends(get_db),
    _: None = Depends(_admin_dep),
):
    """
    Resolve client slug from owner's signup email. Use for automation (e.g. test script with --email).
    Usage: GET /test/client-slug-by-email?email=you@example.com
    """
    conn, c = db
    user = _get_user_by_email(c, email.strip().lower())
    if not user:
        raise HTTPException(status_code=404, detail=f"No account found for '{email}'")
    client = _get_client_by_user_id(c, user["id"])
    if not client:
        raise HTTPException(status_code=404, detail=f"No client for account '{email}'")
    return {"client_slug": client["slug"], "email": user["email"]}


@app.post("/test/send-email-to-owner")
def test_send_email_to_owner(
    client_slug: str = DEFAULT_CLIENT_SLUG,
    db: tuple = Depends(get_db),
    _: None = Depends(_admin_dep),
):
    """
    Send a test email to the client owner's signup email.
    Usage: POST /test/send-email-to-owner?client_slug=demo
    """
    conn, c = db
    client = _get_client_by_slug(c, client_slug)
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_slug}' not found")
    user = _get_user_by_client_id(c, client["id"])
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"Client '{client_slug}' has no owner. Sign up with that client first.",
        )
    to_email = user["email"]
    result = send_test_email(to_email)
    if result.get("success"):
        result["email"] = to_email
    return result


@app.post("/test/send-followup-email")
def test_send_followup_email(
    to_email: str,
    name: str = "Test User",
    template_number: int = 0,
    _: None = Depends(_admin_dep),
):
    """
    Send a specific follow-up template to test how it looks.
    Usage: POST /test/send-followup-email?to_email=your@email.com&name=John&template_number=0
    template_number: 0 = first followup, 1 = second, 2 = third
    """
    result = send_followup_email(to_email, name, template_number)
    return result


@app.post("/test/add-old-lead")
def test_add_old_lead(
    client_slug: str = DEFAULT_CLIENT_SLUG,
    email: str | None = None,
    db: tuple = Depends(get_db),
    _: None = Depends(_admin_dep),
):
    """
    Add a lead with a created_at timestamp from 25 hours ago.
    Use ?client_slug=demo (or another client) to target a client.
    Use ?email=you@example.com to override; if omitted, uses the client owner's signup email.
    """
    conn, c = db
    client = _get_client_by_slug(c, client_slug)
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_slug}' not found")
    if email is not None and (email := email.strip()):
        lead_email = email
    else:
        user = _get_user_by_client_id(c, client["id"])
        if not user:
            raise HTTPException(
                status_code=400,
                detail=f"Client '{client_slug}' has no owner. Sign up first or pass ?email=...",
            )
        lead_email = user["email"]
    old_time = (datetime.datetime.now() - datetime.timedelta(hours=25)).isoformat()
    c.execute("""
        INSERT INTO leads (
            client_id, name, email, phone, status, created_at, last_contacted, followups_sent, source, revenue, inquiry_subject, inquiry_body
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        client["id"],
        "Test Old Lead",
        lead_email,
        "",
        "new",
        old_time,
        None,
        0,
        "Test",
        0.0,
        None,
        None,
    ))
    conn.commit()
    lead_id = c.lastrowid
    print(f"Test: Added old lead (ID: {lead_id}) for client {client_slug}, email={lead_email}, created_at = {old_time}")
    return {
        "id": lead_id,
        "client_id": client["id"],
        "name": "Test Old Lead",
        "email": lead_email,
        "status": "new",
        "created_at": old_time,
        "message": "Lead created. Call POST /test/run-followups to test auto-followup.",
    }


# ==============================================================================
# END OF TEST ENDPOINTS
# ==============================================================================

# Serve frontend (signup, login, dashboard) so the "link" works at http://localhost:8000/
_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
