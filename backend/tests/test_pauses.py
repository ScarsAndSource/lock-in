import asyncio
from datetime import date

import pytest

from app.services.profile_service import ProfileService
from app.services.stats_service import StatsService

EVERY_DAY = {"type": "weekdays", "days": [0, 1, 2, 3, 4, 5, 6]}


def _habit(c, name="Gym"):
    r = c.post("/habits", json={"name": name, "target_frequency": EVERY_DAY})
    assert r.status_code == 201
    return r.json()["id"]


def _stats(world):
    return StatsService(
        world.habit_repo,
        world.sleep_repo,
        world.screen_time_repo,
        ProfileService(world.profile_repo, world._clock),
        pause_repo=world.pause_repo,
    )


def test_a_pause_can_target_one_habit_and_rejects_foreign_or_archived_ones(world, user_a, user_b):
    c = world.client_as(user_a)
    hid = _habit(c)
    ok = c.post("/pauses", json={"start_date": "2026-12-28", "end_date": "2026-12-30", "habit_id": hid})
    assert ok.status_code == 201 and ok.json()["habit_id"] == hid
    assert world.client_as(user_b).post(
        "/pauses", json={"start_date": "2026-12-28", "end_date": "2026-12-30", "habit_id": hid}
    ).status_code == 404
    c = world.client_as(user_a)
    c.patch(f"/habits/{hid}", json={"archived": True})
    assert c.post("/pauses", json={"start_date": "2026-12-28", "end_date": "2026-12-30", "habit_id": hid}).status_code == 404
    assert c.get("/pauses", params={"habit_id": hid}).json()[0]["habit_id"] == hid


def test_pausing_one_habit_changes_only_its_consistency(world, user_a):
    c = world.client_as(user_a)
    gym, read = _habit(c, "Gym"), _habit(c, "Read")
    for day in ("2026-12-24", "2026-12-25", "2026-12-26", "2026-12-27"):
        for hid in (gym, read):
            c.post(f"/habits/{hid}/logs", json={"log_date": day, "status": "done"})
    stats = _stats(world)

    def pct():
        items = asyncio.run(stats.consistency(user_a, date(2026, 12, 30), 7))[1]
        return {i.habit_name: i.consistency_pct for i in items}

    assert pct() == {"Gym": 66.7, "Read": 66.7}
    c.post("/pauses", json={"start_date": "2026-12-28", "end_date": "2026-12-29", "habit_id": gym})
    assert pct() == {"Gym": 100.0, "Read": 66.7}


def test_a_paused_habit_no_longer_drags_the_days_chain_state(world, user_a):
    c = world.client_as(user_a)
    gym, read = _habit(c, "Gym"), _habit(c, "Read")
    c.post(f"/habits/{read}/logs", json={"log_date": "2026-12-28", "status": "done"})  # gym unlogged
    stats = _stats(world)
    state = lambda: {d.day.isoformat(): d.habits for d in asyncio.run(stats.chain(user_a, date(2026, 12, 30), 4))[1]}
    assert state()["2026-12-28"] == "ok"  # 1 of 2 scheduled habits
    c.post("/pauses", json={"start_date": "2026-12-28", "end_date": "2026-12-28", "habit_id": gym})
    assert state()["2026-12-28"] == "good"  # only Read counts that day


def test_a_paused_habit_leaves_the_checkin_and_no_default_is_guessed(world, user_a):
    c = world.client_as(user_a)
    gym, read = _habit(c, "Gym"), _habit(c, "Read")
    c.post("/pauses", json={"start_date": "2026-12-31", "end_date": "2026-12-31", "habit_id": gym})
    entries = {e["habit_name"]: e for e in c.get("/checkins/2026-12-31/defaults").json()["entries"]}
    assert entries["Gym"]["is_scheduled"] is False and entries["Gym"]["status"] is None and entries["Gym"]["reason"] == "Paused."
    assert entries["Read"]["is_scheduled"] is True
    assert c.post("/checkins/2026-12-31/confirm", json={}).status_code == 200
    logged = {l.habit_id for l in world.habit_repo._logs.values() if l.log_date == date(2026, 12, 31)}
    assert gym not in {str(i) for i in logged} and read in {str(i) for i in logged}


def test_a_global_pause_rests_every_habit_in_the_checkin(world, user_a):
    c = world.client_as(user_a)
    _habit(c, "Gym")
    _habit(c, "Read")
    c.post("/pauses", json={"start_date": "2026-12-31", "end_date": "2027-01-02"})
    assert all(e["is_scheduled"] is False for e in c.get("/checkins/2026-12-31/defaults").json()["entries"])


def test_a_habit_plan_goes_quiet_while_its_habit_is_paused(world, user_a):
    c = world.client_as(user_a)
    gym = _habit(c, "Gym")
    c.post("/intentions", json={
        "linked_domain": "habit",
        "linked_entity_id": gym,
        "cue": "I put on my shoes",
        "action": "I walk to the gym",
    })
    assert len(c.get("/intentions/due").json()) == 1
    c.post("/pauses", json={"start_date": "2026-12-31", "end_date": "2026-12-31", "habit_id": gym})
    assert c.get("/intentions/due").json() == []


def test_end_pause_today_and_delete(world, user_a):
    c = world.client_as(user_a)
    p = c.post("/pauses", json={"start_date": "2026-12-30", "end_date": "2027-01-05"}).json()
    assert p["active"] is True
    ended = c.post(f"/pauses/{p['id']}/end").json()
    assert ended["end_date"] == "2026-12-31"
    assert c.delete(f"/pauses/{p['id']}").status_code == 204
    assert c.delete(f"/pauses/{p['id']}").status_code == 404
