"""Tests for pause shortcuts: GET /pauses/shortcuts, GET /pauses/habits,
POST /pauses/quick, POST /pauses/resume."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.pause_shortcuts_service import preset_range, shortcut_list

EVERY_DAY = {"type": "weekdays", "days": [0, 1, 2, 3, 4, 5, 6]}
# world.now = 2026-12-31 12:00 UTC => local today is 2026-12-31 (Thursday, weekday 3)
TODAY = date(2026, 12, 31)


def _habit(c, name="Gym"):
    r = c.post("/habits", json={"name": name, "target_frequency": EVERY_DAY})
    assert r.status_code == 201
    return r.json()["id"]


# ============================================================ unit: preset helpers

def test_preset_ranges_from_thursday():
    assert preset_range("today", TODAY) == (TODAY, TODAY)
    assert preset_range("3_days", TODAY) == (TODAY, TODAY + timedelta(days=2))
    # Thursday (3) + (6 - 3) = Sunday
    assert preset_range("this_week", TODAY) == (TODAY, TODAY + timedelta(days=3))
    assert preset_range("1_week", TODAY) == (TODAY, TODAY + timedelta(days=6))
    assert preset_range("2_weeks", TODAY) == (TODAY, TODAY + timedelta(days=13))


def test_shortcut_list_drops_duplicates_on_sunday():
    sunday = date(2026, 12, 27)  # weekday() == 6
    keys = [s.key for s in shortcut_list(sunday)]
    # "this_week" (through Sunday = today) == "today" => duplicate dropped
    assert "this_week" not in keys
    assert "today" in keys


def test_shortcut_list_on_a_non_sunday_has_all_presets():
    assert len(shortcut_list(TODAY)) == 5  # Thursday: all 5 distinct ranges


# ============================================================ GET /pauses/shortcuts

def test_shortcuts_endpoint_returns_list(world, user_a):
    c = world.client_as(user_a)
    r = c.get("/pauses/shortcuts")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 4  # at least 4 (or 5 if no duplicates)
    today_entry = next(s for s in body if s["key"] == "today")
    assert today_entry["start_date"] == str(TODAY)
    assert today_entry["end_date"] == str(TODAY)
    assert today_entry["days"] == 1


# ============================================================ GET /pauses/habits

def test_overview_shows_all_active_habits_as_active_when_no_pauses(world, user_a):
    c = world.client_as(user_a)
    gym = _habit(c, "Gym")
    read = _habit(c, "Read")
    body = c.get("/pauses/habits").json()
    assert body["global_pause"] is None
    rows = {r["habit_id"]: r for r in body["habits"]}
    assert rows[gym]["state"] == "active" and rows[read]["state"] == "active"
    assert not rows[gym]["effective_paused"]


def test_overview_shows_paused_habit_and_global_pause(world, user_a):
    c = world.client_as(user_a)
    gym = _habit(c, "Gym")
    _habit(c, "Read")
    c.post("/pauses", json={"start_date": str(TODAY), "end_date": str(TODAY + timedelta(days=2)), "habit_id": gym})
    c.post("/pauses", json={"start_date": str(TODAY), "end_date": str(TODAY + timedelta(days=1))})
    body = c.get("/pauses/habits").json()
    assert body["global_pause"] is not None
    rows = {r["habit_id"]: r for r in body["habits"]}
    assert rows[gym]["state"] == "paused" and rows[gym]["paused_by"] == "habit"
    assert rows[gym]["effective_paused"] is True


# ============================================================ POST /pauses/quick

def test_quick_creates_a_pause_for_the_preset(world, user_a):
    c = world.client_as(user_a)
    gym = _habit(c, "Gym")
    r = c.post("/pauses/quick", json={"preset": "3_days", "habit_id": gym})
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is True
    assert body["end_date"] == str(TODAY + timedelta(days=2))
    assert body["habit_id"] == gym


def test_quick_extends_a_running_pause_instead_of_stacking(world, user_a):
    c = world.client_as(user_a)
    gym = _habit(c, "Gym")
    # create a "today" pause first
    r1 = c.post("/pauses/quick", json={"preset": "today", "habit_id": gym})
    assert r1.status_code == 200
    pause_id = r1.json()["id"]
    # extend with a longer preset: should extend the same pause
    r2 = c.post("/pauses/quick", json={"preset": "1_week", "habit_id": gym})
    assert r2.status_code == 200
    body = r2.json()
    assert body["id"] == pause_id  # same pause object
    assert body["end_date"] == str(TODAY + timedelta(days=6))
    # no new pause was created
    pauses = c.get("/pauses").json()
    assert len(pauses) == 1


def test_quick_with_shorter_preset_does_not_shorten_existing(world, user_a):
    c = world.client_as(user_a)
    gym = _habit(c, "Gym")
    c.post("/pauses/quick", json={"preset": "1_week", "habit_id": gym})
    r = c.post("/pauses/quick", json={"preset": "today", "habit_id": gym})
    assert r.status_code == 200
    assert r.json()["end_date"] == str(TODAY + timedelta(days=6))  # unchanged


def test_quick_for_unknown_habit_returns_404(world, user_a, user_b):
    c = world.client_as(user_a)
    other_gym = _habit(world.client_as(user_b), "Gym")
    c = world.client_as(user_a)
    r = c.post("/pauses/quick", json={"preset": "today", "habit_id": other_gym})
    assert r.status_code == 404


# ============================================================ POST /pauses/resume

def test_resume_ends_a_running_pause_and_today_counts_again(world, user_a):
    c = world.client_as(user_a)
    gym = _habit(c, "Gym")
    # pause started yesterday, still running today
    yesterday = TODAY - timedelta(days=1)
    c.post("/pauses", json={
        "start_date": str(yesterday), "end_date": str(TODAY + timedelta(days=2)), "habit_id": gym,
    })
    r = c.post("/pauses/resume", json={"habit_id": gym})
    assert r.status_code == 200
    body = r.json()
    assert body["resumed"] == 1 and body["still_paused_by_all"] is False
    pauses = c.get("/pauses", params={"include_past": "true"}).json()
    # pause now ends yesterday (today is no longer covered)
    assert pauses[0]["end_date"] == str(yesterday)
    assert pauses[0]["active"] is False


def test_resume_deletes_a_pause_that_started_today(world, user_a):
    c = world.client_as(user_a)
    gym = _habit(c, "Gym")
    c.post("/pauses", json={"start_date": str(TODAY), "end_date": str(TODAY + timedelta(days=3)), "habit_id": gym})
    r = c.post("/pauses/resume", json={"habit_id": gym})
    assert r.status_code == 200
    assert r.json()["resumed"] == 1
    assert c.get("/pauses").json() == []  # deleted


def test_resume_reports_still_paused_when_global_pause_also_covers(world, user_a):
    c = world.client_as(user_a)
    gym = _habit(c, "Gym")
    c.post("/pauses", json={"start_date": str(TODAY), "end_date": str(TODAY + timedelta(days=1)), "habit_id": gym})
    c.post("/pauses", json={"start_date": str(TODAY), "end_date": str(TODAY + timedelta(days=1))})
    r = c.post("/pauses/resume", json={"habit_id": gym})
    assert r.status_code == 200
    assert r.json()["still_paused_by_all"] is True


def test_resume_with_no_running_pause_returns_zero(world, user_a):
    c = world.client_as(user_a)
    gym = _habit(c, "Gym")
    r = c.post("/pauses/resume", json={"habit_id": gym})
    assert r.status_code == 200
    assert r.json()["resumed"] == 0
