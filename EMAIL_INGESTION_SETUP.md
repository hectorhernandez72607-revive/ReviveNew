# Email lead ingestion (no domain required)

Leads can be ingested from your **Gmail inbox**: unread emails are read via IMAP, parsed for name/email/phone, and created as leads on the dashboard. No domain or Resend needed for ingestion.

---

## 1. Gmail App Password

1. Go to [Google Account → Security](https://myaccount.google.com/security).
2. Under **Signing in to Google**, turn on **2-Step Verification** if it’s not already.
3. Open **App passwords** (same Security page).
4. Choose **Mail** and your device, then **Generate**.
5. Copy the **16-character password** (no spaces). You won’t see it again.

---

## 2. Configure `backend/.env`

Add or update:

```env
IMAP_EMAIL=your_email@gmail.com
IMAP_APP_PASSWORD=xxxxxxxxxxxxxxxx
IMAP_CLIENT_SLUG=demo
```

- **IMAP_EMAIL**: Gmail address that receives lead emails (e.g. `hectorhernandez72607@gmail.com`).
- **IMAP_APP_PASSWORD**: The 16-char app password from step 1.
- **IMAP_CLIENT_SLUG**: Client slug for new leads (same as in the dashboard “Connect your Google Form”). Use your dashboard slug if you’ve signed up.

Restart the backend after changing `.env`.

---

## 3. How it works

- **Inbox**: The app connects to Gmail IMAP and reads **unread** emails from **INBOX**.
- **Parsing**: From **From** it gets name and email; from the **body** it looks for a US-style phone number.
- **Leads**: Each processed email becomes a lead with `source: "Email"`. Duplicates are avoided by storing `Message-ID`.
- **Dashboard**: New leads show up in the leads table. Ingestion runs automatically every 10 minutes.
- **Scheduler**: Ingestion also runs automatically **every 10 minutes**.

---

## 4. Testing

1. Restart the backend (so it loads `IMAP_*`).
2. Send an **unread** email to `IMAP_EMAIL` (e.g. from another account or a second Gmail).
3. Wait for the next automatic run (every 10 minutes), or trigger manually via `POST /me/run-email-ingestion` if you have access.
4. You should see a new lead with **Source: Email**. Sender name/email and any phone in the body are used.

**Manual API trigger:**

```bash
curl -X POST "http://localhost:8000/test/run-email-ingestion"
```

(Or `POST /me/run-email-ingestion` with `Authorization: Bearer <token>` when logged in. The dashboard no longer has a "Check email" button; ingestion is automatic.)

---

## 5. Troubleshooting

| Issue | What to check |
|-------|----------------|
| “IMAP_EMAIL and IMAP_APP_PASSWORD required” | Both set in `backend/.env`, backend restarted. |
| “Client 'X' not found” | `IMAP_CLIENT_SLUG` matches a real client (e.g. your dashboard slug). |
| No leads created | Emails are **unread**; sender has a valid **From** address. |
| Login/IMAP errors | Use the **App Password**, not your normal Gmail password. 2-Step Verification must be on. |

---

## 6. Optional: AI “is this a lead?” classifier

When **OPENAI_API_KEY** is set in `backend/.env`, each parsed email is sent to OpenAI. Only emails the model classifies as **potential leads** (inquiries, quotes, interest in services) are created as leads. Newsletters, receipts, notifications, marketing blasts, etc. are skipped.

1. Get an API key from [OpenAI](https://platform.openai.com/api-keys).
2. Add to `backend/.env`:

   ```env
   OPENAI_API_KEY=sk-your-key-here
   ```

3. Optional: set **OPENAI_MODEL** (default `gpt-4o-mini`). Restart the backend.

If `OPENAI_API_KEY` is not set, all unread parsed emails are treated as leads (previous behavior).

---

## 7. Optional: plus-addressing (later)

You can use **plus-addressing** (e.g. `you+client1@gmail.com`) to route leads to different clients. Right now ingested leads go to the client from `IMAP_CLIENT_SLUG`. Multi-inbox or plus-address routing can be added later.
