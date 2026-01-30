# Email autofollowup setup

The app sends automatic follow-up emails to leads (from Google Forms, manual add, etc.) using **Resend**. Leads older than **24 hours** get up to **3** follow-up emails. The scheduler runs **every hour**.

---

## 1. Get a Resend API key

1. Sign up at **[resend.com](https://resend.com)**.
2. Go to **API Keys** → **Create API Key**.
3. Copy the key (starts with `re_`).

---

## 2. Configure environment variables

1. In `backend/`, copy the example env file (if you don't have `.env` yet):
   ```bash
   cd backend
   cp .env.example .env
   ```
2. Edit `backend/.env` and set:

   ```env
   RESEND_API_KEY=re_your_actual_key_here
   SENDER_EMAIL=onboarding@resend.dev
   SENDER_NAME=Your Business Name
   ```

   - **Testing:** Use `onboarding@resend.dev`. Resend sends to **your own email** only when using this.
   - **Production:** Verify your domain in Resend, then use e.g. `noreply@yourdomain.com`.

3. Save the file. **Never commit `.env`** (it's in `.gitignore`).

---

## 3. Restart the backend

```bash
cd /path/to/dashboard
bash start-backend.sh
```

The scheduler starts with the app. Emails are sent when the follow-up job runs (every hour, or when you trigger it manually).

---

## 4. Test that emails send

**Option A: Dashboard "Test follow-up" button (no slug needed)**

Log in to the dashboard, scroll to **Connect your Google Form**, and click **Test follow-up**. A test email and follow-up are sent to **your signup email**. No slug or CLI required.

**Option B: Test script**

```bash
cd backend
source venv/bin/activate
pip install requests   # if not already installed
python test_followup.py --email you@example.com      # auto-resolve from signup email (no slug)
python test_followup.py --client-slug YOUR_CLIENT_SLUG   # or pass slug explicitly
```

With `--email`, the script resolves your client from your signup email. With `--client-slug`, use the slug from the dashboard (e.g. `jane-42`). The test email and follow-up go to **your signup email**.

**Option C: Manual API calls**

1. **Test Resend** (sends to client owner's signup email):
   ```bash
   curl -X POST "http://localhost:8000/test/send-email-to-owner?client_slug=YOUR_CLIENT_SLUG"
   ```
   Or send to a specific address: `curl -X POST "http://localhost:8000/test/send-email?to_email=YOU@email.com"`

2. **Add an old lead** (25 hours ago) for your client. Uses owner's email if `email` is omitted:
   ```bash
   curl -X POST "http://localhost:8000/test/add-old-lead?client_slug=YOUR_CLIENT_SLUG"
   ```
   Use your dashboard **Client slug** (from "Connect your Google Form").

3. **Trigger the follow-up job:**
   ```bash
   curl -X POST "http://localhost:8000/test/run-followups"
   ```

4. Check your inbox and the backend terminal for "✅ Auto followup #1 sent to …".

---

## 5. How it works

- **Scheduler:** Runs every **1 hour** (`central_loop`).
- **Eligibility:** Lead is **older than 24 hours**, has **< 3 follow-ups** sent, and is **not** recovered.
- **Templates:** 3 follow-up emails (first, second, third). The right one is chosen from `followups_sent`.
- **Per client:** Each client's leads are processed separately.
- **Sender email:** Follow-ups automatically use the **client owner's email** (the user who signed up for that client) as the sender. If the client has no user, it falls back to `SENDER_EMAIL` from `.env`.

**⚠️ Important:** The client's email address must be **verified in Resend** for it to work. If not verified, Resend will reject the email and it will fall back to `SENDER_EMAIL`. For testing, `onboarding@resend.dev` works for your own email only.

New leads (Forms, manual, etc.) will get their first follow-up **24 hours after** they're created, then the next two according to the same rules.

---

## 6. Troubleshooting

| Issue | What to check |
|-------|----------------|
| "RESEND_API_KEY not configured" | `.env` in `backend/`, correct variable name, backend restarted after editing `.env`. |
| No email received | Use `onboarding@resend.dev` only for **your** email; check spam; Resend dashboard → Logs. |
| Follow-up not sent | Lead must be **> 24 h** old. Use `test/add-old-lead` or wait. Run `test/run-followups` to trigger immediately. |
| Wrong client | Use **your** `client_slug` in `test/add-old-lead` (same as in the dashboard). |

---

## 7. Optional: test a single template

```bash
curl "http://localhost:8000/test/send-followup-email?to_email=YOU@email.com&name=Alex&template_number=0"
```

- `template_number=0` → first follow-up  
- `1` → second  
- `2` → third  

Useful to verify content and deliverability without the scheduler.
