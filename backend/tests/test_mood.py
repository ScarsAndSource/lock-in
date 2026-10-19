"""Mood in two taps: its own API, and riding along with the daily check-in."""
from app.domain import MoodLog


# ============================================================ mood API
def test_mood_roundtrip_validation_and_range(world, user_a):
    c = world.client_as(user_a)
    r = c.put("/mood/2026-12-30", json={"valence": 4, "energy": 2})
    assert r.status_code == 200 and r.json() == {"log_date": "2026-12-30", "valence": 4, "energy": 2}
    c.put("/mood/2026-12-30", json={"valence": 5, "energy": 5})                       # same day = update
    assert c.get("/mood/2026-12-30").json()["valence"] == 5
    c.put("/mood/2026-12-31", json={"valence": 1, "energy": 1})
    listed = c.get("/mood", params={"start_date": "2026-12-29", "end_date": "2026-12-31"}).json()
    assert [m["log_date"] for m in listed] == ["2026-12-30", "2026-12-31"]
    assert c.put("/mood/2026-12-30", json={"valence": 6, "energy": 3}).status_code == 422
    assert c.put("/mood/2026-12-30", json={"valence": 3}).status_code == 422
    assert c.get("/mood/2026-12-01").status_code == 404
    assert c.get("/mood", params={"start_date": "2026-12-31", "end_date": "2026-12-01"}).status_code == 422
    assert c.delete("/mood/2026-12-30").status_code == 204 and c.delete("/mood/2026-12-30").status_code == 404


def test_mood_is_private_to_its_owner(world, user_a, user_b):
    world.client_as(user_a).put("/mood/2026-12-30", json={"valence": 4, "energy": 4})
    assert world.client_as(user_b).get("/mood/2026-12-30").status_code == 404


def test_mood_cannot_be_logged_for_the_future(world, user_a):
    c = world.client_as(user_a)
    assert c.put("/mood/2027-01-15", json={"valence": 3, "energy": 3}).status_code == 422


def test_mood_rides_along_with_the_check_in(world, user_a):
    c = world.client_as(user_a)
    assert c.get("/checkins/2026-12-31/defaults").json()["mood"] is None
    out = c.post("/checkins/2026-12-31/confirm", json={"mood": {"valence": 3, "energy": 5}}).json()
    assert out["mood"] == {"log_date": "2026-12-31", "valence": 3, "energy": 5}
    assert c.get("/checkins/2026-12-31/defaults").json()["mood"]["energy"] == 5
    again = c.post("/checkins/2026-12-31/confirm", json={}).json()              # no mood sent: keep what's there
    assert again["mood"]["valence"] == 3
    assert c.post("/checkins/2026-12-31/confirm", json={"mood": {"valence": 9, "energy": 1}}).status_code == 422


def test_mood_log_rejects_out_of_range_values():
    import pytest
    from uuid import uuid4
    from datetime import date
    with pytest.raises(ValueError):
        MoodLog(user_id=uuid4(), log_date=date(2026, 12, 31), valence=0, energy=3)
    with pytest.raises(ValueError):
        MoodLog(user_id=uuid4(), log_date=date(2026, 12, 31), valence=3, energy=6)
