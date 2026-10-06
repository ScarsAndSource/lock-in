"""Integration tests for the /retros family of endpoints."""
import json
from datetime import date, datetime, timezone
from uuid import uuid4

from app.domain import PatternInsight
from app.services.llm import LLMUnavailableError

GOOD_RETRO = json.dumps({
    "observation": "Wed is the chain: bad sleep that morning, a heavy screen day on Tue, then the habit skipped. Outside that you had 5 clean days.",
    "next_step": "Next week: when Tue runs heavy, set lights-out before midnight and log the sleep.",
    "cited_days": ["2026-12-23", "2026-12-22"],
})


def seed_retro_week(client, previous_week=False):
    """Week of 12/21–12/27: bad sleep + skipped habit on Wed after a heavy screen day on Tue."""
    hid = client.post("/habits/", json={
        "name": "Gym",
        "target_frequency": {"type": "weekdays", "days": [0, 1, 2, 3, 4, 5, 6]},
    }).json()["id"]
    for day in range(21, 28):
        bad = day == 23
        client.post("/sleep/", json={
            "log_date": f"2026-12-{day:02d}",
            "time_to_bed": "01:00:00" if bad else "23:00:00",
            "time_woke": "05:00:00" if bad else "07:00:00",
            "self_rated_quality": 2 if bad else 4,
        })
        client.post(f"/habits/{hid}/log", json={
            "log_date": f"2026-12-{day:02d}",
            "status": "skipped" if bad else "done",
        })
    client.post("/screen-time/", json={
        "log_date": "2026-12-22", "total_minutes": 300, "source": "manual",
    })
    if previous_week:
        for day in range(14, 21):
            client.post(f"/habits/{hid}/log", json={
                "log_date": f"2026-12-{day:02d}", "status": "done",
            })
    return hid


def _stale_insight(user_id, i):
    return PatternInsight(
        id=uuid4(), user_id=user_id,
        generated_at=datetime(2026, 12, 1 + i, 12, tzinfo=timezone.utc),
        generated_on=date(2026, 12, 1 + i), pattern_key=f"k{i}",
        insight_text="t", next_step="n", source_domains=[], evidence_refs={},
        narrated=False, voice_version="v1", model=None,
    )


def test_retro_tells_the_chain_with_dates_when_llm_succeeds(world, user_a):
    client = world.client_as(user_a)
    seed_retro_week(client)
    world.llm.replies = [GOOD_RETRO]

    resp = client.post("/retros/generate", json={})
    assert resp.status_code == 201
    body = resp.json()
    assert body["week_start"] == "2026-12-21"
    assert body["week_end"] == "2026-12-27"
    assert body["status"] == "ready"
    assert body["narrated"] is True
    assert body["evidence_refs"]["cited_days"] == ["2026-12-23", "2026-12-22"]

    chain = body["summary"]["chains"][0]
    assert chain["slip_date"] == "2026-12-23"
    assert [u["signal"] for u in chain["caused_by"]] == ["sleep", "screen_time"]
    assert body["summary"]["clean_day_count"] == 5
    assert body["summary"]["unexplained_slips"] == []
    assert body["pending_ratings"] == []


def test_generate_is_idempotent_second_call_returns_200(world, user_a):
    client = world.client_as(user_a)
    seed_retro_week(client)
    world.llm.replies = [GOOD_RETRO]
    first = client.post("/retros/generate", json={}).json()

    again = client.post("/retros/generate", json={})
    assert again.status_code == 200
    assert again.json()["id"] == first["id"]
    assert len(world.llm.calls) == 1   # LLM called only once


def test_retro_retrievable_via_latest_by_date_and_list(world, user_a):
    client = world.client_as(user_a)
    seed_retro_week(client)
    world.llm.replies = [GOOD_RETRO]
    created = client.post("/retros/generate", json={}).json()

    assert client.get("/retros/latest").json()["id"] == created["id"]
    assert client.get("/retros/2026-12-21").json()["id"] == created["id"]
    assert client.get("/retros/2026-12-14").status_code == 404
    assert [r["id"] for r in client.get("/retros").json()] == [created["id"]]


def test_llm_outage_produces_deterministic_chain_text(world, user_a):
    client = world.client_as(user_a)
    seed_retro_week(client)
    world.llm.error = LLMUnavailableError("down")

    body = client.post("/retros/generate", json={}).json()
    assert body["narrated"] is False
    assert body["narrative"] == "Wed: habits slipped, after bad sleep (Wed) and a heavy screen day (Tue)."
    assert body["next_step"].startswith("Tonight: phone charging outside")


def test_tone_gate_failure_falls_back_to_deterministic_text(world, user_a):
    client = world.client_as(user_a)
    seed_retro_week(client)
    # Both replies fail validation (tone gate rejects prescriptive language)
    bad = json.dumps({"observation": "You're lazy and always skip.", "next_step": "Try harder!", "cited_days": ["2026-12-23"]})
    world.llm.replies = [bad, bad]

    body = client.post("/retros/generate", json={}).json()
    assert body["narrated"] is False
    assert len(world.llm.calls) == 2
    assert body["narrative"].startswith("Wed:")


def test_empty_week_gets_honest_no_data_answer(world, user_a):
    body = world.client_as(user_a).post("/retros/generate", json={}).json()
    assert body["narrated"] is False
    assert "isn't enough logged" in body["narrative"]


def test_only_completed_monday_weeks_are_valid(world, user_a):
    client = world.client_as(user_a)
    # Still running (this week)
    assert client.post("/retros/generate", json={"week_start": "2026-12-28"}).status_code == 422
    # Not a Monday
    assert client.post("/retros/generate", json={"week_start": "2026-12-22"}).status_code == 422
    # Too far back (> 26 weeks)
    assert client.post("/retros/generate", json={"week_start": "2026-01-05"}).status_code == 422


def test_unrated_insights_surface_and_block_refresh(world, user_a):
    client = world.client_as(user_a)
    seed_retro_week(client)
    # Seed 3 stale unrated insights directly into the repo
    for i in range(3):
        stale = _stale_insight(user_a, i)
        world.insight_repo._insights[stale.id] = stale
    world.llm.replies = [GOOD_RETRO]

    retro = client.post("/retros/generate", json={}).json()
    assert len(retro["pending_ratings"]) == 3

    done = client.post("/retros/2026-12-21/complete").json()
    assert done["retro"]["completed_at"] is not None
    assert done["insights"]["generated"] == []
    assert done["insights"]["skipped_reason"] == "rate_previous_first"


def test_complete_is_idempotent_and_second_call_returns_already_completed(world, user_a):
    client = world.client_as(user_a)
    seed_retro_week(client)
    world.llm.replies = [GOOD_RETRO]
    client.post("/retros/generate", json={})
    first = client.post("/retros/2026-12-21/complete").json()
    assert first["insights"]["skipped_reason"] == "no_patterns"

    second = client.post("/retros/2026-12-21/complete").json()
    assert second["insights"]["skipped_reason"] == "already_completed"


def test_complete_nonexistent_retro_returns_404(world, user_a):
    assert world.client_as(user_a).post("/retros/2026-12-14/complete").status_code == 404


def test_retros_are_user_isolated(world, user_a, user_b):
    client_a = world.client_as(user_a)
    seed_retro_week(client_a)
    world.llm.replies = [GOOD_RETRO]
    client_a.post("/retros/generate", json={})

    client_b = world.client_as(user_b)
    assert client_b.get("/retros").json() == []
    assert client_b.get("/retros/2026-12-21").status_code == 404
    assert client_b.get("/retros/latest").status_code == 404
    assert client_b.post("/retros/2026-12-21/complete").status_code == 404


def test_retros_appear_in_account_export(world, user_a):
    client = world.client_as(user_a)
    seed_retro_week(client)
    world.llm.replies = [GOOD_RETRO]
    client.post("/retros/generate", json={})

    export = client.get("/account/me/export").json()
    assert len(export["weekly_retros"]) == 1


def test_job_module_is_importable():
    import app.jobs.generate_retros as job
    assert callable(job.main) and callable(job.build_retro_service)
