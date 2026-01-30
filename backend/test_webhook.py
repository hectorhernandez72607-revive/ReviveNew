#!/usr/bin/env python3
"""
Test script to simulate Google Forms submissions to the webhook endpoint.
Each paying client has their own webhook URL: /webhook/lead/{client_slug}

Usage:
  python test_webhook.py              # uses client 'demo'
  python test_webhook.py acme-corp    # uses client 'acme-corp'
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8000"
DEFAULT_CLIENT = "demo"


def webhook_url(client_slug: str) -> str:
    return f"{BASE_URL}/webhook/lead/{client_slug}"


def test_webhook(client_slug: str, name: str, email: str, phone: str = "", source: str = "Google Forms") -> bool:
    """Test the webhook endpoint with sample data for a given client."""
    payload = {
        "name": name,
        "email": email,
        "phone": phone,
        "source": source
    }
    url = webhook_url(client_slug)

    try:
        print(f"\n📤 Sending test lead to client '{client_slug}': {name} ({email})")
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success! Lead added with ID: {data['id']}")
            print(f"   Status: {data['status']}")
            print(f"   Source: {data.get('source', 'N/A')}")
            return True
        elif response.status_code == 404:
            print(f"❌ Client '{client_slug}' not found. Create it first: POST /clients")
            return False
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"   Response: {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Is your backend running on port 8000?")
        print("   Start it with: uvicorn main2:app --reload --port 8000")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    client = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CLIENT
    print("=" * 50)
    print("Google Forms Webhook Test Script")
    print("=" * 50)
    print(f"Client: {client}")
    print(f"URL: {webhook_url(client)}")

    test_cases = [
        ("John Doe", "john.doe@example.com", "555-1234", "Google Forms"),
        ("Jane Smith", "jane.smith@example.com", "", "Google Forms"),
        ("Bob Johnson", "bob@example.com", "555-5678", "Google Forms"),
    ]

    print(f"\nTesting {len(test_cases)} leads...")
    success_count = 0

    for name, email, phone, source in test_cases:
        if test_webhook(client, name, email, phone, source):
            success_count += 1

    print("\n" + "=" * 50)
    print(f"Results: {success_count}/{len(test_cases)} successful")
    print("=" * 50)

    if success_count == len(test_cases):
        print("\n✅ All tests passed! Your webhook is working.")
        print("   Use this URL in Google Apps Script for this client:")
        print(f"   {webhook_url(client)}")
    else:
        print("\n⚠️  Some tests failed. Check your backend logs.")
        sys.exit(1)
