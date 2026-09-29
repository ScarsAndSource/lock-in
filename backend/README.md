# Lock'in backend — slice 1 (habit domain + unified daily check-in)

## What's in this slice
- Habit domain: create/list habits, log/correct a habit's status for any date.
- Unified daily check-in: opt-out defaults ("same as usual") computed from
  same-weekday history, confirm flow that persists real logs, encrypted
  journal text.
- RLS on every table, application-layer ownership checks as a second line
  of defense on top of it, field-level encryption for journal text.

## What's deliberately NOT in this slice
Sleep, screen time, study, urge/relapse, implementation intentions, goals,
pattern insights (Groq), weekly retrospectives — all later slices, per
SPEC.md section 12's build order. Nothing here is a stub pretending to be
one of those; they simply don't exist yet.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then fill in your actual Supabase values
```

Run the migration against your Supabase project's SQL editor (or `psql`):
`migrations/001_init_habit_and_checkin.sql`.

```bash
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for interactive API docs.

## Running tests

```bash
python -m pytest -v
```

33 tests, all passing as of this slice: the defaults engine's weekday/tie/
lookback-window logic, the encryption module (round-trip, tampering,
wrong-key), and the full HTTP flow (auth, cross-user access control,
encryption-at-rest, correcting a past default) via an in-memory fake
database.

## What was NOT verified, and why — read this before deploying

I'm stating this plainly because "no mistakes" has to include not
overstating what's actually been checked:

- **The SQL migration has not been run against a real Postgres/Supabase
  instance.** This sandbox has no database to run it against, and I'm not
  going to ask you for real Supabase credentials to test with. The SQL was
  written and reviewed carefully (correct RLS policy syntax, correct FK
  references to `auth.users`, `gen_random_uuid()` requires the `pgcrypto`
  extension which the migration enables) but "carefully reviewed" is not
  the same claim as "executed successfully." **Run it in a scratch Supabase
  project first, not your real one, before trusting it.**
- **The Supabase JWT verification assumes HS256 shared-secret signing.**
  Flagged in `.env.example` and `app/config.py` — verify which scheme your
  project actually uses before relying on auth working at all.
- **No rate limiting anywhere yet.** Not needed for this slice (no Groq
  calls, no expensive endpoints), but it's a real gap once the insight
  feed and chat land in a later slice, per SPEC.md's own requirement.
- **Load-bearing assumption on the defaults algorithm itself**: "same
  weekday, last 4 occurrences, majority wins" is a reasonable v1 heuristic,
  not something SPEC.md pinned down or something user-tested. It's fully
  unit tested for internal consistency (it does what it's designed to do),
  not validated against what actually feels right to a real user yet — that
  can only come from you and your friends actually using it.
