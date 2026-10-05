import pytest

ACTIVE_BODY = {
    "name": "Get fit", "target_metric": "run 5k", "target_date": "2026-12-31",
    "habit_ids": [],
}


def test_start_mission_returns_201_with_id(world, user_a):
    client = world.client_as(user_a)
    r = client.post("/missions/", json=ACTIVE_BODY)
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "active"
    assert "id" in data


def test_get_missions_returns_the_mission(world, user_a):
    client = world.client_as(user_a)
    client.post("/missions/", json=ACTIVE_BODY)
    r = client.get("/missions/")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_cannot_start_two_active_missions(world, user_a):
    client = world.client_as(user_a)
    client.post("/missions/", json=ACTIVE_BODY)
    r = client.post("/missions/", json=ACTIVE_BODY)
    assert r.status_code == 409


def test_complete_mission(world, user_a):
    client = world.client_as(user_a)
    mission_id = client.post("/missions/", json=ACTIVE_BODY).json()["id"]
    r = client.post(f"/missions/{mission_id}/complete", json={"outcome_notes": "nailed it"})
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_abandon_mission(world, user_a):
    client = world.client_as(user_a)
    mission_id = client.post("/missions/", json=ACTIVE_BODY).json()["id"]
    r = client.post(f"/missions/{mission_id}/abandon", json={"reason": "too hard"})
    assert r.status_code == 200
    assert r.json()["status"] == "abandoned"


def test_users_cannot_see_each_others_missions(world, user_a, user_b):
    world.client_as(user_a).post("/missions/", json=ACTIVE_BODY)
    r = world.client_as(user_b).get("/missions/")
    assert r.json() == []


def test_mission_history_returns_non_active_missions(world, user_a):
    client = world.client_as(user_a)
    mid = client.post("/missions/", json=ACTIVE_BODY).json()["id"]
    client.post(f"/missions/{mid}/complete", json={"outcome_notes": ""})
    r = client.get("/missions/history")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_cannot_complete_a_completed_mission(world, user_a):
    client = world.client_as(user_a)
    mid = client.post("/missions/", json=ACTIVE_BODY).json()["id"]
    client.post(f"/missions/{mid}/complete", json={"outcome_notes": ""})
    r = client.post(f"/missions/{mid}/complete", json={"outcome_notes": ""})
    assert r.status_code == 409


def test_mission_not_found_returns_404_not_403(world, user_a):
    client = world.client_as(user_a)
    r = client.post("/missions/00000000-0000-0000-0000-000000000000/complete", json={"outcome_notes": ""})
    assert r.status_code == 404
