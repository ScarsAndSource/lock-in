import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.domain import WeeklyRetro
from app.services.llm import LLMBudgetExceeded
from app.services.week_mode import (
    ROUGH_BANNED,
    ROUGH_MAX_OBSERVATION,
    ROUGH_MAX_STEP,
    fallback_for_mode,
    fallback_rough,
    narrate_retro,
    resolve_week_mode,
    signals,
)
from app.voice_config import VOICE_VERSION, retro_system_prompt
from tests.conftest import FIXED_NOW, FakeLLMClient

EVERY_DAY = {"type": "weekdays", "days": [0, 1, 2, 3, 4, 5, 6]}

GOOD_CHAT = json.dumps({
    "answer": "Gym held on Wednesday. Only one day is logged so far, so there's no pattern to read yet.",
    "next_step": "Log tomorrow's check-in so a second day exists.",
    "cited_days": ["2026-12-30"],
})


def _habit(c, name="Gym"):
    r = c.post("/habits", json={"name": name, "target_frequency": EVERY_DAY})
    assert r.status_code == 201
    return r.json()["id"]


def _seed_data(c):
    hid = _habit(c)
    c.post(f"/habits/{hid}/logs", json={"log_date": "2026-12-30", "status": "done"})
    return hid


# ============================================================ rough-week mode

def _day(date_, **states):
    base = {
        "date": date_, "weekday": "Mon", "habits": "none", "sleep": "none",
        "screen_time": "none", "study": "none", "urges": "none",
    }
    return {**base, **states}


def _summary(
    *, days=None, habit_pct=70.0, relapsed=0, follow=None, planned=0,
    clean=None, chains=None, unexplained=None,
):
    days = days if days is not None else [_day(f"2026-12-{21 + i}", habits="good") for i in range(7)]
    return {
        "week": {"start": "2026-12-21", "end": "2026-12-27", "days": 7},
        "days": days,
        "habit_overall_pct": habit_pct,
        "clean_days": clean or [],
        "clean_day_count": len(clean or []),
        "chains": chains or [],
        "unexplained_slips": unexplained or [],
        "study": {"follow_through_pct": follow, "planned_minutes": planned},
        "urges": {"relapsed": relapsed, "resisted": 2},
    }


BAD_DAYS = [_day(f"2026-12-{21 + i}", habits="bad") for i in range(5)] + [
    _day("2026-12-26"), _day("2026-12-27"),
]


def test_a_solid_week_is_normal():
    assert resolve_week_mode(_summary()).mode == "normal"


def test_two_signals_make_a_rough_week_and_report_their_reasons():
    wm = resolve_week_mode(_summary(days=BAD_DAYS, habit_pct=30.0))
    assert wm.mode == "rough" and wm.source == "auto"
    assert set(wm.reasons) == {"many_slip_days", "low_habit_consistency"}


def test_one_signal_alone_is_not_enough():
    assert resolve_week_mode(_summary(days=BAD_DAYS, habit_pct=70.0)).mode == "normal"
    assert resolve_week_mode(_summary(habit_pct=20.0)).mode == "normal"


def test_other_signal_pairs_count():
    assert resolve_week_mode(_summary(habit_pct=30.0, relapsed=3)).mode == "rough"
    assert resolve_week_mode(_summary(relapsed=4, follow=20.0, planned=300)).mode == "rough"


def test_a_thin_week_is_never_called_rough():
    thin = [_day("2026-12-21", habits="bad"), _day("2026-12-22", habits="bad")] + [
        _day(f"2026-12-{23 + i}") for i in range(5)
    ]
    assert signals(_summary(days=thin, habit_pct=10.0, relapsed=5)) == []
    assert resolve_week_mode(_summary(days=thin, habit_pct=10.0, relapsed=5)).mode == "normal"


def test_the_user_can_override_the_read_either_way():
    rough_week = _summary(days=BAD_DAYS, habit_pct=30.0)
    assert resolve_week_mode(rough_week, "normal").mode == "normal"
    assert resolve_week_mode(rough_week, "normal").source == "user"
    assert resolve_week_mode(_summary(), "rough").mode == "rough"
    assert resolve_week_mode(rough_week, "auto").source == "auto"


CHAIN = {
    "slip_date": "2026-12-24",
    "weekday": "Thu",
    "slips": ["habits"],
    "caused_by": [{"signal": "sleep", "date": "2026-12-24", "weekday": "Thu"}],
}


def test_rough_fallback_is_short_one_chain_and_one_minimum_step():
    s = _summary(
        days=BAD_DAYS, habit_pct=30.0,
        clean=[{"date": "2026-12-23", "weekday": "Wed"}],
        chains=[CHAIN, {**CHAIN, "slip_date": "2026-12-25"}],
    )
    s["week_mode"] = resolve_week_mode(s).as_dict()
    text, step, cited = fallback_for_mode(s)
    assert text.startswith("Wed held") and "habits slipped" in text and "bad sleep" in text
    assert len(text) <= ROUGH_MAX_OBSERVATION and len(step) <= ROUGH_MAX_STEP
    assert text.count("Thu:") == 1 and set(cited) == {"2026-12-23", "2026-12-24"}


def test_rough_fallback_with_no_data_is_honest():
    s = _summary(days=[_day(f"2026-12-{21 + i}") for i in range(7)], habit_pct=None)
    s["urges"] = {"relapsed": 0, "resisted": 0}  # nothing to show at all
    text, step, cited = fallback_rough(s)
    assert "no logged data" in text and cited == []


def test_rough_prompt_is_a_different_task_and_the_voice_is_versioned():
    assert "worked badly" not in retro_system_prompt("normal")
    assert "went badly in the data" in retro_system_prompt("rough")
    assert "REJECT (consolation)" in retro_system_prompt("rough") and VOICE_VERSION == "v3"


def _rough_summary():
    s = _summary(
        days=BAD_DAYS, habit_pct=30.0,
        clean=[{"date": "2026-12-23", "weekday": "Wed"}],
        chains=[CHAIN],
    )
    s["week_mode"] = resolve_week_mode(s).as_dict()
    return s


GOOD_ROUGH = json.dumps({
    "observation": "Wednesday held: nothing broke. Thursday: habits slipped after bad sleep.",
    "next_step": "Monday: do the smallest version of one habit and log it.",
    "cited_days": ["2026-12-23"],
})


def test_rough_narration_uses_the_rough_prompt_and_accepts_a_tight_answer():
    llm = FakeLLMClient()
    llm.replies = [GOOD_ROUGH]
    out = asyncio.run(narrate_retro(llm, _rough_summary()))
    assert out is not None and out.next_step.startswith("Monday")
    assert llm.calls[0][0][0]["content"] == retro_system_prompt("rough")


@pytest.mark.parametrize("bad", [
    {"observation": "Tough week, but don't worry, you've got this.", "next_step": "Monday: one habit.", "cited_days": ["2026-12-23"]},
    {"observation": "It's okay, a bad week happens.", "next_step": "Monday: one habit.", "cited_days": ["2026-12-23"]},
    {"observation": "x" * 301, "next_step": "Monday: one habit.", "cited_days": ["2026-12-23"]},
    {"observation": "Wednesday held.", "next_step": "y" * 141, "cited_days": ["2026-12-23"]},
])
def test_rough_narration_rejects_consolation_labels_and_overlong_text(bad):
    llm = FakeLLMClient()
    llm.replies = [json.dumps(bad), json.dumps(bad)]
    assert asyncio.run(narrate_retro(llm, _rough_summary())) is None


def test_the_same_long_answer_is_fine_in_a_normal_week():
    s = _summary(clean=[{"date": "2026-12-23", "weekday": "Wed"}])
    s["week_mode"] = resolve_week_mode(s).as_dict()
    llm = FakeLLMClient()
    llm.replies = [json.dumps({
        "observation": "Wednesday held. " + "x" * 280,
        "next_step": "Monday: keep it.",
        "cited_days": ["2026-12-23"],
    })]
    assert asyncio.run(narrate_retro(llm, s)) is not None
    assert ROUGH_BANNED.search("you've got this")


def _seed_retro(world, user, summary):
    retro = WeeklyRetro(
        id=uuid4(), user_id=user,
        week_start=date(2026, 12, 21), week_end=date(2026, 12, 27),
        generated_at=world.now - timedelta(days=1),
        narrative="Original read.", next_step="Original step.",
        summary=summary, evidence_refs={},
        narrated=False, voice_version="v2", model=None,
    )
    asyncio.run(world.retro_repo.create(retro))
    return retro


def test_retone_rereads_the_week_and_is_a_no_op_when_nothing_changes(world, user_a):
    c = world.client_as(user_a)
    normal = _summary(
        clean=[{"date": "2026-12-23", "weekday": "Wed"}],
        chains=[CHAIN],
    )
    normal["week_mode"] = resolve_week_mode(normal).as_dict()
    _seed_retro(world, user_a, normal)
    world.llm.replies = [GOOD_ROUGH]
    r = c.post("/retros/2026-12-21/tone", json={"mode": "rough"})
    assert r.status_code == 200
    body = r.json()
    assert body["week_mode"]["mode"] == "rough" and body["week_mode"]["source"] == "user"
    assert body["narrated"] is True and body["narrative"].startswith("Wednesday held")
    assert body["summary"]["week_mode"]["mode"] == "rough"

    calls = len(world.llm.calls)
    assert c.post("/retros/2026-12-21/tone", json={"mode": "rough"}).status_code == 200
    assert len(world.llm.calls) == calls  # unchanged read: no model call

    world.llm.replies = [json.dumps({
        "observation": "Wednesday held: nothing broke.",
        "next_step": "Keep the same week going.",
        "cited_days": ["2026-12-23"],
    })]
    back = c.post("/retros/2026-12-21/tone", json={"mode": "auto"}).json()
    assert back["week_mode"] == {"mode": "normal", "reasons": [], "source": "auto"}


def test_retone_falls_back_deterministically_when_the_model_is_down(world, user_a):
    from app.services.llm import LLMUnavailableError
    c = world.client_as(user_a)
    s = _summary(
        days=BAD_DAYS, habit_pct=30.0, chains=[CHAIN],
        clean=[{"date": "2026-12-23", "weekday": "Wed"}],
    )
    s["week_mode"] = resolve_week_mode(s, "normal").as_dict()
    _seed_retro(world, user_a, s)
    world.llm.error = LLMUnavailableError("down")
    body = c.post("/retros/2026-12-21/tone", json={"mode": "rough"}).json()
    assert body["narrated"] is False and body["week_mode"]["mode"] == "rough"
    assert len(body["narrative"]) <= ROUGH_MAX_OBSERVATION and len(body["next_step"]) <= ROUGH_MAX_STEP


def test_old_retros_report_no_week_mode_and_other_users_cannot_retone(world, user_a, user_b):
    _seed_retro(world, user_a, _summary())
    assert world.client_as(user_a).get("/retros/2026-12-21").json()["week_mode"] is None
    assert world.client_as(user_b).post("/retros/2026-12-21/tone", json={"mode": "rough"}).status_code == 404
