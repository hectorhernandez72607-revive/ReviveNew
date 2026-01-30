"""
SMS/Message Service Module
Handles sending follow-up SMS via Twilio. Same schedule as email (24h first, then weekly).
Used for leads that come in through messages (source=Messages).
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Twilio client is lazy-initialized so backend starts without Twilio configured
_twilio_client = None


def _get_twilio_client():
    global _twilio_client
    if _twilio_client is not None:
        return _twilio_client
    sid = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
    token = (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
    if not sid or not token:
        return None
    try:
        from twilio.rest import Client
        _twilio_client = Client(sid, token)
        return _twilio_client
    except Exception:
        return None


FROM_PHONE = (os.getenv("TWILIO_PHONE_NUMBER") or "").strip()
SENDER_NAME = os.getenv("SENDER_NAME", "Your Business")

# SMS-friendly templates (short; subject line not used in SMS)
SMS_FOLLOWUP_TEMPLATES = [
    "Hi {name}, just following up on your message. Do you have any questions? Happy to help — {sender_name}",
    "Hi {name}, checking in — still here if you need anything. — {sender_name}",
    "Hi {name}, last note from me. Reach out anytime if you'd like to connect. — {sender_name}",
]


def generate_followup_sms_copy(
    lead_name: str,
    followup_number: int,
    sender_name: str,
    inquiry_body: str | None = None,
    is_weekly: bool = False,
) -> str | None:
    """
    Generate a short SMS follow-up body (no subject). Prefer OpenAI for first message
    when inquiry_body is set; otherwise use template. Returns plain string body or None.
    """
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        template_idx = min(followup_number, len(SMS_FOLLOWUP_TEMPLATES) - 1)
        t = SMS_FOLLOWUP_TEMPLATES[template_idx]
        return t.format(name=lead_name or "there", sender_name=sender_name or SENDER_NAME)

    try:
        import openai
    except ImportError:
        template_idx = min(followup_number, len(SMS_FOLLOWUP_TEMPLATES) - 1)
        return SMS_FOLLOWUP_TEMPLATES[template_idx].format(
            name=lead_name or "there", sender_name=sender_name or SENDER_NAME
        )

    model = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
    has_inquiry = bool((inquiry_body or "").strip())

    if is_weekly:
        prompt = f"""Write one short SMS (under 160 chars) from a business to a potential customer. Gentle check-in, we've reached out before. No hype.
Lead name: {lead_name}. Sender: {sender_name}.
Reply with only the SMS body, no quotes, no SUBJECT:."""
    elif has_inquiry and followup_number == 0:
        snippet = (inquiry_body or "")[:300].strip()
        prompt = f"""Write one short SMS reply (under 160 chars) from a business to someone who texted. Acknowledge their message and offer to help.
What they said: {snippet}
Lead name: {lead_name}. Sender: {sender_name}.
Reply with only the SMS body, no quotes."""
    else:
        which = ["first", "second", "third"][min(followup_number, 2)]
        prompt = f"""Write one short follow-up SMS (under 160 chars) from a business. This is the {which} follow-up; they haven't replied. Friendly, one clear ask.
Lead name: {lead_name}. Sender: {sender_name}.
Reply with only the SMS body, no quotes."""

    try:
        client = openai.OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.7,
        )
        body = (resp.choices[0].message.content or "").strip().strip('"').strip("'")[:320]
        return body if body else None
    except Exception as e:
        print(f"[message_service] OpenAI error: {e}. Using template.")
        template_idx = min(followup_number, len(SMS_FOLLOWUP_TEMPLATES) - 1)
        return SMS_FOLLOWUP_TEMPLATES[template_idx].format(
            name=lead_name or "there", sender_name=sender_name or SENDER_NAME
        )


def send_followup_sms(
    to_phone: str,
    lead_name: str,
    followup_number: int = 0,
    body: str | None = None,
    inquiry_body: str | None = None,
    is_weekly: bool = False,
) -> dict:
    """
    Send a follow-up SMS. If body is provided (e.g. from AI), use it; otherwise generate
    (optionally inquiry-aware when inquiry_body is set, or weekly when is_weekly=True).
    Returns {"success": bool, "message" | "error": str, "sid": str?}.
    """
    client = _get_twilio_client()
    from_phone = FROM_PHONE
    if not client or not from_phone:
        print("WARNING: Twilio not configured (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER). SMS not sent.")
        return {"success": False, "error": "Twilio not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER in .env."}

    to_phone = (to_phone or "").strip()
    if not to_phone:
        return {"success": False, "error": "No phone number"}

    # E.164: if US 10-digit, add +1
    if to_phone.isdigit() and len(to_phone) == 10:
        to_phone = "+1" + to_phone
    elif not to_phone.startswith("+"):
        to_phone = "+" + to_phone

    if not body:
        body = generate_followup_sms_copy(
            lead_name=lead_name,
            followup_number=followup_number,
            sender_name=SENDER_NAME,
            inquiry_body=inquiry_body,
            is_weekly=is_weekly,
        ) or SMS_FOLLOWUP_TEMPLATES[min(followup_number, len(SMS_FOLLOWUP_TEMPLATES) - 1)].format(
            name=lead_name or "there", sender_name=SENDER_NAME
        )

    body = (body or "")[:320]  # Twilio limit 1600; keep SMS short

    try:
        msg = client.messages.create(body=body, from_=from_phone, to=to_phone)
        sid = getattr(msg, "sid", None) or (msg.get("sid") if isinstance(msg, dict) else None)
        print(f"SMS followup sent to {to_phone} (followup #{followup_number + 1}, sid={sid})")
        return {"success": True, "message": f"SMS sent to {to_phone}", "sid": sid}
    except Exception as e:
        print(f"Failed to send SMS to {to_phone}: {e}")
        return {"success": False, "error": str(e)}
