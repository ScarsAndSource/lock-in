"""Tests for account-level operations and the rate limiter middleware."""
from uuid import uuid4


def test_delete_account_returns_204(world, user_a):
    client = world.client_as(user_a)
    r = client.delete("/account/me")
    assert r.status_code == 204


def test_delete_account_removes_all_data(world, user_a):
    client = world.client_as(user_a)
    # create some data first
    client.post("/habits/", json={"name": "Read", "target_frequency": {"type": "daily"}})
    client.delete("/account/me")
    # re-authenticate as same user and verify data is gone
    r = client.get("/habits/")
    assert r.json() == []


def test_export_returns_200_with_json_body(world, user_a):
    client = world.client_as(user_a)
    r = client.get("/account/me/export")
    assert r.status_code == 200
    body = r.json()
    assert "habits" in body
    assert "checkins" in body


def test_unauthenticated_request_returns_401(world):
    from app.security import get_current_user_id
    from app.main import app
    # Temporarily remove the override to simulate a missing token
    overrides_backup = dict(app.dependency_overrides)
    app.dependency_overrides.pop(get_current_user_id, None)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/habits/")
    # restore
    app.dependency_overrides.update(overrides_backup)
    assert r.status_code == 401


def test_rate_limit_not_enforced_when_disabled(world, user_a):
    """Rate limiter is disabled in test env (RATE_LIMIT_ENABLED=false), so 200 expected."""
    client = world.client_as(user_a)
    for _ in range(200):
        r = client.get("/habits/")
    assert r.status_code == 200
