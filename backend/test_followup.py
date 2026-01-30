#!/usr/bin/env python3
"""
Test script for email autofollowup.
Sends a test email to the client owner's signup email, adds an "old" lead (25h ago)
with that same email, and triggers the follow-up job.

Usage:
  python test_followup.py --email you@example.com     # auto-resolve client from signup email
  python test_followup.py --client-slug your-slug     # or pass slug explicitly

Requires: backend running on port 8000, RESEND_API_KEY in backend/.env
The client must have an owner (user who signed up); test email and followup go to that email.

If ADMIN_API_KEY is set in .env, test endpoints require X-Admin-Key header (script loads it).
"""

import argparse
import os

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
DEFAULT_CLIENT = "demo"
ADMIN_KEY = (os.getenv("ADMIN_API_KEY") or "").strip()


def _headers():
    return {"X-Admin-Key": ADMIN_KEY} if ADMIN_KEY else {}


def main():
    parser = argparse.ArgumentParser(description="Test email autofollowup")
    parser.add_argument("--email", "-e", help="Signup email: auto-resolve client slug (no slug needed)")
    parser.add_argument("--client-slug", "-c", help=f"Client slug (default: {DEFAULT_CLIENT} if no --email)")
    args = parser.parse_args()

    slug = None
    email = None

    if args.email:
        try:
            r = requests.get(
                f"{BASE_URL}/test/client-slug-by-email",
                params={"email": args.email.strip()},
                headers=_headers(),
                timeout=10,
            )
            if r.status_code != 200:
                print(f"❌ {r.status_code} {r.text[:200]}")
                if r.status_code == 404:
                    print("→ No account or client for that email. Sign up first.")
                if r.status_code == 403:
                    print("→ Add ADMIN_API_KEY to backend/.env and pass X-Admin-Key, or unset ADMIN_API_KEY.")
                return 1
            data = r.json()
            slug = data["client_slug"]
            email = data.get("email", args.email)
        except requests.exceptions.ConnectionError:
            print("❌ Cannot reach backend. Is it running on port 8000?")
            print("   Start with: bash start-backend.sh")
            return 1
    else:
        slug = args.client_slug or DEFAULT_CLIENT

    print("=" * 55)
    print("Email autofollowup test")
    print("=" * 55)
    print(f"Client: {slug}")
    if email:
        print(f"Email:  {email}")
    print("(Test email + followup → client owner's signup email)")
    print()

    try:
        # 1. Send test email to client owner
        print("1. Sending test email to client owner...")
        r = requests.post(
            f"{BASE_URL}/test/send-email-to-owner",
            params={"client_slug": slug},
            headers=_headers(),
            timeout=10,
        )
        if r.status_code != 200:
            print(f"   ❌ Failed: {r.status_code} {r.text[:200]}")
            if r.status_code == 404:
                msg = (r.json().get("detail", "") or "") if r.headers.get("content-type", "").startswith("application/json") else ""
                if "no owner" in str(msg).lower():
                    print(f"   → Sign up with client '{slug}' first, or use a client that has an owner.")
                elif "Not Found" in str(msg):
                    print("   → Test endpoints disabled. Set ENABLE_TEST_ENDPOINTS=true in backend/.env")
                else:
                    print(f"   → Client '{slug}' not found. Use your dashboard client slug.")
            if r.status_code == 403:
                print("   → Add ADMIN_API_KEY to backend/.env or unset it.")
            return 1
        data = r.json()
        if not data.get("success"):
            print(f"   ❌ {data.get('error', 'Unknown error')}")
            print("   → Add RESEND_API_KEY to backend/.env and restart the backend.")
            return 1
        email = data.get("email", "")
        print(f"   ✅ Test email sent to {email}. Check your inbox.")

        # 2. Add old lead (owner's email so they receive the follow-up)
        print("\n2. Adding old lead (25h ago)...")
        r = requests.post(
            f"{BASE_URL}/test/add-old-lead",
            params={"client_slug": slug},
            headers=_headers(),
            timeout=10,
        )
        if r.status_code != 200:
            print(f"   ❌ Failed: {r.status_code} {r.text[:200]}")
            if r.status_code == 404:
                print(f"   → Client '{slug}' not found. Use your dashboard client slug.")
            if r.status_code == 400:
                print(f"   → Client has no owner. Sign up with that client first.")
            return 1
        lead = r.json()
        print(f"   ✅ Lead added: {lead.get('name')} ({lead.get('email')})")

        # 3. Run followups
        print("\n3. Running follow-up job...")
        r = requests.post(f"{BASE_URL}/test/run-followups", headers=_headers(), timeout=30)
        if r.status_code != 200:
            print(f"   ❌ Failed: {r.status_code} {r.text[:200]}")
            return 1
        print("   ✅ Job completed. Check backend terminal for '✅ Auto followup #1 sent'.")
        print(f"   → Follow-up sent to {email}. Check your inbox.")

        print("\n" + "=" * 55)
        print("Done. Check your inbox + backend logs.")
        print("=" * 55)
        return 0

    except requests.exceptions.ConnectionError:
        print("❌ Cannot reach backend. Is it running on port 8000?")
        print("   Start with: bash start-backend.sh")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
