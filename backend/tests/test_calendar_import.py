"""Agent B: ICS parsing, classification, recurrence, and exam nudges. Pure: no DB, no network."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.services.calendar_import import (
    HORIZON_DAYS, MAX_OCCURRENCES_PER_EVENT, NotCalendarError, classify, parse_ics, parse_line, unfold,
)
from app.services.exam_awareness import ExamEvent, exam_nudge

IST = ZoneInfo("Asia/Kolkata")
START = datetime(2026, 10, 22, 0, 0, tzinfo=IST)  # "today" local midnight


def ics(*events: str) -> str:
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "".join(f"BEGIN:VEVENT\r\n{e}\r\nEND:VEVENT\r\n" for e in events) + "END:VCALENDAR\r\n"


def parse(*events: str, start: datetime = START):
    return parse_ics(ics(*events), IST, start)


# ------------------------------------------------------------------ text layer
def test_unfold_and_parse_line_with_params_and_quotes():
    assert unfold("SUMMARY:Data Struc\r\n tures Exam\r\nX:1") == ["SUMMARY:Data Structures Exam", "X:1"]
    assert parse_line('DTSTART;TZID="Asia/Kolkata":20261105T100000') == (
        "DTSTART", {"TZID": "Asia/Kolkata"}, "20261105T100000",
    )
    assert parse_line("garbage without colon") is None


def test_not_a_calendar_raises_and_garbage_events_are_skipped():
    with pytest.raises(NotCalendarError):
        parse_ics("hello world", IST, START)
    res = parse("SUMMARY:No start", "DTSTART:notadate\r\nSUMMARY:Bad", "DTSTART:20261105T100000\r\nSUMMARY:Fine\r\nUID:a")
    assert [e.title for e in res.events] == ["Fine"] and res.skipped == 2


# ------------------------------------------------------------------ times
def test_timezones_utc_floating_all_day_and_unknown_tzid():
    res = parse(
        "UID:u1\r\nSUMMARY:UTC\r\nDTSTART:20261105T043000Z",
        "UID:u2\r\nSUMMARY:Tz\r\nDTSTART;TZID=America/New_York:20261105T090000",
        "UID:u3\r\nSUMMARY:Floating\r\nDTSTART:20261105T100000",
        "UID:u4\r\nSUMMARY:Windows\r\nDTSTART;TZID=India Standard Time:20261105T110000",
        "UID:u5\r\nSUMMARY:Bogus zone\r\nDTSTART;TZID=Not/AZone:20261105T120000",
        "UID:u6\r\nSUMMARY:Holiday\r\nDTSTART;VALUE=DATE:20261106\r\nDTEND;VALUE=DATE:20261107",
    )
    by = {e.uid: e for e in res.events}
    assert by["u1"].starts_at == datetime(2026, 11, 5, 4, 30, tzinfo=timezone.utc)
    assert by["u2"].starts_at == datetime(2026, 11, 5, 14, 0, tzinfo=timezone.utc)
    assert by["u3"].starts_at == datetime(2026, 11, 5, 10, 0, tzinfo=IST)
    assert by["u4"].starts_at == datetime(2026, 11, 5, 11, 0, tzinfo=IST)
    assert by["u5"].starts_at == datetime(2026, 11, 5, 12, 0, tzinfo=IST)  # unknown zone falls back to the person's
    assert by["u6"].all_day and by["u6"].starts_at == datetime(2026, 11, 6, 0, 0, tzinfo=IST)
    assert by["u6"].ends_at == datetime(2026, 11, 7, 0, 0, tzinfo=IST)


def test_end_from_dtend_or_duration_and_window_filter():
    res = parse(
        "UID:a\r\nSUMMARY:One\r\nDTSTART:20261105T100000\r\nDTEND:20261105T123000",
        "UID:b\r\nSUMMARY:Two\r\nDTSTART:20261105T140000\r\nDURATION:PT1H30M",
        "UID:old\r\nSUMMARY:Past\r\nDTSTART:20260101T100000",
        "UID:far\r\nSUMMARY:Far\r\nDTSTART:20300101T100000",
    )
    by = {e.uid: e for e in res.events}
    assert set(by) == {"a", "b"}
    assert by["a"].ends_at - by["a"].starts_at == timedelta(hours=2, minutes=30)
    assert by["b"].ends_at - by["b"].starts_at == timedelta(hours=1, minutes=30)


def test_text_is_unescaped_cleaned_and_capped_and_alarms_ignored():
    res = parse(
        "UID:t\r\nSUMMARY:Maths\\, Paper\\nII " + "x" * 300 + "\r\nDTSTART:20261105T100000\r\n"
        "BEGIN:VALARM\r\nSUMMARY:Alarm title\r\nTRIGGER:-PT15M\r\nEND:VALARM",
    )
    title = res.events[0].title
    assert title.startswith("Maths, Paper II xxx") and len(title) <= 120 and "Alarm" not in title


# ------------------------------------------------------------------ recurrence
def test_weekly_byday_count_exdate_and_override():
    res = parse(
        "UID:cls\r\nSUMMARY:DS Lecture\r\nDTSTART;TZID=Asia/Kolkata:20261026T090000\r\n"
        "RRULE:FREQ=WEEKLY;BYDAY=MO,WE;COUNT=6\r\n"
        "EXDATE;TZID=Asia/Kolkata:20261028T090000",
        "UID:cls\r\nSUMMARY:DS Lecture (moved)\r\nRECURRENCE-ID;TZID=Asia/Kolkata:20261102T090000\r\n"
        "DTSTART;TZID=Asia/Kolkata:20261102T150000",
    )
    starts = [(e.title, e.starts_at.astimezone(IST).strftime("%m-%d %H:%M")) for e in res.events]
    # COUNT=6 counts Mon 26, Wed 28 (excluded), Mon 2 (overridden), Wed 4, Mon 9, Wed 11
    assert starts == [
        ("DS Lecture", "10-26 09:00"),
        ("DS Lecture (moved)", "11-02 15:00"),
        ("DS Lecture", "11-04 09:00"),
        ("DS Lecture", "11-09 09:00"),
        ("DS Lecture", "11-11 09:00"),
    ]


def test_daily_until_monthly_yearly_and_unsupported_rule():
    res = parse(
        "UID:d\r\nSUMMARY:Standup\r\nDTSTART:20261023T080000\r\nRRULE:FREQ=DAILY;INTERVAL=2;UNTIL=20261029",
        "UID:m\r\nSUMMARY:Rent\r\nDTSTART:20261031T090000\r\nRRULE:FREQ=MONTHLY;COUNT=3",
        "UID:y\r\nSUMMARY:Birthday\r\nDTSTART:20261201T090000\r\nRRULE:FREQ=YEARLY",
        "UID:x\r\nSUMMARY:Odd\r\nDTSTART:20261104T090000\r\nRRULE:FREQ=MONTHLY;BYDAY=2TU",
    )
    days = lambda uid: [e.starts_at.astimezone(IST).strftime("%m-%d") for e in res.events if e.uid == uid]  # noqa: E731
    assert days("d") == ["10-23", "10-25", "10-27", "10-29"]
    assert days("m") == ["10-31", "12-31", "01-31"]  # Nov has no 31st: skipped and NOT counted (RFC 5545)
    assert days("y") == ["12-01"]
    assert days("x") == ["11-04"] and any("can't expand" in w for w in res.warnings)


def test_runaway_rules_are_capped():
    res = parse("UID:r\r\nSUMMARY:Spam\r\nDTSTART:20200101T080000\r\nRRULE:FREQ=DAILY", start=START)
    count = sum(1 for e in res.events if e.uid == "r")
    assert 0 < count <= HORIZON_DAYS + 1 and count <= MAX_OCCURRENCES_PER_EVENT


def test_cancelled_events_and_dedupe():
    res = parse(
        "UID:c\r\nSUMMARY:Gone\r\nSTATUS:CANCELLED\r\nDTSTART:20261105T100000",
        "UID:k\r\nSUMMARY:Same\r\nDTSTART:20261105T100000",
        "UID:k\r\nSUMMARY:Same\r\nDTSTART:20261105T100000",
    )
    assert [e.uid for e in res.events] == ["k"] and res.skipped == 1


# ------------------------------------------------------------------ classification
@pytest.mark.parametrize("title,kind", [
    ("Data Structures Mid-Sem Exam", "exam"),
    ("DS Quiz 2", "exam"),
    ("Viva voce", "exam"),
    ("ENDSEM - Maths", "exam"),
    ("Final Exam: Physics", "exam"),
    ("Lab Exam (OS)", "exam"),
    ("Exam prep session", "other"),
    ("Revision for midterm", "other"),
    ("Mock test", "other"),
    ("DS Lecture", "class"),
    ("OS Lab", "class"),
    ("Tutorial 4", "class"),
    ("Dentist", "other"),
    ("Contest night", "other"),
])
def test_classify(title, kind):
    assert classify(title) == kind


def test_category_can_mark_an_exam():
    assert classify("Paper 2", ("Exam",)) == "exam"


# ------------------------------------------------------------------ exam nudges
TODAY = date(2026, 10, 22)


def exam(eid: str, days: int, minute: int | None = 14 * 60, title: str = "DS Exam") -> ExamEvent:
    day = TODAY + timedelta(days=days)
    return ExamEvent(eid, title, datetime(day.year, day.month, day.day, tzinfo=IST), minute is None, day, minute)


def test_exam_nudge_phases_scores_and_tone():
    today = exam_nudge([exam("a", 0)], TODAY, 8 * 60, "direct")
    assert today and (today.score, today.eyebrow) == (95, "Exam today") and "Starts 14:00" in today.detail
    assert exam_nudge([exam("a", 1)], TODAY, 600, "direct").score == 90
    assert exam_nudge([exam("a", 3)], TODAY, 600, "coach").score == 62
    far = exam_nudge([exam("a", 6)], TODAY, 600, "direct")
    assert far and far.score == 40 and far.title == "DS Exam in 6 days"
    assert exam_nudge([exam("a", 8)], TODAY, 600, "direct") is None
    assert "breathe" in exam_nudge([exam("a", 0)], TODAY, 600, "coach").detail


def test_exam_nudge_goes_quiet_once_started_and_collapses_same_day():
    assert exam_nudge([exam("a", 0)], TODAY, 14 * 60, "direct") is None
    assert exam_nudge([exam("a", 0, None)], TODAY, 23 * 60, "direct") is not None  # all-day: stays all day
    two = exam_nudge([exam("a", 1, 9 * 60), exam("b", 1, 14 * 60)], TODAY, 600, "direct")
    assert two and two.event_id == "a" and "+1 more that day" in two.detail
    assert exam_nudge([exam("a", 1)], TODAY, 600, "direct").key == "exam:a:1"  # key changes daily: "not now" is per day


def test_calendar_and_inference_routers_build():
    from app.routers import calendar, inference
    paths = {(m, r.path) for r in calendar.router.routes for m in getattr(r, "methods", ())}
    assert {
        ("POST", "/calendar/import"),
        ("GET", "/calendar/exams"),
        ("PATCH", "/calendar/events/{event_id}"),
        ("DELETE", "/calendar/sources/{source}"),
        ("GET", "/calendar/sources"),
        ("GET", "/calendar/events"),
    } <= paths
    assert ("GET", "/companion/inference") in {(m, r.path) for r in inference.router.routes for m in r.methods}
