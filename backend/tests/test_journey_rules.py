"""No-database tests for the journey layer's pure rules (seasons, unlock, exam radar, snapshot, graduation)."""
from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.exceptions import ValidationError
from app.services import graduation_rules as gr
from app.services import recall_plan as rp
from app.services import season as sn
from app.services import snapshot_math as sm
from app.services.unlock import stage_for

D = date(2026, 11, 2)


def d(n: int) -> date:
    return D + timedelta(days=n)


# ---- seasons
def test_phase_boundaries():
    assert sn.phase(D, D) == sn.Phase("focus", 1, 42)
    assert sn.phase(D, d(41)) == sn.Phase("focus", 6, 1)
    assert sn.phase(D, d(42)) == sn.Phase("rest", 7, 7)
    assert sn.phase(D, d(49)) == sn.Phase("ended", 7, 0)


def test_rest_week_is_the_seventh_week():
    days = sn.rest_days(D)
    assert len(days) == 7 and d(42) in days and d(48) in days and d(41) not in days and d(49) not in days


def test_slots_grandfather_existing_habits():
    assert sn.slots_for(0) == 3 and sn.slots_for(3) == 3 and sn.slots_for(5) == 5 and sn.slots_for(80) == 50


def test_free_slots_ignore_archived_focus_habits():
    a, b, c = uuid4(), uuid4(), uuid4()
    assert sn.free_slots(3, [a, b], [a, b, c]) == 1
    assert sn.free_slots(3, [a, b], [a, c]) == 2  # b was archived or graduated, its slot is free again


def test_validate_focus():
    a, b, c, e = uuid4(), uuid4(), uuid4(), uuid4()
    assert sn.validate_focus([a, a], 3, [a, b]) == [a]
    with pytest.raises(ValidationError):
        sn.validate_focus([a, b, c, e], 3, [a, b, c, e])
    with pytest.raises(ValidationError):
        sn.validate_focus([e], 3, [a])


# ---- slow unlock
def test_existing_accounts_keep_everything():
    assert stage_for(date(2026, 10, 1), date(2026, 10, 2), 0) == 4


def test_new_accounts_climb_the_ladder():
    assert stage_for(D, D, 0) == 0
    assert stage_for(D, d(7), 3) == 1
    assert stage_for(D, d(7), 2) == 0
    assert stage_for(D, d(14), 7) == 2
    assert stage_for(D, d(40), 5) == 1
    assert stage_for(D, d(35), 20) == 4


# ---- exam radar
def test_plan_without_constraints_is_1_3_7_14():
    assert rp.build_plan(D, None, frozenset(), {}) == [(1, d(1)), (3, d(3)), (7, d(7)), (14, d(14))]


def test_plan_never_lands_on_or_after_the_exam():
    plan = rp.build_plan(D, d(4), frozenset(), {})
    assert plan == [(1, d(1)), (3, d(3))] or all(due < d(4) for _, due in plan)
    assert all(due < d(4) for _, due in plan)


def test_exam_tomorrow_plans_nothing():
    assert rp.build_plan(D, d(1), frozenset(), {}) == []


def test_plan_skips_blocked_days_and_full_days():
    assert rp.build_plan(D, None, frozenset({d(1)}), {})[0] == (1, d(2))
    assert rp.build_plan(D, None, frozenset(), {d(1): rp.MAX_PER_DAY})[0] == (1, d(2))


def test_reflow_moves_overdue_forward_and_leaves_the_rest():
    a, b = uuid4(), uuid4()
    moves = rp.reflow([(a, d(8), None), (b, d(12), None)], d(10), frozenset(), {})
    assert moves == {a: d(10)}


def test_reflow_moves_a_review_off_a_blocked_day():
    a = uuid4()
    assert rp.reflow([(a, d(12), None)], d(10), frozenset({d(12)}), {}) == {a: d(13)}


def test_reflow_drops_a_review_that_no_longer_fits_before_the_exam():
    a = uuid4()
    assert rp.reflow([(a, d(8), d(10))], d(10), frozenset(), {}) == {a: None}


def test_topics_are_cleaned_and_deduped():
    assert rp.parse_topics("AVL trees, avl trees;\n- Graphs\n\n") == ["AVL trees", "Graphs"]
    with pytest.raises(ValidationError):
        rp.parse_topics(" , ;")


# ---- snapshot
def test_support_routing():
    assert sm.needs_support(3, None) and not sm.needs_support(4, None)
    assert sm.needs_support(4, 8) and not sm.needs_support(7, 8)


def test_deltas_need_two_snapshots_and_never_guess():
    base = sm.Snap(date(2026, 11, 1), {m: 5 for m in sm.METRICS})
    assert all(w["metrics"] is None for w in sm.deltas([base]))
    later = sm.Snap(date(2026, 12, 1), {**{m: 5 for m in sm.METRICS}, "wellbeing": 7})
    out = sm.deltas([base, later])
    assert out[0]["metrics"]["wellbeing"] == 2 and out[0]["metrics"]["sleep"] == 0
    assert out[1]["metrics"] is None and out[2]["metrics"] is None


def test_snapshot_due_every_30_days():
    assert sm.is_due(None, D) and not sm.is_due(D, d(29)) and sm.is_due(D, d(30))


# ---- graduation
def test_offer_needs_consistency_history_age_and_feeling_automatic():
    assert gr.offer(85, 25, 60, None)
    assert not gr.offer(85, 25, 60, 5)
    assert not gr.offer(79, 25, 60, None)
    assert not gr.offer(90, 10, 60, None)
    assert not gr.offer(90, 25, 30, None)


def test_shelf_checkins_at_30_and_90_days():
    c30, c90 = gr.check_dates(date(2026, 11, 1))
    assert (c30, c90) == (date(2026, 12, 1), date(2027, 1, 30))
    assert gr.due_check(c30, c90, None, None, date(2026, 11, 15)) is None
    assert gr.due_check(c30, c90, None, None, c30) == 30
    assert gr.due_check(c30, c90, "holding", None, c30) is None
    assert gr.due_check(c30, c90, None, None, c90) == 90
    assert gr.due_check(c30, c90, "holding", "holding", c90) is None