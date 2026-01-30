# Email System Setup Guide

Your lead dashboard now supports automatic follow-up emails using Resend!

## Quick Setup (5 minutes)

### Step 1: Sign up for Resend

1. Go to: https://resend.com
2. Sign up for a free account (3,000 emails/month free)
3. Verify your email

### Step 2: Get your API key

1. Go to: https://resend.com/api-keys
2. Click "Create API Key"
3. Name it something like "Lead Dashboard"
4. Copy the key (starts with `re_`)

### Step 3: Create your .env file

```bash
cd /Users/hectorhernandez2607/Desktop/dashboard/backend
cp .env.example .env
```

Then edit `.env` and add your API key:

```
RESEND_API_KEY=re_your_actual_api_key_here
SENDER_EMAIL=onboarding@resend.dev
SENDER_NAME=Your Business Name
```

### Step 4: Install dependencies

```bash
cd backend
source venv/bin/activate
pip install resend python-dotenv
```

### Step 5: Restart your backend

```bash
uvicorn main2:app --reload --port 8000
```

---

## Testing the Email System

### Test 1: Send a test email

```bash
curl -X POST "http://localhost:8000/test/send-email?to_email=YOUR_EMAIL@example.com"
```

Check your inbox for the test email.

### Test 2: Preview follow-up templates

```bash
# Template 1 (first follow-up)
curl -X POST "http://localhost:8000/test/send-followup-email?to_email=YOUR_EMAIL@example.com&name=John&template_number=0"

# Template 2 (second follow-up)
curl -X POST "http://localhost:8000/test/send-followup-email?to_email=YOUR_EMAIL@example.com&name=John&template_number=1"

# Template 3 (third follow-up)
curl -X POST "http://localhost:8000/test/send-followup-email?to_email=YOUR_EMAIL@example.com&name=John&template_number=2"
```

### Test 3: Full flow test

```bash
# Add an old lead
curl -X POST http://localhost:8000/test/add-old-lead

# Run followups (will send actual email!)
curl -X POST http://localhost:8000/test/run-followups
```

---

## Email Templates

The system includes 3 follow-up templates:

| # | Timing | Subject | Tone |
|---|--------|---------|------|
| 1 | 24 hours | "Quick follow-up on your inquiry, {name}!" | Friendly, helpful |
| 2 | 48 hours | "Still interested, {name}?" | Gentle reminder |
| 3 | 72 hours | "Last chance to connect, {name}" | Final, respectful |

Templates are in `backend/email_service.py`. You can customize:
- Subject lines
- HTML content (with styling)
- Plain text version
- Colors and branding

---

## How It Works

1. **Lead comes in** (Google Form, manual, etc.)
2. **24 hours pass** without contact
3. **Scheduler runs** (every hour)
4. **First follow-up** email sent automatically
5. Lead status changes to "waiting"
6. **If no response after another 24 hours**, second follow-up sent
7. **After third follow-up**, no more emails (respects the lead's time)

---

## Configuration

### Sender Email

For testing, use Resend's default: `onboarding@resend.dev`

For production:
1. Go to Resend → Domains
2. Add your domain
3. Add DNS records they provide
4. Update `SENDER_EMAIL` in `.env`

### Customize Templates

Edit `backend/email_service.py`:

```python
FOLLOWUP_TEMPLATES = [
    {
        "subject": "Your custom subject, {name}!",
        "html": "Your HTML content...",
        "text": "Plain text version..."
    },
    # Add more templates...
]
```

### Change Follow-up Timing

Edit `backend/main2.py`:

```python
# Change from 24 hours to something else
def is_older_than_24_hours(created_at: str) -> bool:
    lead_time = datetime.datetime.fromisoformat(created_at)
    return lead_time <= datetime.datetime.now() - datetime.timedelta(hours=24)  # Change this
```

### Change Max Follow-ups

Edit the `followup()` function in `main2.py`:

```python
if lead["followups_sent"] >= 3:  # Change this number
    print(f"Followup limit reached for {lead['email']}")
    return False
```

---

## Troubleshooting

### "RESEND_API_KEY not configured"

- Make sure `.env` file exists in the backend folder
- Make sure `RESEND_API_KEY` is set correctly
- Restart the backend after changing `.env`

### Emails not sending

- Check the terminal for error messages
- Verify your API key is valid at resend.com
- Make sure you have emails remaining in your free tier

### Emails going to spam

- Verify your domain in Resend (for production)
- Use a professional sender name
- Don't use spammy words in subject lines

---

## Files Created/Modified

- `backend/email_service.py` - Email sending logic and templates
- `backend/.env.example` - Template for environment variables
- `backend/.env` - Your actual config (create this)
- `backend/.gitignore` - Prevents committing secrets
- `backend/requirements.txt` - Added resend, python-dotenv
- `backend/main2.py` - Updated followup() to send real emails

---

## Next Steps

1. ✅ Set up Resend account
2. ✅ Create `.env` file with API key
3. ✅ Test with `/test/send-email`
4. ✅ Customize templates to match your brand
5. ✅ (Optional) Verify your domain for production
