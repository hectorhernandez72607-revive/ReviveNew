# Deployment Guide – Step 1: Deploy to Production

This guide walks you through deploying your Lead Dashboard to **Render** (free tier).

---

## Prerequisites

- [GitHub](https://github.com) account
- [Render](https://render.com) account (free)
- Your project in a GitHub repository

---

## Step 1: Push Your Code to GitHub

If you haven’t already:

```bash
cd /Users/hectorhernandez2607/Desktop/dashboard
git init
git add .
git commit -m "Initial commit - lead dashboard"
git branch -M master
git remote add origin https://github.com/hectorhernandez72607/ReviveNew.git
git push -u origin master
```

> **Important:** Never commit `backend/.env`. It’s in `.gitignore` and contains secrets.

---

## Step 2: Deploy on Render

1. **Go to [Render Dashboard](https://dashboard.render.com)** and sign in (or create an account).

2. **Create a Blueprint:**
   - Click **New +** → **Blueprint**
   - Connect your GitHub account if needed
   - Select the `revive` repository
   - Render will detect `render.yaml` and show the services it defines

3. **Set environment variables when prompted:**
   - **JWT_SECRET** – auto-generated (or add your own: `openssl rand -hex 32`)
   - **RESEND_API_KEY** – your Resend API key from [resend.com/api-keys](https://resend.com/api-keys)
   - Other vars (`SENDER_EMAIL`, `SENDER_NAME`, `CORS_ORIGINS`) have defaults

4. **Create the Blueprint** – Render will build and deploy the app.

5. **Wait for the build** – usually 2–5 minutes. The app will be available at:
   ```
   https://lead-dashboard-XXXX.onrender.com
   ```

---

## Step 3: Add More Environment Variables (Optional)

In Render: **Dashboard → your service → Environment**:

| Variable | Required | Notes |
|----------|----------|-------|
| `RESEND_API_KEY` | Yes (for email) | From Resend |
| `JWT_SECRET` | Yes | Use `openssl rand -hex 32` |
| `DATABASE_PATH` | No | For persistent DB: set to `/data/leads.db` when using a Render disk (see "Fix: Login fails after redeploy" below) |
| `SENDER_EMAIL` | No | Default: `onboarding@resend.dev` |
| `SENDER_NAME` | No | Your business name |
| `CORS_ORIGINS` | No | Comma-separated frontend URLs; `*` = allow all |
| `IMAP_EMAIL` | No | For email ingestion |
| `IMAP_APP_PASSWORD` | No | Gmail App Password |
| `TWILIO_*` | No | For SMS (see `MESSAGES_SETUP.md`) |
| `OPENAI_API_KEY` | No | For lead classifier |

---

## Step 4: Test Your Deployment

1. Open `https://YOUR-SERVICE-NAME.onrender.com`
2. Sign up with a new account
3. Log in and confirm the dashboard loads
4. Add a test lead and verify it appears

---

## Your Production URL

After deploy, your app URL will look like:

```
https://lead-dashboard-xxxx.onrender.com
```

Use this URL as `BACKEND_BASE` in:
- Google Forms script (see `GOOGLE_FORMS_SETUP.md`)
- Any other integrations (webhooks, etc.)

---

## Notes

### SQLite and data persistence

- The app uses SQLite stored on the server filesystem.
- On Render’s free tier, the filesystem is ephemeral: data can be lost on redeploys or restarts.
- For production, consider a persistent database (e.g. Render Postgres) and migrating the app to use it.

### Fix: Login fails after redeploy

If login works right after signup but fails after a Render redeploy (exact email and password no longer work), the database was recreated empty. Fix it by using a **persistent disk** so the DB survives redeploys. This requires a **paid Render plan** (disks are not on the free tier).

1. **Add a persistent disk:** Render Dashboard → your Web Service → **Disks** → Add disk. Set mount path to `/data` and size (e.g. 1 GB). Save; Render will redeploy.
2. **Set the database path:** Same service → **Environment** → Add **Key:** `DATABASE_PATH`, **Value:** `/data/leads.db`. Save (triggers another redeploy).
3. **Sign up again once:** After the deploy finishes, open your app and sign up again with your email and password. The previous account lived on the old ephemeral DB; the new one will persist on the disk. From then on, login will work across redeploys.

The app already reads `DATABASE_PATH` from the environment; no code change is required. In Render logs you should see `Database: /data/leads.db` at startup when the env is set.

### Cold starts (free tier)

- After ~15 minutes of inactivity, the service may sleep.
- First request after sleep can take 30–60 seconds.
- Paid plans avoid this.

### Custom domain

- In Render: **Settings → Custom Domains** to add your own domain.
- Update `CORS_ORIGINS` with your domain.

---

## Next Steps (Step 2 from the deployment plan)

After deployment:

1. **Link your website/integrations:**
   - Set `BACKEND_BASE` in the Google Forms script to your Render URL
   - Set `CORS_ORIGINS` in Render if using a separate frontend domain

2. **Add payment** (when ready):
   - Integrate Stripe or another payment provider
   - Use your production URL for webhooks and redirects
