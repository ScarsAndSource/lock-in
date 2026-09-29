from datetime import date, time


def test_log_and_retrieve_sleep(world, user_a):
    client = world.client_as(user_a)

    resp = client.post(
        "/sleep/logs",
        json={
            "log_date": "2026-09-20",
            "time_to_bed": "23:30:00",
            "time_woke": "07:00:00",
            "self_rated_quality": 4,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["self_rated_quality"] == 4
    # 23:30 -> 07:00 crossing midnight = 7.5 hours = 450 minutes
    assert body["duration_minutes"] == 450

    fetched = client.get("/sleep/logs/2026-09-20")
    assert fetched.status_code == 200
    assert fetched.json()["duration_minutes"] == 450


def test_correcting_a_sleep_log_is_an_upsert(world, user_a):
    client = world.client_as(user_a)
    client.post(
        "/sleep/logs",
        json={"log_date": "2026-09-20", "self_rated_quality": 2},
    )
    resp = client.post(
        "/sleep/logs",
        json={"log_date": "2026-09-20", "self_rated_quality": 5},
    )
    assert resp.status_code == 200
    assert resp.json()["self_rated_quality"] == 5

    fetched = client.get("/sleep/logs/2026-09-20")
    assert fetched.json()["self_rated_quality"] == 5


def test_sleep_quality_out_of_range_rejected(world, user_a):
    client = world.client_as(user_a)
    resp = client.post(
        "/sleep/logs",
        json={"log_date": "2026-09-20", "self_rated_quality": 7},
    )
    assert resp.status_code == 422


def test_partial_sleep_log_is_valid(world, user_a):
    """A log with only self_rated_quality (no bed/wake times) must persist
    fine, with duration_minutes coming back None -- not an error."""
    client = world.client_as(user_a)
    resp = client.post(
        "/sleep/logs",
        json={"log_date": "2026-09-21", "self_rated_quality": 3},
    )
    assert resp.status_code == 200
    assert resp.json()["duration_minutes"] is None


def test_sleep_log_not_visible_to_other_user(world, user_a, user_b):
    client_a = world.client_as(user_a)
    client_a.post("/sleep/logs", json={"log_date": "2026-09-20", "self_rated_quality": 4})

    client_b = world.client_as(user_b)
    resp = client_b.get("/sleep/logs/2026-09-20")
    assert resp.status_code == 404


def test_sleep_range_validation(world, user_a):
    client = world.client_as(user_a)

    resp = client.get(
        "/sleep/logs", params={"start_date": "2026-09-20", "end_date": "2026-09-10"}
    )
    assert resp.status_code == 422

    resp = client.get(
        "/sleep/logs", params={"start_date": "2026-01-01", "end_date": "2026-12-31"}
    )
    assert resp.status_code == 422


def test_log_and_list_screen_time(world, user_a):
    client = world.client_as(user_a)

    for i, minutes in enumerate([180, 240, 90]):
        client.post(
            "/screen-time/logs",
            json={"log_date": f"2026-09-2{i}", "total_minutes": minutes, "source": "manual"},
        )

    resp = client.get(
        "/screen-time/logs",
        params={"start_date": "2026-09-20", "end_date": "2026-09-22"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [entry["total_minutes"] for entry in body] == [180, 240, 90]
    assert all(entry["source"] == "manual" for entry in body)


def test_correcting_a_screen_time_log_is_an_upsert(world, user_a):
    client = world.client_as(user_a)
    client.post(
        "/screen-time/logs",
        json={"log_date": "2026-09-20", "total_minutes": 300, "source": "manual"},
    )
    resp = client.post(
        "/screen-time/logs",
        json={"log_date": "2026-09-20", "total_minutes": 250, "source": "manual"},
    )
    assert resp.status_code == 200
    assert resp.json()["total_minutes"] == 250


def test_screen_time_category_breakdown_round_trips(world, user_a):
    client = world.client_as(user_a)
    resp = client.post(
        "/screen-time/logs",
        json={
            "log_date": "2026-09-20",
            "total_minutes": 200,
            "source": "manual",
            "category_breakdown": {"social": 120, "coding": 80},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["category_breakdown"] == {"social": 120, "coding": 80}


def test_screen_time_negative_minutes_rejected(world, user_a):
    client = world.client_as(user_a)
    resp = client.post(
        "/screen-time/logs",
        json={"log_date": "2026-09-20", "total_minutes": -5, "source": "manual"},
    )
    assert resp.status_code == 422


def test_screen_time_log_not_visible_to_other_user(world, user_a, user_b):
    client_a = world.client_as(user_a)
    client_a.post(
        "/screen-time/logs",
        json={"log_date": "2026-09-20", "total_minutes": 200, "source": "manual"},
    )

    client_b = world.client_as(user_b)
    resp = client_b.get("/screen-time/logs/2026-09-20")
    assert resp.status_code == 404
