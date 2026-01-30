# Quick Start: Multi-Tenant Dashboard + Google Forms

## ✅ What's Been Built

1. **Multi-tenant**: Each paying client has their own dashboard (`?client=slug`) and webhook (`/webhook/lead/{slug}`). Data is isolated per client.
2. **Client-scoped API**: `GET/POST /clients/{slug}/leads`, `POST /clients` to create clients.
3. **Test Script**: `backend/test_webhook.py [client_slug]` — defaults to `demo`.
4. **Google Apps Script**: `google_forms_script.js` — set `BACKEND_BASE` and `CLIENT_SLUG` per client.
5. **Source tracking**: Leads show source (Manual, Google Forms, etc.).

---

## 🚀 Quick Test (5 minutes)

### Step 1: Start Your Backend

```bash
cd backend
source venv/bin/activate
uvicorn main2:app --reload --port 8000
```

### Step 2: Test the Webhook

In a new terminal:

```bash
cd backend
source venv/bin/activate
pip install requests  # If not already installed
python test_webhook.py          # uses client 'demo'
python test_webhook.py acme     # or another client slug
```

You should see leads added successfully.

### Step 3: Check Your Dashboard

Open `frontend/index.html?client=demo` in your browser. If you omit `?client=...`, you’ll see a “Select a client” screen; use **Open Demo Client** or add `?client=demo` to the URL. You should see the test leads.

---

## 📋 Full Setup (Google Forms)

See `GOOGLE_FORMS_SETUP.md` for complete instructions.

**Quick version:**
1. Open your Google Form → Script editor.
2. Paste `google_forms_script.js`.
3. Set `BACKEND_BASE` (e.g. ngrok URL or deployed API) and `CLIENT_SLUG` (same as dashboard `?client=...`).
4. Set up trigger: `onFormSubmit` → “On form submit”.
5. Test by submitting the form.

---

## 🧪 Testing Options

### Option 1: Test Script (Easiest)
```bash
python backend/test_webhook.py           # client 'demo'
python backend/test_webhook.py acme      # client 'acme'
```

### Option 2: Manual curl
```bash
curl -X POST http://localhost:8000/webhook/lead/demo \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","email":"test@example.com","phone":"","source":"Google Forms"}'
```

### Option 3: Google Forms
Follow `GOOGLE_FORMS_SETUP.md` for full Google Forms integration.

---

## 📁 Files Created

- `backend/main2.py` - Updated with webhook endpoint
- `backend/test_webhook.py` - Test script
- `google_forms_script.js` - Google Apps Script code
- `GOOGLE_FORMS_SETUP.md` - Complete setup guide
- `QUICK_START.md` - This file

---

## 🎯 Next Steps

1. ✅ Test locally with `test_webhook.py`
2. ✅ Set up Google Forms (see `GOOGLE_FORMS_SETUP.md`)
3. ✅ Deploy backend for production
4. ✅ Add more integrations (Facebook, LinkedIn, etc.)

---

## 💡 Tips

- **Local Testing**: Use ngrok to expose localhost to Google
- **Production**: Deploy backend to Railway/Render/Heroku
- **Security**: Add API key authentication for production
- **Multiple clients**: Each client has its own `CLIENT_SLUG` and webhook URL; use different forms/scripts per client.

---

## 🐛 Troubleshooting

**Webhook not working?**
- Check backend is running: `uvicorn main2:app --reload --port 8000`
- Test with `python backend/test_webhook.py`
- Check backend terminal for errors

**Google Forms not sending?**
- Check Apps Script execution logs.
- Verify `BACKEND_BASE` and `CLIENT_SLUG` (webhook = `BACKEND_BASE/webhook/lead/CLIENT_SLUG`).
- Make sure trigger is set up.
- For localhost, use ngrok URL as `BACKEND_BASE`.

**Leads not showing?**
- Open the dashboard with `?client=your-client-slug` (e.g. `?client=demo`).
- Refresh the page.
- Check browser console for errors.
- Verify the backend received the request (check terminal).
