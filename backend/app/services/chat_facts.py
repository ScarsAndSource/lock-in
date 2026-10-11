"""
The chat evidence pack: everything the model is allowed to know, as compact JSON.
- structured states/numbers only; NO free text (journal, urge notes/triggers/coping, check-in notes)
- only labels the user typed (habit/subject/goal names), sanitized + length-capped
- auto-filled (defaulted) values are left out: guesses are not evidence
- a domain missing from a day row means "not logged", never "failed"
"""
from __future__ import annotations

from datetime import date

from app.services.narration import sanitize_user_text

_WD = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_NONE = "none"
WINDOW_DAYS = 14
HABIT_WINDOW_DAYS = 30


def _label(text: str, n: int) -> str:
    return sanitize_user_text(text, n, single_line=True)


def _day_row(d) -> dict | None:
    row: dict = {"date": d.day.isoformat(), "weekday": _WD[d.day.weekday()]}
    if not getattr(d, "habits_defaulted", False) and d.habits != _NONE:
        row["habits"] = d.habits
        if d.habit_ratio is not None:
            row["habit_pct"] = round(d.habit_ratio * 100)
    if not d.sleep_defaulted and d.sleep != _NONE:
        row["sleep"] = d.sleep
        if d.sleep_minutes is not None:
            row["sleep_hours"] = round(d.sleep_minutes / 60, 1)
    if not d.screen_time_defaulted and d.screen_time != _NONE:
        row["screen"] = d.screen_time
        if d.screen_minutes is not None:
            row["screen_minutes"] = d.screen_minutes
    for key in ("study", "urges"):
        state = getattr(d, key, _NONE)
        if state != _NONE:
            row[key] = state
    return row if len(row) > 2 else None


def build_chat_facts(
    *,
    end: date,
    days,
    habit_items,
    patterns,
    study,
    by_subject,
    urge,
    goals,
    mission: dict | None,
) -> dict:
    rows = [r for r in (_day_row(d) for d in days) if r]
    facts: dict = {
        "today": {"date": end.isoformat(), "weekday": _WD[end.weekday()]},
        "window_days": WINDOW_DAYS,
        "logged_days": len(rows),
        "days": rows,
        "habit_window_days": HABIT_WINDOW_DAYS,
        "habits": [
            {
                "name": _label(h.habit_name, 40),
                "consistency_pct": h.consistency_pct,
                "logged_days": h.logged_days,
                "current_run": h.current_run,
            }
            for h in habit_items[:12]
        ],
        "patterns": [
            {
                "key": p.key,
                "statement": p.statement,
                "trigger_days": p.trigger_days,
                "hits": p.hits,
                "rate_after_trigger": round(p.rate_after_trigger, 3),
                "baseline_rate": round(p.baseline_rate, 3),
                "evidence": [d.isoformat() for d in p.evidence_dates[:6]],
            }
            for p in patterns[:5]
        ],
        "study": (
            {
                "days": WINDOW_DAYS,
                "total_minutes": study.total_actual,
                "planned_minutes": study.total_planned,
                "follow_through_pct": study.follow_through_pct,
                "days_studied": study.days_studied,
                "by_subject": [{"name": _label(name, 40), "minutes": m} for _, name, m in by_subject[:8]],
            }
            if (study.total_actual or study.total_planned)
            else None
        ),
        "urges": (
            {
                "days": WINDOW_DAYS,
                "total": urge.total,
                "resisted": urge.resisted,
                "relapsed": urge.relapsed,
                "resist_rate_pct": urge.resist_rate_pct,
                "relapse_free_days_pct": urge.relapse_free_days_pct,
            }
            if urge.total
            else None
        ),
        "goals": [
            {
                "domain": p.goal.domain,
                "definition": _label(p.goal.definition, 120),
                "on_track": p.on_track,
                "current": p.current,
                "target": p.target_value,
                "unit": p.unit,
                "detail": p.detail,
            }
            for p in goals[:8]
        ],
        "mission": mission,
    }
    return {k: v for k, v in facts.items() if v not in (None, [], {})}


def fact_days(facts: dict) -> set[str]:
    """Every ISO date the model is allowed to cite."""
    days = {r["date"] for r in facts.get("days", [])}
    for p in facts.get("patterns", []):
        days.update(p.get("evidence", []))
    return days


def fallback_digest(facts: dict) -> str:
    """Deterministic reply when the model can't be trusted/reached: plain facts, no advice."""
    parts: list[str] = []
    habits = [h for h in facts.get("habits", []) if h.get("consistency_pct") is not None]
    if habits:
        low = min(habits, key=lambda h: h["consistency_pct"])
        parts.append(
            f"Over the last {facts['habit_window_days']} days your lowest-consistency habit is "
            f"{low['name']} at {low['consistency_pct']}%."
        )
    patterns = facts.get("patterns", [])
    if patterns:
        parts.append(patterns[0]["statement"])
    parts.append(f"{facts['logged_days']} of the last {facts['window_days']} days have logged data.")
    parts.append("I couldn't tie a full answer to your logs just now. Ask again in a moment.")
    return " ".join(parts)
