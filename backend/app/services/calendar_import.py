"""
ICS (RFC 5545) import. PURE: text in, events out. No DB, no clock, no network, no third-party parser.

An .ics file is UNTRUSTED INPUT, so this parser is deliberately small and bounded:
  * only SUMMARY, DTSTART, DTEND, DURATION, RRULE, EXDATE, RECURRENCE-ID, STATUS, UID and CATEGORIES are read.
    Location, description, attendees, attachments and links are never looked at, so they can't be stored or leaked.
  * hard caps on VEVENT count, expanded occurrences, rule iterations and title length; nothing recurses.
  * malformed events are skipped and counted, never raised. Only "this is not a calendar at all" raises.

Recurrence: DAILY / WEEKLY (with BYDAY) / MONTHLY (a single day of month) / YEARLY, with INTERVAL, COUNT, UNTIL,
EXDATE and RECURRENCE-ID overrides, expanded in the event's own wall-clock time zone so a 10:00 class stays 10:00
across DST. Anything fancier (BYSETPOS, "second Tuesday", BYYEARDAY, ...) imports its first occurrence only and says so.

Classification is a title heuristic:
  "Mid-sem exam", "DS Quiz 2", "Viva" -> exam; "Lecture", "Lab" -> class;
  "Exam prep", "Revision session", "Mock test" -> other (it is studying, not the exam).
The person can always correct a guess.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_ICS_CHARS = 1_000_000
MAX_VEVENTS = 3000
HORIZON_DAYS = 180
MAX_STORED_PER_IMPORT = 2500
MAX_OCCURRENCES_PER_EVENT = 400
MAX_RULE_STEPS = 20000
MAX_TITLE = 120
MAX_UID = 200
KINDS = ("exam", "class", "other")


class NotCalendarError(ValueError):
    """The text is not an iCalendar file."""


@dataclass(frozen=True, slots=True)
class ParsedEvent:
    uid: str
    title: str
    starts_at: datetime  # timezone-aware
    ends_at: datetime | None
    all_day: bool
    kind: str  # exam | class | other


@dataclass(frozen=True, slots=True)
class ParseResult:
    events: tuple[ParsedEvent, ...]
    skipped: int
    warnings: tuple[str, ...]


# ------------------------------------------------------------------ classification
_EXAM = re.compile(
    r"\b(exams?|examinations?|mid[- ]?terms?|mid[- ]?sems?|end[- ]?sems?|finals|quiz(?:zes)?|viva|tests?|internals?|assessments?)\b",
    re.I,
)
_PREP = re.compile(r"\b(prep|preparation|review|revision|revise|study|studying|discussion|doubts?|solutions?|results?|answer key|mock)\b", re.I)
_CLASS = re.compile(r"\b(lectures?|lec|labs?|tutorials?|class(?:es)?|seminars?|workshops?|recitations?|sections?)\b", re.I)


def classify(title: str, categories: tuple[str, ...] = ()) -> str:
    text = f"{title} {' '.join(categories)}"
    if _EXAM.search(text):
        return "other" if _PREP.search(text) else "exam"
    if _CLASS.search(text):
        return "class"
    return "other"


# ------------------------------------------------------------------ low-level iCalendar text
_WINDOWS_TZ = {
    "India Standard Time": "Asia/Kolkata",
    "Eastern Standard Time": "America/New_York",
    "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver",
    "Pacific Standard Time": "America/Los_Angeles",
    "GMT Standard Time": "Europe/London",
    "W. Europe Standard Time": "Europe/Berlin",
    "Central Europe Standard Time": "Europe/Budapest",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "UTC": "UTC",
}
_ESC = re.compile(r"\\([nN,;\\])")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_DATE = re.compile(r"\d{8}")
_DATETIME = re.compile(r"(\d{8})T(\d{6})(Z?)")
_DURATION = re.compile(r"^([+-]?)P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")
_WD = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def unfold(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and out:
            out[-1] += raw[1:]
        else:
            out.append(raw)
    return out


def _split_unquoted(s: str, sep: str) -> list[str]:
    parts, cur, quoted = [], [], False
    for ch in s:
        if ch == '"':
            quoted = not quoted
        if ch == sep and not quoted:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def parse_line(line: str) -> tuple[str, dict[str, str], str] | None:
    quoted, split_at = False, -1
    for i, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif ch == ":" and not quoted:
            split_at = i
            break
    if split_at <= 0:
        return None
    head, value = line[:split_at], line[split_at + 1:]
    parts = _split_unquoted(head, ";")
    params: dict[str, str] = {}
    for p in parts[1:]:
        k, _, v = p.partition("=")
        params[k.strip().upper()] = v.strip().strip('"')
    return parts[0].strip().upper(), params, value


def unescape(s: str) -> str:
    return _ESC.sub(lambda m: "\n" if m.group(1) in "nN" else m.group(1), s)


def clean_title(s: str) -> str:
    text = " ".join(_CTRL.sub(" ", unescape(s)).split())
    return text[:MAX_TITLE].rstrip() or "(untitled)"


@lru_cache(maxsize=64)
def _zone(name: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(_WINDOWS_TZ.get(name, name))
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None


def _tz(tzid: str | None, default: tzinfo) -> tzinfo:
    return (_zone(tzid) if tzid else None) or default


def parse_dt(value: str, params: dict[str, str], default_tz: tzinfo) -> tuple[datetime, bool] | None:
    """-> (aware datetime, is_all_day) or None. All-day values land on local midnight in the person's zone."""
    value = value.strip()
    try:
        if params.get("VALUE", "").upper() == "DATE" or _DATE.fullmatch(value):
            return datetime.combine(date(int(value[0:4]), int(value[4:6]), int(value[6:8])), time(0), tzinfo=default_tz), True
        m = _DATETIME.fullmatch(value)
        if not m:
            return None
        naive = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None
    zone = timezone.utc if m.group(3) else _tz(params.get("TZID"), default_tz)
    return naive.replace(tzinfo=zone), False


def parse_duration(value: str) -> timedelta | None:
    m = _DURATION.match(value.strip())
    if not m:
        return None
    sign, w, d, h, mi, s = m.groups()
    delta = timedelta(weeks=int(w or 0), days=int(d or 0), hours=int(h or 0), minutes=int(mi or 0), seconds=int(s or 0))
    return -delta if sign == "-" else delta


# ------------------------------------------------------------------ recurrence
@dataclass(frozen=True, slots=True)
class Rule:
    supported: bool
    freq: str = ""
    interval: int = 1
    count: int | None = None
    until: datetime | None = None
    byday: tuple[int, ...] = ()
    bymonthday: int | None = None


def parse_rrule(value: str, tz: tzinfo) -> Rule:
    fields: dict[str, str] = {}
    for part in value.split(";"):
        k, _, v = part.partition("=")
        if k:
            fields[k.strip().upper()] = v.strip()
    if fields.get("FREQ", "").upper() not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        return Rule(False)
    if any(k in fields for k in ("BYSETPOS", "BYWEEKNO", "BYYEARDAY", "BYHOUR", "BYMINUTE", "BYSECOND", "BYMONTH")):
        return Rule(False)
    byday: list[int] = []
    for token in filter(None, fields.get("BYDAY", "").upper().split(",")):
        if token not in _WD:  # "1MO" / "-1FR" (ordinals) are not supported
            return Rule(False)
        byday.append(_WD[token])
    bymonthday: int | None = None
    if "BYMONTHDAY" in fields:
        try:
            bymonthday = int(fields["BYMONTHDAY"])
        except ValueError:
            return Rule(False)
        if not 1 <= bymonthday <= 31:
            return Rule(False)
    try:
        interval = max(1, min(int(fields.get("INTERVAL", "1")), 52))
        count = int(fields["COUNT"]) if "COUNT" in fields else None
    except ValueError:
        return Rule(False)
    if count is not None and count < 1:
        return Rule(False)
    until: datetime | None = None
    if "UNTIL" in fields:
        got = parse_dt(fields["UNTIL"], {}, tz)
        if got is None:
            return Rule(False)
        until = got[0] + timedelta(days=1) - timedelta(seconds=1) if got[1] else got[0]
    return Rule(True, fields["FREQ"].upper(), interval, count, until, tuple(byday), bymonthday)


def _dim(year: int, month: int) -> int:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return (nxt - date(year, month, 1)).days


def _generate(d0: datetime, rule: Rule) -> Iterator[datetime]:
    """Naive wall-clock candidates from d0 onward, ascending. Infinite: the caller bounds it."""
    k = 0
    if rule.freq == "DAILY":
        while True:
            yield d0 + timedelta(days=rule.interval * k)
            k += 1
    elif rule.freq == "WEEKLY":
        days = sorted(set(rule.byday)) or [d0.weekday()]
        week0 = d0 - timedelta(days=d0.weekday())
        while True:
            base = week0 + timedelta(weeks=rule.interval * k)
            for wd in days:
                cand = base + timedelta(days=wd)
                if cand >= d0:
                    yield cand
            k += 1
    elif rule.freq == "MONTHLY":
        day = rule.bymonthday or d0.day
        while True:
            total = d0.month - 1 + rule.interval * k
            year, month = d0.year + total // 12, total % 12 + 1
            if year > 9998:
                return
            if day <= _dim(year, month):
                yield d0.replace(year=year, month=month, day=day)
            k += 1
    else:  # YEARLY
        while True:
            year = d0.year + rule.interval * k
            if year > 9998:
                return
            try:
                yield d0.replace(year=year)
            except ValueError:  # Feb 29 in a non-leap year
                pass
            k += 1


def expand(
    start: datetime, rule: Rule, window_start: datetime, window_end: datetime, exdates: set[datetime],
) -> tuple[list[datetime], bool]:
    """Occurrences inside the window, in the event's own wall-clock zone. Second value: True if a cap cut it short."""
    tz = start.tzinfo
    out: list[datetime] = []
    produced = steps = 0
    for naive in _generate(start.replace(tzinfo=None), rule):
        steps += 1
        if steps > MAX_RULE_STEPS:
            return out, True
        occ = naive.replace(tzinfo=tz)
        if (rule.until is not None and occ > rule.until) or occ > window_end:
            break
        produced += 1
        if rule.count is not None and produced > rule.count:
            break
        if occ >= window_start and occ not in exdates:
            out.append(occ)
        if len(out) >= MAX_OCCURRENCES_PER_EVENT:
            return out, True
    return out, False


# ------------------------------------------------------------------ the parser
Raw = dict[str, list[tuple[dict[str, str], str]]]


def _collect(lines: list[str]) -> tuple[list[Raw], bool]:
    events: list[Raw] = []
    cur: Raw | None = None
    in_alarm = False
    for line in lines:
        parsed = parse_line(line)
        if parsed is None:
            continue
        name, params, value = parsed
        v = value.strip().upper()
        if name == "BEGIN":
            if v == "VEVENT":
                if len(events) >= MAX_VEVENTS:
                    return events, True
                cur = {}
            elif v == "VALARM":
                in_alarm = True
        elif name == "END":
            if v == "VEVENT" and cur is not None:
                events.append(cur)
                cur = None
            elif v == "VALARM":
                in_alarm = False
        elif cur is not None and not in_alarm:
            cur.setdefault(name, []).append((params, value))
    return events, False


def _first(raw: Raw, name: str) -> tuple[dict[str, str], str] | None:
    got = raw.get(name)
    return got[0] if got else None


def _categories(raw: Raw) -> tuple[str, ...]:
    out: list[str] = []
    for _, value in raw.get("CATEGORIES", []):
        out.extend(clean_title(v) for v in value.split(",") if v.strip())
    return tuple(out[:10])


def _exdates(raw: Raw, tz: tzinfo) -> set[datetime]:
    out: set[datetime] = set()
    for params, value in raw.get("EXDATE", []):
        for piece in value.split(","):
            got = parse_dt(piece, params, tz)
            if got is not None:
                out.add(got[0])
    return out


def parse_ics(text: str, default_tz: tzinfo, window_start: datetime) -> ParseResult:
    """
    Events starting between `window_start` and HORIZON_DAYS later. `default_tz` places floating times and all-day dates
    (the person's own zone). Never raises on malformed events; raises NotCalendarError when this is not iCalendar at all.
    """
    if "BEGIN:VCALENDAR" not in text.upper():
        raise NotCalendarError("That doesn't look like a calendar (.ics) file.")
    window_end = window_start + timedelta(days=HORIZON_DAYS)
    raws, truncated = _collect(unfold(text))
    warnings: set[str] = set()
    if truncated:
        warnings.add(f"Only the first {MAX_VEVENTS} events in the file were read.")

    # Pass 1: instances the file overrides or cancels (RECURRENCE-ID), so the master series skips them.
    overridden: dict[str, set[datetime]] = {}
    for raw in raws:
        uid, rid = _first(raw, "UID"), _first(raw, "RECURRENCE-ID")
        if uid and rid:
            got = parse_dt(rid[1], rid[0], default_tz)
            if got is not None:
                overridden.setdefault(uid[1].strip()[:MAX_UID], set()).add(got[0])

    found: dict[tuple[str, datetime], ParsedEvent] = {}
    skipped = 0
    for raw in raws:
        status = _first(raw, "STATUS")
        start_prop = _first(raw, "DTSTART")
        if (status and status[1].strip().upper() == "CANCELLED") or start_prop is None:
            skipped += 1
            continue
        got = parse_dt(start_prop[1], start_prop[0], default_tz)
        if got is None:
            skipped += 1
            continue
        start, all_day = got
        summary = _first(raw, "SUMMARY")
        title = clean_title(summary[1]) if summary else "(untitled)"
        uid_prop = _first(raw, "UID")
        uid = (uid_prop[1].strip() if uid_prop and uid_prop[1].strip() else "")[:MAX_UID] or (
            "anon-" + hashlib.sha1(f"{title}|{start.isoformat()}".encode()).hexdigest()[:16]
        )
        duration: timedelta | None = None
        end_prop, dur_prop = _first(raw, "DTEND"), _first(raw, "DURATION")
        if end_prop is not None:
            end = parse_dt(end_prop[1], end_prop[0], default_tz)
            if end is not None and end[0] > start:
                duration = end[0] - start
        elif dur_prop is not None:
            d = parse_duration(dur_prop[1])
            duration = d if d is not None and d > timedelta(0) else None
        if duration is None and all_day:
            duration = timedelta(days=1)
        kind = classify(title, _categories(raw))
        rrule, rid = _first(raw, "RRULE"), _first(raw, "RECURRENCE-ID")
        occurrences: list[datetime]
        if rrule is not None and rid is None:
            rule = parse_rrule(rrule[1], start.tzinfo or default_tz)
            if rule.supported:
                exdates = _exdates(raw, start.tzinfo or default_tz) | overridden.get(uid, set())
                occurrences, cut = expand(start, rule, window_start, window_end, exdates)
                if cut:
                    warnings.add("A repeating event was cut short because it repeats very often.")
            else:
                warnings.add("Some repeating events use rules this import can't expand; only their first date was kept.")
                occurrences = [start] if window_start <= start <= window_end else []
        else:
            occurrences = [start] if window_start <= start <= window_end else []

        for occ in occurrences:
            found.setdefault((uid, occ), ParsedEvent(uid, title, occ, occ + duration if duration else None, all_day, kind))

    events = sorted(found.values(), key=lambda e: (e.starts_at, e.uid))
    if len(events) > MAX_STORED_PER_IMPORT:
        events = events[:MAX_STORED_PER_IMPORT]
        warnings.add(f"Only the first {MAX_STORED_PER_IMPORT} events in the next {HORIZON_DAYS} days were kept.")
    return ParseResult(tuple(events), skipped, tuple(sorted(warnings)))
