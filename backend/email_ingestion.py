"""
Ingest leads from email (Gmail IMAP). No domain required.
Configure IMAP_EMAIL + IMAP_APP_PASSWORD in .env. Leads are parsed from
unread emails and created for the client specified by IMAP_CLIENT_SLUG.
"""

import imaplib
import email
import re
import os
from email.header import decode_header
from email.message import Message


# Match US-style phone numbers (optional spacing, dashes, parens)
PHONE_RE = re.compile(
    r"\+?1?[-.\s]?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    r"|"
    r"\b[2-9]\d{2}[-.\s]?\d{3}[-.\s]?\d{4}\b"
)


def _decode_mime(s: str | None) -> str:
    if not s:
        return ""
    if isinstance(s, bytes):
        return s.decode("utf-8", errors="replace")
    return str(s)


def _decode_header_value(val: str | None) -> str:
    if not val:
        return ""
    try:
        parts = decode_header(val or "")
    except Exception:
        return (val or "")[:500]
    out = []
    for p, charset in parts:
        if p is None:
            continue
        if isinstance(p, bytes):
            out.append(p.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(str(p))
    return " ".join(out).strip()


def _parse_from(raw: str) -> tuple[str, str]:
    """Extract (name, email) from From header."""
    name, addr = "", ""
    raw = _decode_header_value(raw)
    m = re.search(r"<([^>]+)>", raw)
    if m:
        addr = m.group(1).strip().lower()
        name = re.sub(r"\s*<[^>]+>\s*", "", raw).strip().strip('"')
    else:
        addr = raw.strip().lower()
        if "@" in addr:
            name = addr.split("@")[0]
    if not addr or "@" not in addr:
        addr = ""
    name = (name or "Unknown").strip()[:200]
    return (name, addr)


def _extract_phone(body: str) -> str:
    m = PHONE_RE.search(body)
    return (m.group(0).strip() if m else "")[:50]


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace for use in body text."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _get_body(msg: Message) -> str:
    """Extract full body text. For multipart, combines text/plain and stripped text/html
    so the classifier sees complete content (many emails put the real message only in HTML).
    """
    plain_parts: list[str] = []
    html_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        plain_parts.append(payload.decode("utf-8", errors="replace"))
                except Exception:
                    pass
            elif ctype == "text/html":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        html_parts.append(payload.decode("utf-8", errors="replace"))
                except Exception:
                    pass
        plain = " ".join(plain_parts).strip()
        html_text = " ".join(_strip_html(h) for h in html_parts).strip()
        if plain and html_text:
            body = f"{plain} {html_text}"
        else:
            body = plain or html_text
    else:
        body = ""
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                raw = payload.decode("utf-8", errors="replace")
                if (msg.get_content_type() or "").lower() == "text/html":
                    body = _strip_html(raw)
                else:
                    body = raw
        except Exception:
            pass
    return body


IMAP_DEFAULT_TIMEOUT = 15  # seconds
IMAP_PORT = 993


def fetch_unread_emails(
    imap_email: str,
    imap_password: str,
    host: str = "imap.gmail.com",
    mailbox: str = "INBOX",
    timeout: int = IMAP_DEFAULT_TIMEOUT,
    max_messages: int | None = None,
) -> list[dict]:
    """
    Connect via IMAP, fetch unread emails, parse into lead-like dicts.
    Returns list of {"name", "email", "phone", "message_id", "subject"}.
    If max_messages is set, stop after that many (e.g. 20 for Check email).
    """
    results = []
    print(f"[email_ingestion] Connecting to {host}:{IMAP_PORT} (timeout={timeout}s)...")
    mail = imaplib.IMAP4_SSL(host, IMAP_PORT, timeout=timeout)
    try:
        print("[email_ingestion] Logging in...")
        mail.login(imap_email, imap_password)
        print("[email_ingestion] Selecting mailbox, fetching UNSEEN...")
        mail.select(mailbox)
        _, data = mail.search(None, "UNSEEN")
        if not data or not data[0]:
            print("[email_ingestion] No unread emails.")
            return results
        ids = data[0].split()
        print(f"[email_ingestion] Found {len(ids)} unread message(s).")
        for uid in ids:
            if max_messages is not None and len(results) >= max_messages:
                break
            try:
                _, msg_data = mail.fetch(uid, "(RFC822)")
                if not msg_data:
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw) if isinstance(raw, bytes) else email.message_from_string(raw)
                message_id = (msg.get("Message-ID") or "").strip()
                if not message_id:
                    message_id = f"uid-{uid.decode() if isinstance(uid, bytes) else uid}"
                from_h = msg.get("From") or ""
                subj = _decode_header_value(msg.get("Subject") or "")
                body = _get_body(msg)
                name, email_addr = _parse_from(from_h)
                phone = _extract_phone(body)
                if not email_addr:
                    email_addr = "unknown@email.invalid"
                results.append({
                    "name": name or "Unknown",
                    "email": email_addr,
                    "phone": phone,
                    "message_id": message_id,
                    "subject": subj[:500],
                    "body_snippet": (body or "")[:2000].strip(),
                })
            except Exception as e:
                print(f"[email_ingestion] Skip message {uid}: {e}")
                continue
    finally:
        try:
            mail.logout()
        except Exception:
            pass
    print(f"[email_ingestion] Done. Parsed {len(results)} email(s).")
    return results


def mark_as_read(
    imap_email: str,
    imap_password: str,
    message_ids: list[str],
    host: str = "imap.gmail.com",
    mailbox: str = "INBOX",
    timeout: int = IMAP_DEFAULT_TIMEOUT,
) -> None:
    """Mark messages as read by Message-ID. Best-effort; not critical for dedup."""
    if not message_ids:
        return
    mail = imaplib.IMAP4_SSL(host, IMAP_PORT, timeout=timeout)
    try:
        mail.login(imap_email, imap_password)
        mail.select(mailbox)
        _, data = mail.search(None, "UNSEEN")
        if not data or not data[0]:
            return
        for uid in data[0].split():
            try:
                _, msg_data = mail.fetch(uid, "(RFC822)")
                if not msg_data:
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw) if isinstance(raw, bytes) else email.message_from_string(raw)
                mid = (msg.get("Message-ID") or "").strip()
                if mid in message_ids:
                    mail.store(uid, "+FLAGS", "\\Seen")
            except Exception:
                pass
    finally:
        try:
            mail.logout()
        except Exception:
            pass
