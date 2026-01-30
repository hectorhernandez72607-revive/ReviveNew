# Auth Setup: Sign Up → Dashboard

Your partner sends paying clients **one shared sign-up link**. They create an account, then access their own dashboard.

---

## Link Your Partner Sends

**Sign-up page:**  
The backend serves the frontend. With the backend running on port 8000:

- **Local:** `http://localhost:8000/signup.html`
- **Production:** `https://your-domain.com/signup.html`

Use the same base URL for **Login** (`/login.html`) and **Dashboard** (`/` or `/index.html`).

Each paying client gets the **same** link. When they open it, they sign up with email + password. The app creates their account and a dedicated client (1 user : 1 client). They’re then logged in and redirected to the dashboard, which shows only **their** leads.

---

## Flow

1. Partner sends **signup.html** link to a paying client.
2. Client opens link → **Sign up** (email, password, confirm password).
3. On success → account created → **redirect to dashboard**.
4. Dashboard shows **their** leads (from `/me/leads`). They can add leads, log out, etc.

Returning users use **login.html** (same origin) to log in.

---

## Pages

| Page        | URL          | Purpose                          |
|-------------|--------------|----------------------------------|
| Sign up     | `signup.html`| Create account → redirect to app |
| Log in      | `login.html` | Log in → redirect to dashboard   |
| Dashboard   | `index.html` | Auth required; shows their leads |

If someone opens **index.html** without being logged in, they’re redirected to **login.html**.

---

## Backend

- `POST /auth/signup` — `{ "email": "...", "password": "..." }` → creates user + client, returns JWT.
- `POST /auth/login` — `{ "email": "...", "password": "..." }` → returns JWT.
- `GET /me` — `Authorization: Bearer <token>` → `{ user, client }`.
- `GET /me/leads` — leads for the authenticated user’s client.
- `POST /me/lead` — add a lead to their client.

Frontend stores the JWT in `localStorage` and sends it as `Authorization: Bearer <token>` on API calls.

---

## Security

- Set **`JWT_SECRET`** in `.env` (see `.env.example`). Use a long, random value in production.
- Passwords are hashed with bcrypt.
- Use **HTTPS** in production for signup/login and the dashboard.

---

## Dependencies

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
```

Adds `passlib[bcrypt]` and `python-jose[cryptography]` for auth.

---

## Serving the Frontend

The FastAPI backend **serves the frontend** from the `frontend/` folder. No separate static server is needed.

1. Run the backend: `uvicorn main2:app --reload --port 8000` (from the `backend/` directory).
- **Production:** Serve `frontend/` from your app’s domain (e.g. Nginx, Vercel, Netlify). Partner sends `https://your-domain.com/signup.html`.

Ensure the frontend’s `API` base URL (in each page’s script) points to your backend (e.g. `https://api.your-domain.com` in production).
