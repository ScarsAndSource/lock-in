"""Launch-day fixes: distance vs. crisis slang, push failures, CORS on early/error responses, retro job pauses."""
from __future__ import annotations

from app.domain import PushSubscription
from app.safety import is_crisis
from app.services.push import PushOutcome

from tests.test_slice11_tasks_nudges import FakeSender, make_dispatch, run, task, NOW, UID
from datetime import timedelta


# ------------------------------------------------------------ "kms" the distance vs. "kms" the slang
def test_distances_are_not_a_crisis_but_the_slang_still_is():
    for text in ("ran 5 kms today", "Cycle 10 kms", "walk 3 km", "2.5kms before class", "did 12 KMS"):
        assert not is_crisis(text), text
    for text in ("kms", "i want to kms", "honestly just kms tonight"):
        assert is_crisis(text), text


# ------------------------------------------------------------ push: our misconfiguration never deletes subscriptions
def test_error_outcome_never_counts_against_or_drops_a_subscription():
    t = task(importance=3, due_at=NOW - timedelta(minutes=10))
    svc, trepo, nrepo, sender = make_dispatch(tasks=[t], sender=FakeSender(PushOutcome.ERROR))
    for _ in range(8):  # well past MAX_FAILS_BEFORE_DROP
        trepo.rows[t.id].last_nudged_at = None
        assert run(svc.dispatch(UID)).sent == 0
    assert len(nrepo.subs) == 1 and nrepo.subs[0].fail_count == 0
    assert trepo.rows[t.id].nudge_count == 0  # the task was not advanced either


# ------------------------------------------------------------ CORS on responses produced outside the router
def test_413_and_500_responses_carry_cors_headers(world, user_a):
    from fastapi.testclient import TestClient
    from app.deps import get_habits_service
    from app.main import app

    origin = "http://localhost:5173"
    client = world.client_as(user_a)
    r = client.post("/habits", content=b"{}", headers={"origin": origin, "content-length": str(10 * 1024 * 1024),
                                                      "content-type": "application/json"})
    assert r.status_code == 413
    assert r.headers.get("access-control-allow-origin") == origin

    def boom():
        raise RuntimeError("kaboom")

    app.dependency_overrides[get_habits_service] = boom
    safe = TestClient(app, raise_server_exceptions=False)
    r = safe.get("/habits", headers={"origin": origin})
    assert r.status_code == 500
    assert r.headers.get("access-control-allow-origin") == origin
    assert safe.get("/habits", headers={"origin": "https://evil.example"}).headers.get("access-control-allow-origin") is None
