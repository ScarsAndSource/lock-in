# Lock'in backend

## Slice status

| Slice | What | Status |
|-------|------|--------|
| 1 | Habit domain, unified daily check-in (defaults engine, encrypted journal) | ✅ Done |
| 3 | Sleep + screen-time logging, basic stats | ✅ Done |
| 3b | Missions (goal-scoped sprints) | ✅ Done |
| 3c | Schedule service, consistency scoring, pattern detection, profile, account export/delete, rate limiting | ✅ Done |
| 4 | Study sessions (`subjects` + `study_sessions`) | ✅ Done |
| 5 | Urge / relapse logging (encrypted free-text) | ✅ Done |
| 6 | Goals & Implementation intentions (If-then plans) | ✅ Done |
| 8 | Weekly retrospective — chain tracing, LLM narration, feedback loop, daily cron job | ✅ Done |
| 7 | Groq LLM layer, crisis safety net, daily call cap, voice v2, stateless chat | ✅ Done |
| 7b | Stored chat threads (encrypted at rest, server-side history window, retention pruning) | ✅ Done |
| 8b | Per-habit and global pauses (consistency, chain, check-ins, intentions) | ✅ Done |
| 11 | Tasks: AI free-text capture, cadence chores, reminders, backoff nudges, web push | ✅ Done |

## Endpoints (current)

```
POST   /chat                         stateless chat over logs (?history=[])
GET    /support/resources            public crisis helplines (?region=)
POST   /chat/messages                send message in thread (starts new thread if thread_id omitted)
GET    /chat/threads                 list chat threads (?limit=)
GET    /chat/threads/{id}            get thread messages (?limit=&before=)
PATCH  /chat/threads/{id}            rename chat thread
DELETE /chat/threads/{id}            delete chat thread
DELETE /chat/threads                 delete all chat threads

POST   /tasks/capture                free text -> structured tasks (AI; falls back to your own words)
GET    /tasks/focus                  Now / Small things / Later today / Stopped nudging
POST   /tasks                        create a task by hand
GET    /tasks                        list tasks (?status=open|done|dropped)
PATCH  /tasks/{id}                   edit (title, notes, importance, due, remind, repeat_days, status)
POST   /tasks/{id}/done              complete (cadence tasks come due again N days from now)
POST   /tasks/{id}/snooze            snooze 5 min .. 7 days
DELETE /tasks/{id}                   delete

GET    /notifications/vapid-key      public push key (null = push not configured)
GET    /notifications/prefs          quiet hours, digest hour, daily cap, device count
PATCH  /notifications/prefs          update them
PUT    /notifications/subscription   register this browser for push
DELETE /notifications/subscription   unregister it
POST   /notifications/test           send a test push to your devices

POST   /pauses                       create pause (?habit_id=)
GET    /pauses                       list pauses (?include_past=&habit_id=)
POST   /pauses/{id}/end              end running pause today
DELETE /pauses/{id}                  delete pause

POST   /habits                       create habit
GET    /habits                       list habits (?include_archived=bool)
PATCH  /habits/{id}                  update habit (rename / archive / unarchive / schedule)
POST   /habits/{id}/logs             log habit status for a date (upsert)
DELETE /habits/{id}/logs/{date}      un-log habit status for a date

GET    /checkins/{date}/defaults     compute opt-out defaults for date
POST   /checkins/{date}/confirm      confirm check-in (habits + sleep + screen + journal)
GET    /checkins/{date}/journal      get decrypted journal for date

POST   /sleep/logs                   create/upsert sleep log
GET    /sleep/logs/{date}            get sleep log for a date
GET    /sleep/logs                   list sleep logs (?start_date=&end_date=)
DELETE /sleep/logs/{date}            delete sleep log for a date

POST   /screen-time/logs             create/upsert screen-time log
GET    /screen-time/logs/{date}      get screen-time log for a date
GET    /screen-time/logs             list screen-time logs (?start_date=&end_date=)
DELETE /screen-time/logs/{date}      delete screen-time log for a date

GET    /study/subjects               list study subjects
POST   /study/subjects               create study subject
PATCH  /study/subjects/{id}          rename / archive subject
POST   /study/sessions               log study session
GET    /study/sessions               list study sessions (?start_date=&end_date=)
DELETE /study/sessions/{id}          delete study session

POST   /urges/quick-capture          quick-capture urge log (resisted/relapsed)
POST   /urges/{id}/detail            add/update encrypted urge details
GET    /urges                        list urge logs (?start_date=&end_date=)
DELETE /urges/{id}                   delete urge log

POST   /goals                        create goal across domains
GET    /goals                        list goals (?status=)
PATCH  /goals/{id}                   update goal status/target
GET    /goals/progress               get goal progress metrics

POST   /intentions                   create implementation intention (if-then plan)
GET    /intentions                   list implementation intentions (?domain=&active_only=)
GET    /intentions/due               list due intentions for surfacing
PATCH  /intentions/{id}              update intention cue/action/status
DELETE /intentions/{id}              delete implementation intention

GET    /stats/consistency            rolling consistency score (?end_date=&window_days=)
GET    /stats/chain                  multi-domain chain strip (?end_date=&days=)
GET    /stats/patterns               detected cross-domain patterns (?end_date=&days=)

POST   /insights/refresh             refresh pattern insights
GET    /insights                     list pattern insights (?unrated_only=bool&limit=int)
POST   /insights/{id}/feedback       rate pattern insight (accurate, not_quite, unsure)

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
- **Groq** is stubbed. The stubs satisfy the interface, so the
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
migrations/004_study.sql
migrations/005_urges.sql
migrations/006_goals_and_intentions.sql
migrations/007_weekly_retros.sql
migrations/008_pattern_insights.sql
migrations/009_llm_usage.sql
migrations/010_pauses.sql
migrations/011_chat_threads.sql
migrations/012_pauses_per_habit.sql
migrations/013_tasks_and_nudges.sql
```

```bash
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for interactive API docs.

## Cron jobs

| Job | Schedule | Command |
|-----|----------|---------|
| Generate weekly retros | Daily | `python -m app.jobs.generate_retros` |
| Send task nudges (web push) | Every 5 minutes | `python -m app.jobs.send_nudges` |

Daily rather than weekly because users in different timezones finish their Sunday
at different times. Generation is idempotent — one retro per user per week.

## Running tests

```bash
python -m pytest -v
```

Tests use fully in-memory fakes — no database or network required. All 136 tests passing across unit, service, security, and API integration suites.

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

## Slice 11 — tasks, reminders, nudges

### What a task is (and what the code does NOT know)
One `tasks` table covers deadlines ("lab report friday 5pm"), exact reminders ("remind me at 6pm") and cadence
chores ("call nani every few days", "laundry"). There is no list of family members, chores or categories anywhere in
code. The capture step reads the person's own sentence and fills three generic knobs: `importance` (1 small, 2 normal,
3 real deadline), when (`due` / `remind`), and `repeat_days`. A cadence chore is just a task with `repeat_days` set;
completing it schedules the next one N days from **completion**, so being late never makes tasks pile up.

### Capture pipeline (same trust model as chat/retros)
```
crisis screen on raw text ──► support payload, nothing stored, no model call
        ↓
LLM extracts JSON ──► validated in code (title/length caps, importance 1..3, repeat 1..365,
        │               due/remind through the same strict local-time parser as the API,
        │               past reminders dropped, max 12 tasks, duplicates of open tasks skipped)
        ↓
model down / over budget / junk twice ──► your words kept as plain tasks, mode="fallback"
```
The capture counts against the same per-user daily AI cap (feature label `tasks`; migration 013 widens the
`llm_usage` check constraint — without it every capture would fail on cap bookkeeping).

### Nudge policy (`services/nudge_policy.py`, pure and fully tested)
- A task is only nudged once its **trigger** passes: exact reminder, else due time, else (date-only) the person's
  nudge hour that day. No trigger = backlog = never pushed.
- Nudges **back off, never escalate**: gap = base × 2^(nudges sent) (base 2h / 6h / 24h by importance), and after
  5 / 3 / 2 nudges pushing stops. The task shows under "Stopped nudging" in the app for a decision.
- Small things (importance 1) never ping individually: one **digest** at the nudge hour. Only an exact reminder fires alone.
- Quiet hours always win. A global pause silences everything except the first fire of an exact reminder.
- Daily cap per user; only a push that reached a device counts and advances backoff, so failures just retry.
- More than 3 pushes due at once: the extras collapse into one digest.

### Web push setup
```bash
pip install -r requirements.txt
python -m app.jobs.gen_vapid        # prints VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY -> put both in env
# also set VAPID_SUBJECT=mailto:you@example.com
```
Add a Render Cron Job running `python -m app.jobs.send_nudges` every 5 minutes (same env vars as the API).
Without VAPID keys the app works fine: the task list and focus view just never push.

Security notes: a subscription endpoint is a URL **this server POSTs to**, so `PUT /notifications/subscription` only
accepts https endpoints on known push services (`PUSH_ALLOWED_HOST_SUFFIXES`, SSRF guard). Payloads and keys are never logged.

### Known limits
- Rate limiting is still in-memory/per-process (see above).
- Notification tap opens the app; there are no Done/Snooze buttons on the notification itself (the service worker
  has no access to the auth token). Possible next step.
- A browser shared between two accounts keeps one push endpoint: the second account gets a clear 409 until the
  first turns notifications off.
- Migration 013 and the nudge job have not been run against a live Postgres/Supabase
