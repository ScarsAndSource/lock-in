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
POST   /habits/                      create habit
GET    /habits/                      list habits
PATCH  /habits/{id}                  update habit
DELETE /habits/{id}                  archive habit
POST   /habits/{id}/log              log habit status for a date
GET    /habits/{id}/logs             list habit logs

POST   /checkins/v2                  upsert daily check-in (bulk form)
GET    /checkins/v2/{date}           get check-in for a date
GET    /checkins/v2/defaults         compute opt-out defaults for today

GET    /sleep/                       list sleep logs
POST   /sleep/                       create/upsert sleep log
DELETE /sleep/{date}                 delete sleep log

GET    /screen-time/                 list screen-time logs
POST   /screen-time/                 create/upsert screen-time log
DELETE /screen-time/{date}           delete screen-time log

GET    /stats/                       overall stats summary
GET    /stats/habits/{id}            consistency score for one habit
GET    /stats/habits/{id}/patterns   detected patterns for one habit

POST   /missions/                    start a mission
GET    /missions/                    active mission
GET    /missions/history             completed / abandoned missions
POST   /missions/{id}/complete       complete a mission
POST   /missions/{id}/abandon        abandon a mission

GET    /profile/                     get profile
PUT    /profile/                     upsert profile

GET    /retros                       list past retros (up to 52)
GET    /retros/latest                latest retro with pending insight ratings
GET    /retros/{week_start}          get retro for a specific Monday
POST   /retros/generate              generate (or retrieve) this week's retro
POST   /retros/{week_start}/complete mark retro done → triggers insight refresh

GET    /account/me/export            export all user data as JSON
DELETE /account/me                   delete account and all data
```

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

Tests use fully in-memory fakes — no database or network required.

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
