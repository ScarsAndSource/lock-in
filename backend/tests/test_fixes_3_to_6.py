from uuid import uuid4

from app.domain import PatternInsight


def _seed_insight(world, user_id, feedback=None):
    i = PatternInsight(
        id=uuid4(), user_id=user_id, generated_at=world.now, generated_on=world.now.date(),
        pattern_key="sleep->habits",
        insight_text="Bad sleep → habits slipped the same day: 4/5 times, vs 20% of other days.",
        next_step="Tonight: phone charging outside the bedroom before midnight.",
        source_domains=["sleep", "habits"], evidence_refs={}, narrated=False,
        voice_version="v1", model=None, user_feedback=feedback,
    )
    world.insight_repo._insights[i.id] = i
    return i


def _habit(client):
    r = client.post("/habits", json={"name": "Gym", "target_frequency": {"type": "weekdays", "days": [0, 2, 4]}})
    assert r.status_code == 201
    return r.json()["id"]


# ---- #4 insights
def test_rate_insight_stores_feedback(world, user_a):
    i = _seed_insight(world, user_a)
    r = world.client_as(user_a).post(f"/insights/{i.id}/feedback", json={"feedback": "accurate"})
    assert r.status_code == 200 and r.json()["user_feedback"] == "accurate"


def test_rate_insight_rejects_unknown_value(world, user_a):
    i = _seed_insight(world, user_a)
    r = world.client_as(user_a).post(f"/insights/{i.id}/feedback", json={"feedback": "love_it"})
    assert r.status_code == 422


def test_cannot_rate_another_users_insight(world, user_a, user_b):
    i = _seed_insight(world, user_a)
    r = world.client_as(user_b).post(f"/insights/{i.id}/feedback", json={"feedback": "accurate"})
    assert r.status_code == 404


def test_list_unrated_only(world, user_a):
    _seed_insight(world, user_a, feedback="accurate")
    open_one = _seed_insight(world, user_a)
    r = world.client_as(user_a).get("/insights", params={"unrated_only": True})
    assert [x["id"] for x in r.json()] == [str(open_one.id)]


def test_refresh_without_patterns_says_so(world, user_a):
    r = world.client_as(user_a).post("/insights/refresh")
    assert r.status_code == 200 and r.json()["skipped_reason"] == "no_patterns"


# ---- #6 habits
def test_patch_changes_schedule(world, user_a):
    c = world.client_as(user_a)
    hid = _habit(c)
    r = c.patch(f"/habits/{hid}", json={"target_frequency": {"type": "n_per_week", "count": 3}})
    assert r.status_code == 200
    assert r.json()["target_frequency"] == {"type": "n_per_week", "count": 3}


def test_patch_with_nothing_is_rejected(world, user_a):
    c = world.client_as(user_a)
    assert c.patch(f"/habits/{_habit(c)}", json={}).status_code == 422


def test_delete_habit_log_then_404(world, user_a):
    c = world.client_as(user_a)
    hid = _habit(c)
    c.post(f"/habits/{hid}/logs", json={"log_date": "2026-12-30", "status": "done"})
    assert c.delete(f"/habits/{hid}/logs/2026-12-30").status_code == 204
    assert c.delete(f"/habits/{hid}/logs/2026-12-30").status_code == 404


def test_cannot_delete_another_users_habit_log(world, user_a, user_b):
    hid = _habit(world.client_as(user_a))
    world.client_as(user_a).post(f"/habits/{hid}/logs", json={"log_date": "2026-12-30", "status": "done"})
    assert world.client_as(user_b).delete(f"/habits/{hid}/logs/2026-12-30").status_code == 404


def test_delete_sleep_and_screen_logs(world, user_a):
    c = world.client_as(user_a)
    c.post("/sleep/logs", json={"log_date": "2026-12-30", "self_rated_quality": 4})
    c.post("/screen-time/logs", json={"log_date": "2026-12-30", "total_minutes": 90, "source": "manual"})
    assert c.delete("/sleep/logs/2026-12-30").status_code == 204
    assert c.delete("/screen-time/logs/2026-12-30").status_code == 204
    assert c.delete("/sleep/logs/2026-12-30").status_code == 404
    assert c.delete("/screen-time/logs/2026-12-30").status_code == 404


# ---- #6 validation caps
def _screen(**kw):
    return {"log_date": "2026-12-30", "total_minutes": 90, "source": "manual", **kw}


def test_screen_minutes_capped_at_a_day(world, user_a):
    assert world.client_as(user_a).post("/screen-time/logs", json=_screen(total_minutes=5000)).status_code == 422


def test_breakdown_key_count_capped(world, user_a):
    big = {f"app{i}": 10 for i in range(31)}
    assert world.client_as(user_a).post("/screen-time/logs", json=_screen(category_breakdown=big)).status_code == 422


def test_breakdown_values_must_be_whole_minutes(world, user_a):
    c = world.client_as(user_a)
    assert c.post("/screen-time/logs", json=_screen(category_breakdown={"social": -5})).status_code == 422
    assert c.post("/screen-time/logs", json=_screen(category_breakdown={"social": "lots"})).status_code == 422
    assert c.post("/screen-time/logs", json=_screen(category_breakdown={"social": 60})).status_code == 200
