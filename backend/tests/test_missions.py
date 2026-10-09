"""Tests for the /missions family of endpoints."""
import pytest
from uuid import uuid4

MISSION_PAYLOAD = {
    "title": "Get fit",
    "duration_days": 30,
    "start_date": "2026-12-31",
}


def test_start_mission_returns_201_with_id(world, user_a):
    client = world.client_as(user_a)
    r = client.post("/missions", json=MISSION_PAYLOAD)
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "active"
    assert data["title"] == "Get fit"
    assert data["start_date"] == "2026-12-31"
    assert "end_date" in data
    assert "id" in data


def test_get_missions_returns_the_mission(world, user_a):
    client = world.client_as(user_a)
    client.post("/missions", json=MISSION_PAYLOAD)
    r = client.get("/missions")
    assert r.status_code == 200
    missions = r.json()
    assert len(missions) == 1
    assert missions[0]["title"] == "Get fit"


def test_get_active_mission_returns_detail(world, user_a):
    client = world.client_as(user_a)
    client.post("/missions", json=MISSION_PAYLOAD)
    r = client.get("/missions/active")
    assert r.status_code == 200
    data = r.json()
    assert data["mission"]["title"] == "Get fit"
    assert "progress" in data
    assert "habits" in data


def test_cannot_start_two_active_missions(world, user_a):
    client = world.client_as(user_a)
    client.post("/missions", json=MISSION_PAYLOAD)
    r = client.post("/missions", json=MISSION_PAYLOAD)
    assert r.status_code == 409


def test_complete_mission(world, user_a):
    client = world.client_as(user_a)
    mission_id = client.post("/missions", json=MISSION_PAYLOAD).json()["id"]
    r = client.post(f"/missions/{mission_id}/end", json={"completed": True})
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_end_mission_early(world, user_a):
    client = world.client_as(user_a)
    mission_id = client.post("/missions", json=MISSION_PAYLOAD).json()["id"]
    r = client.post(f"/missions/{mission_id}/end", json={"completed": False})
    assert r.status_code == 200
    assert r.json()["status"] == "ended_early"


def test_users_cannot_see_each_others_missions(world, user_a, user_b):
    world.client_as(user_a).post("/missions", json=MISSION_PAYLOAD)
    r = world.client_as(user_b).get("/missions")
    assert r.json() == []


def test_cannot_end_an_already_ended_mission(world, user_a):
    client = world.client_as(user_a)
    mid = client.post("/missions", json=MISSION_PAYLOAD).json()["id"]
    client.post(f"/missions/{mid}/end", json={"completed": True})
    r = client.post(f"/missions/{mid}/end", json={"completed": True})
    assert r.status_code == 409


def test_mission_not_found_returns_404(world, user_a):
    client = world.client_as(user_a)
    r = client.post(f"/missions/{uuid4()}/end", json={"completed": True})
    assert r.status_code == 404
