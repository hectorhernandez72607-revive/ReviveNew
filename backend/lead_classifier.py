"""
AI-based "is this a lead?" classifier for email ingestion.
Uses OpenAI to filter incoming emails: only those likely to be sales leads
(inquiries, interest in services) are created as leads. Newsletters, receipts,
notifications, etc. are skipped.

Set OPENAI_API_KEY in .env to enable. If unset, all parsed emails are treated as leads.
"""

from __future__ import annotations

import os
import re

BATCH_SIZE = 5
DEFAULT_MODEL = "gpt-4o-mini"

# Strong lead signals: if these appear in subject/body (and it's not bulk/marketing), treat as lead.
CODEWORDS = (
    "pricing", "quote", "quotation", "cost", "rates", "availability",
    "book", "booking", "schedule", "demo", "consultation", "estimate",
    "proposal", "package", "services", "options", "turnaround time",
    "timeline", "event", "launch", "campaign", "project", "deadline",
    "upcoming", "planned", "this month", "next week", "q1", "q2", "q3", "q4",
    "interested in", "looking for", "need help with", "can you provide",
    "would like to know", "do you offer", "are you available",
    "what are your rates", "how much does it cost", "who handles",
    "can we talk",
)

# Hard exclusions: if ANY of these appear in subject/body, never treat as lead. Checked before AI.
EXCLUDE_TERMS = (
    "unsubscribe", "newsletter", "spam", "job application", "resume",
    "careers", "support ticket", "complaint", "refund", "cancellation",
    "password reset", "verify your", "confirm your", "click to verify",
    "receipt", "order confirmation", "your order", "order #", "shipped",
    "tracking number", "shipping confirmation", "delivery update",
    "digest", "weekly digest", "daily digest", "roundup", "round-up",
    "promo", "promotion", "marketing", "flash sale", "limited time",
    "otp", "verification code", "one-time password", "login alert",
    "someone tried", "new sign-in", "security alert", "suspicious activity",
    "no-reply", "noreply", "donotreply", "do not reply", "mailer-daemon",
    "mailing list", "out of office", "out-of-office", "ooo", "automatic reply",
    "automated", "notification@", "alert@", "bounce@", "welcome to",
    "sign up", "signup", "you signed up", "confirm your email",
    "click here to", "view in browser", "view this email",
    "invitation to connect", "linkedin", "wants to connect",
    "facebook", "twitter", "instagram", "social media",
    "invoice", "payment received", "payment due", "subscription",
    "your account", "account update", "terms of service", "privacy policy",
    # Subscription / newsletter footers (often past first 700 chars)
    "manage preferences", "manage subscription", "email preferences",
    "you're receiving this because", "you are receiving this because",
    "update your preferences", "unsubscribe from", "preferences center",
    "remove from list", "sent to you because", "update subscription",
    # Meeting / calendar / forwards / non-sales
    "reminder", "meeting invite", "meeting invitation", "calendar invite",
    "invited you to", "you're invited", "event invite", "rsvp",
    "forwarded", "fwd:", "fwd :",
    "thread", "conversation", "internal", "cc:", "bcc:",
    "survey", "feedback request", "please take our survey",
    "scheduled for", "reschedule", "meeting scheduled", "zoom", "teams meeting",
    "google calendar", "outlook calendar", "add to calendar", "add to your calendar",
)

# Sender addresses containing any of these are never leads (bots, no-reply, system).
EXCLUDE_SENDER_PATTERNS = (
    "no-reply", "noreply", "donotreply", "do-not-reply", "no_reply",
    "notification", "notifications", "alert", "alerts", "mailer-daemon",
    "postmaster", "bounce", "bounces", "auto@", "automated@", "system@",
    "newsletter", "news@", "marketing@", "promo@", "digest@", "mailer@",
    "calendar", "reminders", "invite",
)


def _is_sender_excluded(em: dict) -> bool:
    """True if From address looks like a bot, no-reply, or system sender."""
    addr = (em.get("email") or "").lower().strip()
    if not addr or "@" not in addr:
        return True  # invalid sender → not a lead
    local, _, domain = addr.partition("@")
    combined = local + " " + domain
    return any(p in combined for p in EXCLUDE_SENDER_PATTERNS)


def _is_excluded(em: dict) -> bool:
    """True if subject/body contain EXCLUDE_TERMS or sender is excluded (case-insensitive)."""
    if _is_sender_excluded(em):
        return True
    subj = (em.get("subject") or "").lower()
    body = (em.get("body_snippet") or "").lower()
    combined = subj + " " + body
    return any(term in combined for term in EXCLUDE_TERMS)


def _build_prompt(emails: list[dict]) -> str:
    blocks = []
    for i, em in enumerate(emails, 1):
        from_ = f"{em.get('name') or '?'} <{em.get('email') or '?'}>"
        subj = (em.get("subject") or "")[:250]
        body = (em.get("body_snippet") or "")[:600]
        blocks.append(f"--- Email {i} ---\nFROM: {from_}\nSUBJECT: {subj}\nBODY: {body}")
    emails_text = "\n\n".join(blocks)
    return """You are a very strict lead classifier for a small business. Your default is NO. When in doubt, say NO.

Say YES only when ALL of these are true:
- The email is clearly from a real person (not a bot, system, or automated sender).
- The sender is directly asking the business for something commercial: a quote, pricing, availability, a demo, a booking, or to buy/use the business's product or service.
- The email clearly shows intent to do business (e.g. mentions pricing, quote, availability, demo, booking, "interested in", "how much", "can we schedule", "would like to hire").
- It reads like a 1:1 sales inquiry from a potential customer, not a notification, forward, or general chitchat.

Always say NO for:
- Newsletters, digests, marketing, promos, receipts, order confirmations, shipping/tracking.
- Verification emails, OTP, login alerts, password reset, "confirm your email".
- Job applications, support tickets, complaints, refund requests, cancellations.
- Social network messages (LinkedIn, etc.), "view in browser", "unsubscribe".
- Automated notifications, alerts, no-reply senders, mailing list messages, out-of-office.
- Meeting invites, calendar invites, "you're invited", RSVPs, "scheduled for", reschedule, Zoom/Teams links.
- Forwards (Fwd:), reply chains, internal threads, "following up" without a clear sales ask.
- Surveys, feedback requests, "quick question", "just checking in", "touch base" without a concrete business request.
- Anything bulk, templated, or where the sender is not clearly a potential customer asking to buy or get a quote.

If the email could be a notification, forward, meeting invite, or non-sales message, say NO. Only say YES when you are confident it is a direct sales lead (someone asking for a quote, booking, or to use the service).

For each email below, reply with exactly one word per line: YES or NO, in the same order (line 1 = Email 1, line 2 = Email 2, ...). No other text.

""" + emails_text + """

Your reply (one word per line, YES or NO only):"""


def _parse_yes_no_lines(text: str, expected: int) -> list[bool]:
    """Parse YES/NO from model output. Returns list of bools; on parse issues, treat as False (exclude)."""
    results: list[bool] = []
    for line in (text or "").strip().splitlines():
        line = line.strip().upper()
        if not line:
            continue
        if line in ("YES", "Y"):
            results.append(True)
        elif line in ("NO", "N"):
            results.append(False)
        else:
            m = re.match(r"^(YES|NO|Y|N)\b", line, re.I)
            if m:
                results.append(m.group(1).upper() in ("YES", "Y"))
            else:
                results.append(False)  # exclude on ambiguity
    while len(results) < expected:
        results.append(False)
    return results[:expected]


def classify_leads(
    emails: list[dict],
    api_key: str | None = None,
    model: str | None = None,
) -> list[bool]:
    """
    Classify each email as lead (True) or not (False). Same length and order as emails.
    Emails containing EXCLUDE_TERMS (e.g. unsubscribe, newsletter, spam) are always False.
    If api_key is missing/empty or API errors, those emails are NOT added as leads (safe default).
    """
    if not emails:
        return []
    excluded = [_is_excluded(em) for em in emails]
    to_classify = [(i, em) for i, em in enumerate(emails) if not excluded[i]]

    if not to_classify:
        return [False] * len(emails)

    key = (api_key or os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        print("[lead_classifier] OPENAI_API_KEY not set. Not adding any emails as leads.")
        return [False] * len(emails)

    try:
        import openai
    except ImportError:
        print("[lead_classifier] openai not installed. pip install openai. Not adding any emails as leads.")
        return [False] * len(emails)

    model = (model or os.getenv("OPENAI_MODEL") or DEFAULT_MODEL).strip()
    emails_to_run = [em for _, em in to_classify]
    ai_results: list[bool] = []

    for i in range(0, len(emails_to_run), BATCH_SIZE):
        batch = emails_to_run[i : i + BATCH_SIZE]
        prompt = _build_prompt(batch)
        try:
            client = openai.OpenAI(api_key=key)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0,
            )
            raw = (resp.choices[0].message.content or "").strip()
            batch_results = _parse_yes_no_lines(raw, len(batch))
            ai_results.extend(batch_results)
        except Exception as e:
            print(f"[lead_classifier] OpenAI error: {e}. Not adding this batch as leads.")
            ai_results.extend([False] * len(batch))

    result = [False] * len(emails)
    for k, (idx, _) in enumerate(to_classify):
        result[idx] = ai_results[k]
    return result
