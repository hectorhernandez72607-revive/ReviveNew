"""
Email Service Module
Handles sending follow-up emails using Resend API with customizable templates.
"""

import os
import resend
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize Resend with API key from environment
resend.api_key = os.getenv("RESEND_API_KEY", "")

# Your sender email (must be verified in Resend dashboard)
# For testing, Resend provides: onboarding@resend.dev
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "onboarding@resend.dev")
SENDER_NAME = os.getenv("SENDER_NAME", "Your Business")


# ==============================================================================
# EMAIL TEMPLATES
# ==============================================================================

FOLLOWUP_TEMPLATES = [
    # Template 1: First follow-up (24 hours)
    {
        "subject": "Quick follow-up on your inquiry, {name}!",
        "html": """
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #2563eb; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f9fafb; padding: 20px; border-radius: 0 0 8px 8px; }}
        .button {{ display: inline-block; background: #2563eb; color: white; padding: 12px 24px; 
                   text-decoration: none; border-radius: 6px; margin-top: 15px; }}
        .footer {{ margin-top: 20px; font-size: 12px; color: #6b7280; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>Thanks for reaching out!</h2>
        </div>
        <div class="content">
            <p>Hi {name},</p>
            
            <p>I noticed you recently submitted an inquiry, and I wanted to personally follow up to see if you have any questions.</p>
            
            <p>I'd love to help you with whatever you need. Feel free to reply to this email or let me know a good time for a quick call.</p>
            
            <p>Looking forward to hearing from you!</p>
            
            <p>Best regards,<br>
            <strong>{sender_name}</strong></p>
        </div>
        <div class="footer">
            <p>You received this email because you submitted an inquiry on our website.</p>
        </div>
    </div>
</body>
</html>
""",
        "text": """Hi {name},

I noticed you recently submitted an inquiry, and I wanted to personally follow up to see if you have any questions.

I'd love to help you with whatever you need. Feel free to reply to this email or let me know a good time for a quick call.

Looking forward to hearing from you!

Best regards,
{sender_name}
"""
    },
    
    # Template 2: Second follow-up (48 hours)
    {
        "subject": "Still interested, {name}?",
        "html": """
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #059669; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f9fafb; padding: 20px; border-radius: 0 0 8px 8px; }}
        .footer {{ margin-top: 20px; font-size: 12px; color: #6b7280; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>Just checking in!</h2>
        </div>
        <div class="content">
            <p>Hi {name},</p>
            
            <p>I wanted to follow up on my previous message. I understand you might be busy, but I didn't want you to miss out.</p>
            
            <p>If you're still interested, I'm here to help answer any questions you might have.</p>
            
            <p>Just hit reply and let me know how I can assist!</p>
            
            <p>Best,<br>
            <strong>{sender_name}</strong></p>
        </div>
        <div class="footer">
            <p>You received this email because you submitted an inquiry on our website.</p>
        </div>
    </div>
</body>
</html>
""",
        "text": """Hi {name},

I wanted to follow up on my previous message. I understand you might be busy, but I didn't want you to miss out.

If you're still interested, I'm here to help answer any questions you might have.

Just hit reply and let me know how I can assist!

Best,
{sender_name}
"""
    },
    
    # Template 3: Third follow-up (72 hours)
    {
        "subject": "Last chance to connect, {name}",
        "html": """
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #dc2626; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f9fafb; padding: 20px; border-radius: 0 0 8px 8px; }}
        .footer {{ margin-top: 20px; font-size: 12px; color: #6b7280; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>One last follow-up</h2>
        </div>
        <div class="content">
            <p>Hi {name},</p>
            
            <p>I've reached out a couple of times and haven't heard back. I completely understand if now isn't the right time.</p>
            
            <p>This will be my last email, but please know that I'm always here if you need anything in the future.</p>
            
            <p>Wishing you all the best!</p>
            
            <p>Take care,<br>
            <strong>{sender_name}</strong></p>
        </div>
        <div class="footer">
            <p>You received this email because you submitted an inquiry on our website. We won't send any more follow-ups.</p>
        </div>
    </div>
</body>
</html>
""",
        "text": """Hi {name},

I've reached out a couple of times and haven't heard back. I completely understand if now isn't the right time.

This will be my last email, but please know that I'm always here if you need anything in the future.

Wishing you all the best!

Take care,
{sender_name}
"""
    }
]


# ==============================================================================
# AI FOLLOW-UP COPY GENERATOR
# ==============================================================================

def generate_followup_copy(
    lead_name: str,
    followup_number: int,
    sender_name: str,
    lead_source: str | None = None,
    inquiry_subject: str | None = None,
    inquiry_body: str | None = None,
    is_weekly: bool = False,
) -> dict | None:
    """
    Generate human-sounding follow-up subject and body using OpenAI.
    When inquiry_subject/inquiry_body are provided (e.g. from an email lead), the first
    follow-up is written as a direct response to what they asked about.
    When is_weekly=True, generates a gentle weekly check-in (we've reached out before).
    Returns {"subject": "...", "body": "..."} or None on failure (use template fallback).
    """
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None
    try:
        import openai
    except ImportError:
        return None
    model = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
    which = ["first", "second", "third"][min(followup_number, 2)]
    source_note = f" They came in via {lead_source}." if lead_source and lead_source != "Manual" else ""
    has_inquiry = bool((inquiry_subject or "").strip() or (inquiry_body or "").strip())

    if is_weekly:
        prompt = f"""You are writing a short, human weekly check-in email from a small business owner to a potential customer. We've reached out before and haven't heard back—this is a gentle, non-pushy check-in.

Context:
- Lead's name: {lead_name}
- Sender name: {sender_name}

Write a brief weekly check-in. Rules:
- 2–3 sentences. Friendly, low pressure. "Just checking in" or "Still here if you need anything."
- No guilt or pressure. Subject line under 60 chars (e.g. "Quick check-in" or "Still here when you're ready").

Reply with exactly two lines:
Line 1: SUBJECT: <your subject line>
Line 2: BODY: <your email body>"""
    elif has_inquiry and followup_number == 0:
        # First response to a lead who emailed in: reply directly to what they asked.
        subj_snippet = (inquiry_subject or "")[:200].strip()
        body_snippet = (inquiry_body or "")[:800].strip()
        prompt = f"""You are writing a short, human reply email from a small business owner to someone who just reached out. This is the business's first response to them—so it should directly address what they asked about and sound like a real person, not a template.

What the lead wrote:
- Subject: {subj_snippet or "(no subject)"}
- Message: {body_snippet or "(no message)"}

Context:
- Lead's name: {lead_name}
- Sender (business) name: {sender_name}

Write a single reply email. Rules:
- Reference what they asked (e.g. "Thanks for asking about..." or "Re: [their topic]"). Answer or acknowledge their question and offer a next step (e.g. a quick call, more info, or "let me know if you'd like to...").
- 3–5 short sentences. Warm and professional. No hype or "I wanted to reach out." No marketing fluff.
- Subject line: under 60 chars. Use "Re: ..." or a short reply-style subject that relates to their message.

Reply with exactly two lines:
Line 1: SUBJECT: <your subject line>
Line 2: BODY: <your email body>"""
    else:
        # Later follow-up or no inquiry context: generic check-in.
        prompt = f"""You are writing a short, human follow-up email from a small business owner to a potential customer. Sound like a real person—warm, brief, no marketing fluff.

Context:
- Lead's name: {lead_name}
- This is the {which} follow-up (they haven't replied yet).{source_note}
- Sender name: {sender_name}

Write a single follow-up email. Rules:
- 2–4 sentences max. One clear ask: reply or suggest a time for a quick call.
- No exaggerated claims or hype. No "I wanted to reach out" clichés.
- Subject line: under 60 chars, conversational (e.g. "Quick follow-up" or "Still interested?").

Reply with exactly two lines:
Line 1: SUBJECT: <your subject line>
Line 2: BODY: <your email body>"""

    try:
        client = openai.OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.7,
        )
        raw = (resp.choices[0].message.content or "").strip()
        subject = ""
        body = ""
        for line in raw.splitlines():
            line_stripped = line.strip()
            if line_stripped.upper().startswith("SUBJECT:"):
                subject = line_stripped[8:].strip().strip('"').strip("'")[:200]
            elif line_stripped.upper().startswith("BODY:"):
                body = line_stripped[5:].strip().strip('"').strip("'")[:1500]
        if not body and raw:
            lines = [l.strip() for l in raw.splitlines() if l.strip()]
            if len(lines) >= 1:
                subject = lines[0].strip('"').strip("'")[:200]
            if len(lines) >= 2:
                body = "\n\n".join(lines[1:]).strip()[:1500]
        if subject and body:
            return {"subject": subject, "body": body}
        return None
    except Exception as e:
        print(f"[followup AI] OpenAI error: {e}. Using template.")
        return None


def generate_autoreply_copy(
    lead_name: str,
    sender_name: str,
    inquiry_subject: str | None = None,
    inquiry_body: str | None = None,
    client_pricing: str | None = None,
    client_saved_info: str | None = None,
) -> dict | None:
    """
    Generate a short, AI-tailored instant reply subject and body for a new lead.
    References what they asked about; 1-2 sentences + we're on it. When the lead
    asks about pricing/cost/rates and client_pricing is provided, include that pricing
    in the reply. When client_saved_info is provided, the AI may integrate it when
    relevant to the inquiry. Returns None on failure or when no OpenAI key (caller should use generic autoreply).
    """
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None
    try:
        import openai
    except ImportError:
        return None
    has_inquiry = bool((inquiry_subject or "").strip() or (inquiry_body or "").strip())
    if not has_inquiry:
        return None
    subj_snippet = (inquiry_subject or "")[:150].strip()
    body_snippet = (inquiry_body or "")[:500].strip()
    pricing_note = ""
    if client_pricing and (client_pricing or "").strip():
        pricing_note = f"""
- The business's pricing (use ONLY if the lead asked about price/cost/rates; include it in the body exactly as below):
{client_pricing.strip()[:800]}"""
    saved_info_note = ""
    if client_saved_info and (client_saved_info or "").strip():
        saved_info_note = f"""
- Saved info about the business (use ONLY when the lead's inquiry clearly relates; integrate naturally in 1 short phrase or sentence if relevant—e.g. FAQs, policies, services, availability):
{client_saved_info.strip()[:800]}"""
    model = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
    prompt = f"""You are writing a very short instant-reply email from a small business to someone who just reached out. This is the immediate acknowledgment—reference what they asked and say we're on it. Sound like a real person, not a bot.

What they wrote:
- Subject: {subj_snippet or "(no subject)"}
- Message: {body_snippet or "(no message)"}

Context:
- Lead's name: {lead_name}
- Sender (business) name: {sender_name}{pricing_note}{saved_info_note}

Write a single instant-reply email. Rules:
- 1-2 sentences only (or 3 if you include pricing because they asked, or a short saved-info detail that fits). Acknowledge their message (e.g. "Thanks for asking about..." or "Got your note about..."). If they asked about pricing/cost/rates and pricing was provided above, include that pricing in your reply—use it exactly as given. If saved info was provided and their inquiry clearly relates (e.g. they ask about availability, policies, services), you may integrate one short relevant detail naturally. Otherwise say we're on it and will get back to them shortly. Do NOT include a phone number or "call us"—the caller will add that.
- If their message mentions a type of event (e.g. wedding, birthday, corporate event, school event, graduation, party), acknowledge that event in your reply to sound personal (e.g. "Thanks for reaching out about your wedding" or "Got your note about the corporate event—we're on it").
- Use the lead's name at most ONCE in the body (e.g. do not say "Hi [name]" or repeat their name—the greeting "Hi [name]" is added automatically before your body). Sound natural and human; one name use or none is best.
- Subject line: under 50 chars. Use "Re: ..." or "Thanks for reaching out" style.
- No marketing fluff. No "We received your inquiry."

Reply with exactly two lines:
Line 1: SUBJECT: <your subject line>
Line 2: BODY: <your email body>"""
    try:
        client = openai.OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0.5,
        )
        raw = (resp.choices[0].message.content or "").strip()
        subject = ""
        body = ""
        for line in raw.splitlines():
            line_stripped = line.strip()
            if line_stripped.upper().startswith("SUBJECT:"):
                subject = line_stripped[8:].strip().strip('"').strip("'")[:200]
            elif line_stripped.upper().startswith("BODY:"):
                body = line_stripped[5:].strip().strip('"').strip("'")[:600]
        if not body and raw:
            lines = [l.strip() for l in raw.splitlines() if l.strip()]
            if len(lines) >= 1:
                subject = (lines[0].strip('"').strip("'")[:200]) if not subject else subject
            if len(lines) >= 2:
                body = "\n\n".join(lines[1:]).strip()[:600]
        if subject and body:
            return {"subject": subject, "body": body}
        return None
    except Exception as e:
        print(f"[autoreply AI] OpenAI error: {e}. Using generic autoreply.")
        return None


def _plain_to_simple_html(text: str) -> str:
    """Convert plain text body to minimal HTML (paragraphs)."""
    if not text:
        return "<p></p>"
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    return "".join(f"<p>{_escape_html(p)}</p>" for p in paras)


def _escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ==============================================================================
# EMAIL SENDING FUNCTIONS
# ==============================================================================

def get_template(followup_number: int) -> dict:
    """Get the appropriate template based on followup number (0-indexed)"""
    index = min(followup_number, len(FOLLOWUP_TEMPLATES) - 1)
    return FOLLOWUP_TEMPLATES[index]


def format_template(template: dict, lead_name: str, sender_name: str | None = None) -> dict:
    """Format template with lead's name and sender info"""
    name = sender_name or SENDER_NAME
    return {
        "subject": template["subject"].format(name=lead_name, sender_name=name),
        "html": template["html"].format(name=lead_name, sender_name=name),
        "text": template["text"].format(name=lead_name, sender_name=name),
    }


def send_followup_email(
    to_email: str,
    lead_name: str,
    followup_number: int = 0,
    from_email: str | None = None,
    from_name: str | None = None,
    subject: str | None = None,
    body_plain: str | None = None,
    body_html: str | None = None,
    signature_block: str | None = None,
    logo: str | None = None,
) -> dict:
    """
    Send a follow-up email to a lead.
    When subject and body_plain are provided (e.g. from AI), use those; otherwise use template.
    If signature_block is provided, it is appended at the bottom of the email (contact/signature).
    
    Args:
        to_email: The lead's email address
        lead_name: The lead's name (for personalization)
        followup_number: Which follow-up this is (0 = first, 1 = second, etc.)
        from_email: Optional sender email (defaults to SENDER_EMAIL from .env)
        from_name: Optional sender name (defaults to SENDER_NAME from .env)
        subject: Optional custom subject (AI-generated)
        body_plain: Optional custom plain-text body (AI-generated)
        body_html: Optional custom HTML body; if None and body_plain set, generated from body_plain
        signature_block: Optional contact/signature block appended at bottom of email
    
    Returns:
        dict with success status and message/error
    """
    # Check if API key is configured
    if not resend.api_key:
        print("WARNING: RESEND_API_KEY not configured. Email not sent.")
        return {
            "success": False,
            "error": "RESEND_API_KEY not configured. Set it in your .env file."
        }
    
    try:
        sender_email = from_email or SENDER_EMAIL
        sender_name = from_name or SENDER_NAME
        
        if subject and body_plain:
            html = body_html or _plain_to_simple_html(body_plain)
            text = body_plain
        else:
            template = get_template(followup_number)
            formatted = format_template(template, lead_name, sender_name)
            subject = formatted["subject"]
            html = formatted["html"]
            text = formatted["text"]
        
        # Prepend logo at top if set (data URL; do not escape, data URLs are safe in quoted attr)
        if logo and isinstance(logo, str) and logo.strip().startswith("data:image/") and len(logo) <= 150000:
            logo_src = logo.strip().replace('"', "%22")
            logo_html = f'<p style="margin-bottom:16px;"><img src="{logo_src}" alt="Logo" style="max-width:200px;height:auto;" /></p>'
            html = logo_html + html
        
        # Append client's signature/contact block at bottom if set
        if signature_block and signature_block.strip():
            sig = signature_block.strip()
            text = text.rstrip() + "\n\n" + sig
            sig_html = _escape_html(sig).replace("\n", "<br>")
            sig_p = f"<p style='margin-top:1em;white-space:pre-wrap;font-size:14px;'>{sig_html}</p>"
            if "</body>" in html:
                html = html.replace("</body>", sig_p + "</body>")
            else:
                html = html + sig_p
        
        result = resend.Emails.send({
            "from": f"{sender_name} <{sender_email}>",
            "to": [to_email],
            "subject": subject,
            "html": html,
            "text": text,
        })
        
        print(f"✅ Email sent to {to_email} (followup #{followup_number + 1}, from: {sender_email})")
        return {
            "success": True,
            "message": f"Email sent successfully to {to_email}",
            "email_id": result.get("id") if isinstance(result, dict) else str(result)
        }
        
    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


def send_test_email(to_email: str) -> dict:
    """
    Send a test email to verify the configuration is working.
    
    Args:
        to_email: Email address to send test to
    
    Returns:
        dict with success status and message/error
    """
    if not resend.api_key:
        return {
            "success": False,
            "error": "RESEND_API_KEY not configured. Set it in your .env file."
        }
    
    try:
        result = resend.Emails.send({
            "from": f"{SENDER_NAME} <{SENDER_EMAIL}>",
            "to": [to_email],
            "subject": "Test Email - Your Follow-up System is Working!",
            "html": """
                <h2>🎉 Your email system is working!</h2>
                <p>This is a test email from your lead follow-up system.</p>
                <p>If you received this, your Resend configuration is correct.</p>
            """,
            "text": "Your email system is working! This is a test email from your lead follow-up system."
        })
        
        print(f"✅ Test email sent to {to_email}")
        return {
            "success": True,
            "message": f"Test email sent to {to_email}",
            "email_id": result.get("id") if isinstance(result, dict) else str(result)
        }
        
    except Exception as e:
        print(f"❌ Failed to send test email: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


def send_autoreply_lead(
    to_email: str,
    lead_name: str,
    client_phone: str | None,
    sender_name: str = SENDER_NAME,
    sender_email: str = SENDER_EMAIL,
    inquiry_subject: str | None = None,
    inquiry_body: str | None = None,
    reply_to: str | None = None,
    client_pricing: str | None = None,
    client_saved_info: str | None = None,
    bcc: str | None = None,
    signature_block: str | None = None,
    logo: str | None = None,
) -> dict:
    """
    Send instant autoreply to a new lead. When inquiry_subject/body are provided,
    uses AI to tailor the message; otherwise uses generic "we received your inquiry" + optional phone.
    From = sender_name + sender_email (your verified Resend address). When reply_to is set,
    replies from the lead go to that address (e.g. client owner email). When bcc is set
    (e.g. owner email), that address receives a copy of the email sent to the lead.
    When signature_block is set, it is appended at the bottom (contact block).
    Returns dict with success and message/error.
    """
    if not resend.api_key:
        return {"success": False, "error": "RESEND_API_KEY not configured. Set it in your .env file."}
    name = (lead_name or "there").strip() or "there"
    if client_phone and (client_phone or "").strip():
        call_line = f" Feel free to reply to this email with any other questions you may have or feel free to call/text {client_phone.strip()}!"
    else:
        call_line = " Feel free to reply to this email with any other questions you may have or feel free to call/text us at your convenience!"

    subject = "We received your inquiry"
    body_text = f"Thank you for reaching out, we are actively working on this.{call_line}"
    ai_copy = generate_autoreply_copy(
        lead_name=name,
        sender_name=sender_name,
        inquiry_subject=inquiry_subject,
        inquiry_body=inquiry_body,
        client_pricing=client_pricing,
        client_saved_info=client_saved_info,
    )
    if ai_copy and (ai_copy.get("subject") or "").strip() and (ai_copy.get("body") or "").strip():
        subject = (ai_copy["subject"] or subject).strip()[:200]
        body_text = ((ai_copy["body"] or "").strip() + call_line).strip()[:800]

    logo_html = ""
    if logo and isinstance(logo, str) and logo.strip().startswith("data:image/") and len(logo) <= 150000:
        logo_src = logo.strip().replace('"', "%22")
        logo_html = f'<p style="margin-bottom:16px;"><img src="{logo_src}" alt="Logo" style="max-width:200px;height:auto;" /></p>'
    html = f"""<p>Hi {name},</p><p>{body_text}</p><p>Best regards,<br><strong>{sender_name}</strong></p>"""
    html = logo_html + html
    text = f"Hi {name},\n\n{body_text}\n\nBest regards,\n{sender_name}"
    if signature_block and signature_block.strip():
        sig = signature_block.strip()
        text = text.rstrip() + "\n\n" + sig
        sig_html = _escape_html(sig).replace("\n", "<br>")
        sig_p = f"<p style='margin-top:1em;white-space:pre-wrap;font-size:14px;'>{sig_html}</p>"
        html = html.rstrip() + sig_p
    payload = {
        "from": f"{sender_name} <{sender_email}>",
        "to": [to_email],
        "subject": subject,
        "html": html,
        "text": text,
    }
    if reply_to and (reply_to or "").strip() and "@" in (reply_to or "").strip():
        payload["reply_to"] = (reply_to or "").strip()
    if bcc and (bcc or "").strip() and "@" in (bcc or "").strip():
        payload["bcc"] = [(bcc or "").strip()]
    try:
        result = resend.Emails.send(payload)
        print(f"[autoreply] Sent to {to_email}")
        return {
            "success": True,
            "message": f"Autoreply sent to {to_email}",
            "email_id": result.get("id") if isinstance(result, dict) else str(result),
        }
    except Exception as e:
        print(f"[autoreply] Failed to send to {to_email}: {e}")
        return {"success": False, "error": str(e)}
