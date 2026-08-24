"""
Integration-style smoke tests against a running API (Docker).

Run inside the backend container after seed:
  pytest -q tests/test_api_smoke.py
"""

import os

import httpx
import pytest

BASE = os.getenv("API_BASE", "http://localhost:8000/api/v1")
EMAIL = os.getenv("SEED_AGENT_EMAIL", "agent@example.com")
PASSWORD = os.getenv("SEED_AGENT_PASSWORD", "agent123!")


@pytest.fixture(scope="module")
def token() -> str:
    r = httpx.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"API not available or seed missing: {r.status_code} {r.text}")
    return r.json()["access_token"]


def test_me(token: str):
    r = httpx.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert r.status_code == 200
    assert r.json()["email"] == EMAIL.lower()


def test_customer_conversation_flow(token: str):
    h = {"Authorization": f"Bearer {token}"}
    c = httpx.post(
        f"{BASE}/customers",
        headers=h,
        json={"name": "Test Customer", "email": "test.customer@example.com"},
        timeout=30,
    )
    assert c.status_code == 201
    customer_id = c.json()["id"]

    conv = httpx.post(
        f"{BASE}/conversations",
        headers=h,
        json={"customer_id": customer_id, "channel": "WEB_CHAT", "initial_message": "Hello"},
        timeout=30,
    )
    assert conv.status_code == 201
    conversation_id = conv.json()["id"]

    msg = httpx.post(
        f"{BASE}/conversations/{conversation_id}/messages",
        headers=h,
        json={"content": "How can I help?", "sender_type": "AGENT"},
        timeout=30,
    )
    assert msg.status_code == 201

    closed = httpx.patch(
        f"{BASE}/conversations/{conversation_id}",
        headers=h,
        json={"status": "CLOSED", "priority": "HIGH"},
        timeout=30,
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"
