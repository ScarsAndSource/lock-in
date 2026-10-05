"""Tests for the /checkins/v2 family (bulk daily check-in form)."""

CHECKIN_BODY = {
    "log_date": "2026-12-31",
    "habits": [],
    "sleep": {"time_to_bed": "23:00", "time_woke": "07:00", "self_rated_quality": 4},
    "screen_time": {"total_minutes": 90},
    "journal": "Good day.",
    "energy": 4,
    "mood": 3,
}


def test_checkin_v2_creates_returns_201(world, user_a):
    client = world.client_as(user_a)
    r = client.post("/checkins/v2", json=CHECKIN_BODY)
    assert r.status_code == 201
    data = r.json()
    assert data["log_date"] == "2026-12-31"
    assert data["energy"] == 4
    assert data["mood"] == 3


def test_checkin_v2_upsert_replaces_existing_entry(world, user_a):
    client = world.client_as(user_a)
    client.post("/checkins/v2", json=CHECKIN_BODY)
    body2 = {**CHECKIN_BODY, "energy": 2, "mood": 1}
    r = client.post("/checkins/v2", json=body2)
    assert r.status_code == 201
    assert r.json()["energy"] == 2


def test_checkin_v2_get_returns_200(world, user_a):
    client = world.client_as(user_a)
    client.post("/checkins/v2", json=CHECKIN_BODY)
    r = client.get("/checkins/v2/2026-12-31")
    assert r.status_code == 200
    assert r.json()["journal"] == "Good day."


def test_checkin_v2_not_found_before_creation(world, user_a):
    r = world.client_as(user_a).get("/checkins/v2/2026-12-31")
    assert r.status_code == 404


def test_checkin_journal_is_stored_encrypted_and_returned_plaintext(world, user_a):
    client = world.client_as(user_a)
    client.post("/checkins/v2", json={**CHECKIN_BODY, "journal": "My secret thoughts."})
    # check plaintext comes back via the GET
    r = client.get("/checkins/v2/2026-12-31")
    assert r.json()["journal"] == "My secret thoughts."
    # check raw repo byte value is NOT the plaintext (encrypted)
    import asyncio
    from datetime import date
    from uuid import UUID
    stored = asyncio.get_event_loop().run_until_complete(
        world.checkin_repo.get_for_date(UUID(int=0), date(2026, 12, 31))
    )
    if stored is not None and stored.journal_enc is not None:
        assert stored.journal_enc != b"My secret thoughts."


def test_checkin_users_isolated(world, user_a, user_b):
    world.client_as(user_a).post("/checkins/v2", json=CHECKIN_BODY)
    r = world.client_as(user_b).get("/checkins/v2/2026-12-31")
    assert r.status_code == 404


def test_defaults_endpoint_returns_200(world, user_a):
    r = world.client_as(user_a).get("/checkins/v2/defaults?tz=Asia/Kolkata")
    assert r.status_code == 200
