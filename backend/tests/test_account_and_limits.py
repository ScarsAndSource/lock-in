"""Tests for account-level operations (/me, /me/export) and the rate limiter middleware."""
from uuid import uuid4


def test_get_me_returns_profile(world, user_a):
    client = world.client_as(user_a)
    r = client.get("/me")
    assert r.status_code == 200
    data = r.json()
    assert data["timezone"] == "UTC"
    assert data["tone_preference"] == "direct"
    assert "today" in data


def test_delete_account_with_confirmation_returns_200(world, user_a):
    client = world.client_as(user_a)
    r = client.request("DELETE", "/me", json={"confirm": "DELETE MY DATA"})
    assert r.status_code == 200
    assert "deleted" in r.json()


def test_delete_account_requires_exact_confirmation(world, user_a):
    client = world.client_as(user_a)
    r = client.request("DELETE", "/me", json={"confirm": "WRONG CONFIRMATION"})
    assert r.status_code == 422


def test_delete_account_removes_all_data(world, user_a):
    client = world.client_as(user_a)
    # create some data first
    client.post("/habits", json={"name": "Read", "target_frequency": {"type": "weekdays", "days": [0, 1, 2, 3, 4, 5, 6]}})
    client.request("DELETE", "/me", json={"confirm": "DELETE MY DATA"})
    # verify data is gone
    r = client.get("/habits")
    assert r.json() == []


def test_export_returns_200_with_json_body(world, user_a):
    client = world.client_as(user_a)
    r = client.get("/me/export")
    assert r.status_code == 200
    body = r.json()
    assert "format_version" in body
    assert "data" in body
    assert "habit_definitions" in body["data"]
    assert "daily_checkins" in body["data"]


def test_unauthenticated_request_returns_401(world):
    from app.main import app
    from app.security import get_current_user_id
    # Temporarily remove the override to simulate a missing token
    overrides_backup = dict(app.dependency_overrides)
    app.dependency_overrides.pop(get_current_user_id, None)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/habits")
    # restore
    app.dependency_overrides.update(overrides_backup)
    assert r.status_code == 401


def test_rate_limit_not_enforced_when_disabled(world, user_a):
    """Rate limiter is disabled in test env (RATE_LIMIT_ENABLED=false), so 200 expected."""
    client = world.client_as(user_a)
    for _ in range(50):
        r = client.get("/habits")
    assert r.status_code == 200
