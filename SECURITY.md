# Security & Hardening

This document describes security measures and production checklist for the Lead Dashboard.

---

## 1. JWT Secret

**Required for production.** Used to sign and verify login tokens.

- **Generate a strong secret:**
  ```bash
  openssl rand -hex 32
  ```
- **Set in `backend/.env`:**
  ```
  JWT_SECRET=<paste the 64-character hex string>
  ```
- The app will warn on startup if `JWT_SECRET` is weak or unchanged from defaults.

---

## 2. Test Endpoints

`/test/*` endpoints (run-followups, send-email, add-old-lead, etc.) are **disabled by default** in production.

### Local development

In `backend/.env`:
```
ENABLE_TEST_ENDPOINTS=true
```

### Production

- **Leave unset or set to `false`** – test endpoints return 404.

### Optional: Protect test endpoints with admin key

When `ENABLE_TEST_ENDPOINTS=true`, you can require an admin key:

1. Generate a key: `openssl rand -hex 24`
2. Add to `backend/.env`:
   ```
   ADMIN_API_KEY=<your-generated-key>
   ```
3. Pass it in requests:
   ```bash
   curl -X POST "http://localhost:8000/test/send-email?to_email=test@example.com" \
     -H "X-Admin-Key: <your-generated-key>"
   ```

---

## 3. CORS

Restrict which origins can call your API.

**Production** – in `backend/.env`:
```
CORS_ORIGINS=https://app.yourdomain.com,https://yourdomain.com
```

**Development** – default `*` allows all (localhost, ngrok, etc.).

---

## 4. Production Checklist

- [ ] Set a strong `JWT_SECRET` (64+ chars)
- [ ] Set `ENABLE_TEST_ENDPOINTS=false` or remove it
- [ ] Set `CORS_ORIGINS` to your real frontend URL(s)
- [ ] Use HTTPS
- [ ] Never commit `backend/.env` (it's in `.gitignore`)
