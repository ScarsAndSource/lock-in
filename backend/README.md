# Lock'in backend

## Slice status

| Slice | What | Status |
|-------|------|--------|
| 1 | Habit domain, unified daily check-in (defaults engine, encrypted journal) | ✅ Done |
| 3 | Sleep + screen-time logging, basic stats | ✅ Done |
| 3b | Missions (goal-scoped sprints) | ✅ Done |
| 3c | Schedule service, consistency scoring, pattern detection, profile, account export/delete, rate limiting | ✅ Done |
| 8 | Weekly retrospective — chain tracing, LLM narration, feedback loop, daily cron job | ✅ Done |
| 4 | Study sessions | 🔜 Next |
| 5 | Urge / relapse logging | 🔜 Next |
| 6 | If-then plans / implementation intentions | 🔜 Next |
| 7 | Groq insight layer (full wiring) | 🔜 Next |

## Endpoints (current)

```
POST   /habits                       create habit
GET    /habits                       list habits (?include_archived=bool)
PATCH  /habits/{id}                  update habit (rename / archive / unarchive)
POST   /habits/{id}/logs             log habit status for a date (upsert)

GET    /checkins/{date}/defaults     compute opt-out defaults for date
POST   /checkins/{date}/confirm      confirm check-in (habits + sleep + screen + journal)
GET    /checkins/{date}/journal      get decrypted journal for date

POST   /sleep/logs                   create/upsert sleep log
GET    /sleep/logs/{date}            get sleep log for a date
GET    /sleep/logs                   list sleep logs (?start_date=&end_date=)

POST   /screen-time/logs             create/upsert screen-time log
GET    /screen-time/logs/{date}      get screen-time log for a date
GET    /screen-time/logs             list screen-time logs (?start_date=&end_date=)

GET    /stats/consistency            rolling consistency score (?end_date=&window_days=)
GET    /stats/chain                  multi-domain chain strip (?end_date=&days=)
GET    /stats/patterns               detected cross-domain patterns (?end_date=&days=)

POST   /missions                     create a mission
GET    /missions                     list missions
GET    /missions/active              active mission progress and checkpoint detail
POST   /missions/{id}/end            end mission (completed=true|false)

GET    /me                           get profile (timezone, tone_preference, today)
PATCH  /me                           update timezone
GET    /me/export                    export all user data as JSON (journals decrypted)
DELETE /me                           irreversibly delete account and all data

GET    /retros                       list past retros (up to 52)
GET    /retros/latest                latest retro with pending insight ratings
GET    /retros/{week_start}          get retro for a specific Monday
POST   /retros/generate              generate (or retrieve) this week's retro
POST   /retros/{week_start}/complete mark retro done → triggers insight refresh
```

## Slice 8 — weekly retro architecture

### The chain tracer

Every retro starts with pure Python, not the model. `retro_engine.py` walks the
week and classifies each day's habits, sleep, and screen time as `good / ok / bad / none`.
A **slip** is any day where habits, study, or urges went bad. For each slip it looks
at four upstream signals:

- same-day sleep (bad sleep → habits slip is a classic same-day link)
- same-day screen time
- previous day's screen time (a late screen night causes the next morning's miss)
- previous day's urges (a relapse the night before)

If any of those were bad, the slip gets a cause. If none of them were, it goes into
`unexplained_slips` — the retro never invents a cause. Auto-filled (defaulted)
habit, sleep, and screen rows are explicitly excluded from being counted as evidence,
so guesses never count as history, feed into defaults, or fabricate consistency.

The top 3 chains (ranked by number of upstream signals) are stored in `summary.chains`
as structured JSON with ISO dates and weekday names. That's what both the fallback
narrative and the LLM prompt operate on.

### The trust pipeline

```
retro_engine.build_summary()   ← deterministic facts, no model involved
        ↓
narrate_structured()           ← LLM narrates ONLY from those facts
        ↓
_validate()                    ← cited_days must appear in the facts JSON,
                                  tone gate rejects prescriptive language,
                                  observation ≤ 450 chars, retried once
        ↓
fallback_narrative()           ← used if LLM is down OR validation fails twice
```

`narrated: false` in the response means the deterministic path ran — that's the
safe outcome, not a failure. Tune `RETRO_TASK` in `voice_config.py` and bump
`VOICE_VERSION` to iterate on narration quality.

### Closing the feedback loop

`GET /retros/latest` returns `pending_ratings`: insights from before this week
that the user hasn't rated yet. `POST /retros/{week}/complete` marks the retro
done and **then** calls `InsightsService.refresh()`, so the user's ratings are
already in before new insights are generated.

A soft gate in `InsightsService.refresh()` returns `rate_previous_first` when 3 or
more insights older than 7 days are still unrated — the loop can't be silently ignored.

### Known limits

- **Chain tracer is deliberately simple.** It looks at 4 upstream signals. It won't
  find anything subtler than that — `unexplained_slips` is the honest "I can't see why."
- **Mission context is "now", not "then".** The active mission shown in a retro reflects
  today's state, not the state during that week.
- **LLM narration holds a DB connection during the LLM call**, same as insights.
  Acceptable for now; fix with a background task when you scale.
- **Study, urges, and Groq** are stubbed. The stubs satisfy the interface, so the
  retro works end-to-end now (with `narrated: false`). Replace stubs slice by slice.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then fill in your actual Supabase values
```

Run migrations against your Supabase project's SQL editor (or `psql`) in order:

```
migrations/001_init_habit_and_checkin.sql
migrations/002_sleep_and_screen_time.sql
migrations/003_missions_defaults_grants.sql
migrations/007_weekly_retros.sql
```

```bash
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for interactive API docs.

## Cron jobs

| Job | Schedule | Command |
|-----|----------|---------|
| Generate weekly retros | Daily | `python -m app.jobs.generate_retros` |

Daily rather than weekly because users in different timezones finish their Sunday
at different times. Generation is idempotent — one retro per user per week.

## Running tests

```bash
python -m pytest -v
```

Tests use fully in-memory fakes — no database or network required. All 114 tests passing across unit, service, security, and API integration suites.

## What has NOT been verified against a live database

- **SQL migrations** have not been executed against a real Postgres/Supabase instance.
  The SQL is carefully reviewed (correct RLS syntax, FK references to `auth.users`,
  `pgcrypto` extension for `gen_random_uuid()`) but **"reviewed" ≠ "executed."**
  Run against a scratch Supabase project first.
- **JWT verification**: the HS256 shared-secret path is unit-tested.
  The JWKS asymmetric path (`AUTH_MODE=jwks`) exercises the cache and decode
  logic but requires a live JWKS endpoint to validate end-to-end.
- **Rate limiting** is in-memory and process-local. It resets on every restart
  and is not coordinated across multiple workers. Acceptable for a single-process
  deployment; add Redis if you scale out.
- **LLM narration** (`narrated: true`) requires a wired Groq key (later slice).
  Without it, retros fall back to deterministic chain text (`narrated: false`),
  which is the safe and honest outcome.
