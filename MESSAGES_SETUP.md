# Twilio SMS Setup Guide

Configure Twilio so leads can come in via text messages and receive SMS followups (same schedule as email: 24h first, then weekly).

---

## Step 1: Sign up for Twilio

1. Go to: **https://www.twilio.com/try-twilio**
2. Sign up (free trial includes a phone number and credits)
3. Verify your phone number and email

---

## Step 2: Get your credentials

1. Open **https://console.twilio.com**
2. On the dashboard you’ll see:
   - **Account SID** (starts with `AC`)
   - **Auth Token** (click “Show” to reveal)
3. Copy both into your `.env` in the backend folder:

```bash
cd backend
# Edit .env and set:
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
```

---

## Step 3: Get a phone number

1. In Twilio Console go to: **Phone Numbers → Manage → Buy a number**
2. (Trial accounts can use a trial number from **Phone Numbers → Manage → Get a number**)
3. Pick a number with **SMS** capability
4. Copy the number in E.164 form (e.g. `+15551234567`) into `.env`:

```
TWILIO_PHONE_NUMBER=+15551234567
```

5. **TWILIO_CLIENT_SLUG** is already set in your `.env` to `hectorhernandez72607-2` so SMS leads go to the same client as your email leads.

---

## Step 4: Set the webhook (incoming SMS → create lead)

Your backend must be reachable from the internet so Twilio can send incoming SMS to it.

**Option A – Local dev with ngrok**

1. Install ngrok: https://ngrok.com/download  
2. Start your backend: `uvicorn main2:app --reload --port 8000`  
3. In another terminal: `ngrok http 8000`  
4. Copy the HTTPS URL (e.g. `https://abc123.ngrok.io`)

**Option B – Deployed backend**

Use your real backend URL (e.g. `https://your-app.herokuapp.com` or `https://api.yourdomain.com`).

**In Twilio:**

1. Go to **Phone Numbers → Manage → Active numbers**
2. Click your Twilio number
3. Under **Messaging**, find **“A MESSAGE COMES IN”**
4. Set:
   - **Webhook:** `https://YOUR-PUBLIC-URL/webhook/twilio/sms`
   - **HTTP:** `POST`
5. Save

Replace `YOUR-PUBLIC-URL` with your ngrok URL or deployed backend URL (no trailing slash).

---

## Step 5: Install Twilio and restart

```bash
cd backend
source venv/bin/activate
pip install twilio
# Restart backend
uvicorn main2:app --reload --port 8000
```

---

## Summary of .env Twilio variables

| Variable | Where to get it |
|----------|-----------------|
| `TWILIO_ACCOUNT_SID` | Console → Dashboard (starts with `AC`) |
| `TWILIO_AUTH_TOKEN` | Console → Dashboard → “Show” |
| `TWILIO_PHONE_NUMBER` | E.164 format, e.g. `+15551234567` |
| `TWILIO_CLIENT_SLUG` | Same as your dashboard client (e.g. `hectorhernandez72607-2`) — already set |

---

## Test it

1. Send an SMS to your Twilio number (e.g. “Hi, I’m interested in your service”).
2. In the dashboard, a new lead should appear with **Source: Messages** and the message in the inquiry.
3. After 24 hours (or when you run the followup job), that lead gets the first SMS followup; weekly SMS followups continue on the same schedule as email.

---

## Troubleshooting

- **“Twilio not configured”** – Check that `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_PHONE_NUMBER` are all set in `.env` and the backend was restarted.
- **SMS not creating leads** – Confirm the webhook URL is correct, uses `https`, and Twilio can reach it (use ngrok for local dev). Check backend logs for `[twilio_sms]` messages.
- **Trial account** – You can only send SMS to verified numbers. Verify numbers in Console → Phone Numbers → Manage → Verified Caller IDs.
