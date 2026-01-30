# Google Forms Integration Setup Guide

This guide will help you connect your Google Forms to automatically add leads to your dashboard.

**Multi-tenant setup:** Each paying client has their own dashboard page (`?client=client-slug`) and their own webhook URL (`/webhook/lead/client-slug`). Use the same `client_slug` for the dashboard and the form's webhook.

## Prerequisites

- Backend running on `http://localhost:8000` (or deployed)
- A Google Form with at least "Name" and "Email" fields
- Google account with access to Google Apps Script
- A **client** created (e.g. the built-in `demo` client, or create one via `POST /clients`)

---

## Step 1: Test Your Webhook (Local Testing)

Before connecting Google Forms, test that your webhook works for a specific client.

### Option A: Use the Test Script

```bash
cd backend
source venv/bin/activate
pip install requests  # If not already installed
python test_webhook.py          # uses client 'demo'
python test_webhook.py acme     # uses client 'acme'
```

This sends 3 test leads to that client's webhook. Open the dashboard with `?client=demo` (or `?client=acme`) and confirm the leads appear.

### Option B: Manual Test with curl

```bash
# Replace 'demo' with your client's slug
curl -X POST http://localhost:8000/webhook/lead/demo \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test User",
    "email": "test@example.com",
    "phone": "",
    "source": "Google Forms"
  }'
```

You should see a JSON response with the new lead's ID.

---

## Step 2: Make Your Backend Accessible to Google

Google Forms can't reach `localhost:8000` directly. You have two options:

### Option A: Use ngrok (For Testing)

1. **Install ngrok**: https://ngrok.com/download

2. **Start your backend**:
   ```bash
   cd backend
   source venv/bin/activate
   uvicorn main2:app --reload --port 8000
   ```

3. **In a new terminal, start ngrok**:
   ```bash
   ngrok http 8000
   ```

4. **Copy the HTTPS base URL** (e.g., `https://abc123.ngrok.io`)

5. **Update the Google Apps Script** (see Step 3) with `BACKEND_BASE` and `CLIENT_SLUG`.

⚠️ **Note**: The ngrok URL changes each time you restart ngrok (unless you have a paid plan). Update the script when it changes.

### Option B: Deploy Your Backend (For Production)

Deploy your FastAPI backend to a service like:
- **Railway**: https://railway.app
- **Render**: https://render.com
- **Heroku**: https://heroku.com
- **Fly.io**: https://fly.io

Use your deployed base URL as `BACKEND_BASE` in the script.

---

## Step 3: Set Up Google Apps Script

1. **Open your Google Form** (one form per client, or use different scripts per client)

2. **Click the three dots (⋮)** in the top right → **"Script editor"**

3. **Delete any existing code** and paste the contents of `google_forms_script.js`

4. **Update the config** for this client:
   ```javascript
   const BACKEND_BASE = "https://abc123.ngrok.io";   // or your deployed URL
   const CLIENT_SLUG = "demo";   // same slug as dashboard ?client=demo
   ```
   The webhook URL will be `BACKEND_BASE + "/webhook/lead/" + CLIENT_SLUG`.

5. **Save the script** (Ctrl+S or Cmd+S)

6. **Set up the trigger**:
   - Click the **clock icon** (Triggers) in the left sidebar
   - Click **"+ Add Trigger"** (bottom right)
   - Configure:
     - **Function**: `onFormSubmit`
     - **Event source**: `From form`
     - **Event type**: `On form submit`
   - Click **Save**

7. **Authorize the script**:
   - You'll be prompted to authorize the script
   - Click **"Review Permissions"**
   - Choose your Google account
   - Click **"Advanced"** → **"Go to [Your Project] (unsafe)"**
   - Click **"Allow"**

---

## Step 4: Configure Field Mapping

The script automatically detects fields by their titles. It looks for:

- **Name**: Fields containing "name", "full name", "first name", "last name"
- **Email**: Fields containing "email", "e-mail", "email address"
- **Phone**: Fields containing "phone", "phone number", "telephone"

### If your form uses different field names:

Edit the `onFormSubmit` function in the Google Apps Script. Update the matching logic:

```javascript
if (questionTitle.includes("your-custom-name-field")) {
  name = answer;
}
```

---

## Step 5: Test the Integration

1. **Submit a test response** to your Google Form

2. **Check the Apps Script logs**:
   - In the Script Editor, click **"Executions"** (left sidebar)
   - Look for the latest execution
   - Click it to see logs

3. **Check your dashboard**:
   - Open your frontend with `?client=<your-client-slug>` (e.g. `?client=demo`)
   - The new lead should appear in the table
   - Source should show as "Google Forms"

---

## Troubleshooting

### "Connection Error" in Apps Script logs

- **Backend not running**: Start it with `uvicorn main2:app --reload --port 8000`
- **Wrong URL**: Double-check `BACKEND_BASE` and `CLIENT_SLUG` in the script (webhook = `BACKEND_BASE/webhook/lead/CLIENT_SLUG`)
- **ngrok not running**: Restart ngrok and update `BACKEND_BASE`

### "Missing required fields" error

- Your form fields don't match the expected names
- Update the field matching logic in the script (see Step 4)

### Leads not appearing in dashboard

- Check Apps Script execution logs for errors
- Verify the backend received the request (check backend terminal)
- Check browser console for frontend errors
- Refresh the dashboard page

### ngrok URL expired

- Restart ngrok: `ngrok http 8000`
- Copy the new base URL
- Update `BACKEND_BASE` in the Google Apps Script

---

## Testing the Script Manually

You can test the script without submitting a form:

1. In the Script Editor, select the `testWebhook` function from the dropdown
2. Click the **Run** button (▶️)
3. Check the logs to see if it worked

---

## Security Notes

For production, consider adding:

1. **API Key Authentication**: Add an API key check in your webhook endpoint
2. **Rate Limiting**: Prevent spam submissions
3. **Input Validation**: Sanitize and validate all inputs
4. **HTTPS Only**: Use HTTPS URLs (ngrok provides this)

---

## Next Steps

Once this is working:

- Add more form fields (phone, company, etc.)
- Set up integrations with other platforms (Facebook Lead Ads, LinkedIn, etc.)
- Add email notifications when new leads arrive
- Customize the source tracking for different forms

---

## Support

If you encounter issues:

1. Check the Apps Script execution logs
2. Check your backend terminal for errors
3. Test the webhook manually with `test_webhook.py`
4. Verify your form field names match the script's expectations
