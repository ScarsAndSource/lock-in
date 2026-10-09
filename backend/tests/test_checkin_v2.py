"""Tests for the /checkins family of endpoints (defaults, confirm, journal)."""
from datetime import date


def _create_habit(client, name="Gym"):
    resp = client.post(
        "/habits",
        json={"name": name, "target_frequency": {"type": "weekdays", "days": [0, 1, 2, 3, 4, 5, 6]}},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_defaults_endpoint_returns_200(world, user_a):
    client = world.client_as(user_a)
    _create_habit(client)
    r = client.get("/checkins/2026-12-31/defaults")
    assert r.status_code == 200
    data = r.json()
    assert data["checkin_date"] == "2026-12-31"
    assert data["already_confirmed"] is False
    assert len(data["entries"]) == 1
    assert data["entries"][0]["status"] == "done"
    assert "sleep" in data
    assert "screen_time" in data


def test_checkin_confirm_creates_logs_and_returns_200(world, user_a):
    client = world.client_as(user_a)
    hid = _create_habit(client)
    body = {
        "overrides": [{"habit_id": hid, "status": "skipped", "note": "rest day"}],
        "sleep": {"time_to_bed": "23:00:00", "time_woke": "07:00:00", "self_rated_quality": 4},
        "screen_time": {"total_minutes": 120, "source": "manual"},
        "journal_text": "Good day overall.",
    }
    r = client.post("/checkins/2026-12-31/confirm", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["checkin_date"] == "2026-12-31"
    assert len(data["entries"]) == 1
    assert data["entries"][0]["status"] == "skipped"
    assert data["sleep"]["duration_minutes"] == 480
    assert data["screen_time"]["total_minutes"] == 120


def test_checkin_confirm_upsert_replaces_existing_entry(world, user_a):
    client = world.client_as(user_a)
    hid = _create_habit(client)
    body1 = {"overrides": [{"habit_id": hid, "status": "done"}]}
    client.post("/checkins/2026-12-31/confirm", json=body1)

    body2 = {"overrides": [{"habit_id": hid, "status": "skipped"}]}
    r = client.post("/checkins/2026-12-31/confirm", json=body2)
    assert r.status_code == 200
    assert r.json()["entries"][0]["status"] == "skipped"


def test_checkin_journal_encrypted_at_rest_and_returned_plaintext(world, user_a):
    client = world.client_as(user_a)
    secret_text = "My highly private reflection for the day."
    client.post("/checkins/2026-12-31/confirm", json={"journal_text": secret_text})

    # Retrieve plaintext via the journal route
    r = client.get("/checkins/2026-12-31/journal")
    assert r.status_code == 200
    assert r.json()["journal_text"] == secret_text

    # Raw database byte storage is encrypted, not plaintext
    stored = world.checkin_repo._checkins.get((user_a, date(2026, 12, 31)))
    assert stored is not None
    assert stored.journal_encrypted is not None
    assert secret_text.encode() not in stored.journal_encrypted


def test_checkin_journal_not_found_before_creation(world, user_a):
    r = world.client_as(user_a).get("/checkins/2026-12-31/journal")
    assert r.status_code == 404


def test_checkin_users_isolated(world, user_a, user_b):
    world.client_as(user_a).post("/checkins/2026-12-31/confirm", json={"journal_text": "Secret A"})
    r = world.client_as(user_b).get("/checkins/2026-12-31/journal")
    assert r.status_code == 404
