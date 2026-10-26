"""Idempotent urge replays, usage report shaping, Sentry scrubbing, /ready probes. (Hinglish coverage: test_safety_hinglish.py)"""
from __future__ import annotations

from datetime import date

import pytest

from app.domain import UrgeOutcome
from app.jobs.llm_usage_report import build_report, render_text
from app.observability import scrub_event
from app.services.urges_service import UrgesService


@pytest.mark.asyncio
async def test_urge_replay_with_same_client_id_is_stored_once(world, user_a):
    urges = UrgesService(world.urge_repo, world.encryptor, world.profile_repo, clock=world._clock)
    cid = __import__("uuid").uuid4()
    first = await urges.capture(user_a, UrgeOutcome.RESISTED, None, 5, "bored", None, None, cid)
    again = await urges.capture(user_a, UrgeOutcome.RESISTED, None, 5, "bored", None, None, cid)
    assert first.log.id == again.log.id == cid
    assert len(world.urge_repo._logs) == 1


@pytest.mark.asyncio
async def test_urge_without_client_id_still_gets_a_server_id(world, user_a):
    urges = UrgesService(world.urge_repo, world.encryptor, world.profile_repo, clock=world._clock)
    a = await urges.capture(user_a, UrgeOutcome.RELAPSED)
    b = await urges.capture(user_a, UrgeOutcome.RELAPSED)
    assert a.log.id != b.log.id


def test_usage_report_groups_by_day_and_feature():
    d1, d2 = date(2026, 10, 25), date(2026, 10, 26)
    report = build_report(
        [(d1, "chat", 10, 4000), (d1, "media", 2, 0), (d2, "chat", 3, 900)],
        [(d1, 2, 9, 0), (d2, 1, 3, 0)],
        cap=80,
    )
    assert [r["date"] for r in report] == ["2026-10-26", "2026-10-25"]
    assert report[1]["calls"] == 12 and report[1]["tokens"] == 4000 and report[1]["users"] == 2
    assert report[1]["by_feature"]["media"] == {"calls": 2, "tokens": 0}
    assert "2026-10-26" in render_text(report, 80)
    assert render_text([], 80).startswith("No LLM usage")


def test_sentry_scrub_removes_bodies_headers_and_ingest_tokens():
    event = {
        "request": {
            "url": "https://api.example.com/ingest/u/SECRET123/screen", "data": {"note": "private"},
            "headers": {"Authorization": "Bearer x"}, "cookies": {"a": "b"}, "query_string": "a=1",
        },
        "user": {"id": "u"}, "breadcrumbs": {"values": [1]}, "transaction": "/ingest/u/SECRET123/screen",
    }
    out = scrub_event(event)
    assert out["request"] == {"url": "https://api.example.com/ingest/u/***/screen"}
    assert "user" not in out and "breadcrumbs" not in out
    assert out["transaction"] == "/ingest/u/***/screen"


@pytest.mark.asyncio
async def test_ready_and_health_answer_head_and_a_hung_db_reads_as_down(monkeypatch):
    import asyncio

    import httpx

    from app import main

    async def _hang():
        await asyncio.sleep(60)

    monkeypatch.setattr(main, "_READY_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(main, "ping_database", _hang)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t") as client:
        assert (await client.head("/health")).status_code == 200
        assert (await client.get("/ready")).status_code == 503
        assert (await client.head("/ready")).status_code == 503
