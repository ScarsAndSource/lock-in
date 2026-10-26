# Lock'in

**A calm, India-first companion for habits, sleep, study, tasks and the urges you're working on.**
One daily check-in across every part of your life, an AI layer that finds the real chain behind a slip, and a rule that is never broken: **a missed day never resets you to zero.**

Installable PWA (works great on Android) · FastAPI + Supabase backend · React + TypeScript frontend · Groq for the language layer · Web Push for the companion.

---

## Table of contents

1. [Why Lock'in exists](#1-why-lockin-exists)
2. [Design principles](#2-design-principles)
3. [Feature tour](#3-feature-tour)
4. [How the intelligence works](#4-how-the-intelligence-works)
5. [Privacy and safety](#5-privacy-and-safety)
6. [Tech stack](#6-tech-stack)
7. [Requirements](#7-requirements)
8. [Repository layout](#8-repository-layout)
9. [Quick start (local)](#9-quick-start-local)
10. [Configuration reference](#10-configuration-reference)
11. [Database and migrations](#11-database-and-migrations)
12. [Scheduled jobs](#12-scheduled-jobs)
13. [Web push setup](#13-web-push-setup)
14. [Deployment guide](#14-deployment-guide)
15. [Using the app](#15-using-the-app)
16. [Hands-free capture (phone automations)](#16-hands-free-capture-phone-automations)
17. [API overview](#17-api-overview)
18. [Testing](#18-testing)
19. [Known limits](#19-known-limits)
20. [Troubleshooting](#20-troubleshooting)
21. [Roadmap](#21-roadmap)

---

## 1. Why Lock'in exists

Most self-improvement apps track **one** thing (habits, or screen time, or urges, or study) and treat a missed day as a broken streak. That triggers shame, then avoidance, then abandonment. It is a documented failure mode.

Lock'in does the opposite:

- **One unified daily check-in** across habits, sleep, screen time, study, mood, urges and tasks.
- **Opt-out defaults:** the check-in starts as "same as usual" and you only touch what was different today. Most days take about 10 seconds.
- **A cross-domain chain view** that shows what actually happened ("bad sleep → late screen → skipped gym") instead of tracking each domain in isolation.
- **A rolling consistency score** instead of a streak counter. A single miss dents the percentage; it never zeroes it.
- **A companion (Maruti)** that speaks up only when it matters, learns *your* rhythm, and backs off instead of nagging.

> Lock'in is a tracking and insight tool. It is **not** therapy or clinical addiction treatment, and it says so.

---

## 2. Design principles

| Principle | What it means in practice |
|---|---|
| **Never reset to zero** | Rolling N-day consistency plus a "longest run" for reference. No shame mechanic. |
| **Never miss twice** | After a slip, the next day shrinks to a minimum viable day (the "floor" version of each habit). |
| **Defaults are guesses, not history** | Auto-filled sleep, screen and habit rows are flagged and are **never** counted as evidence in patterns, retros or experiments. |
| **Facts first, words second** | Deterministic code computes the facts; the LLM may only narrate them, and its output is validated in code. If the model is down, a deterministic fallback runs. |
| **Back off, never escalate** | Nudges space out (base × 2ⁿ) and then stop. One daily push budget is shared by every kind of notification. |
| **Quiet by default** | Quiet hours, pauses and rest days always win. Lock-screen text never reveals private content. |
| **Not a social product (with one careful exception)** | Accounts are isolated islands. The optional Crew layer is small, opt-in, and built around showing up, not ranking. |
| **No cheap gamification** | No points, no coins, no leaderboards. |
| **Direct, not cruel** | Blunt about the *pattern in the data*, never about your worth. No identity-level language ("you're lazy"). |

---

## 3. Feature tour

The app has four tabs: **Now**, **Maruti** (the companion chat), **Mirror** and **Crew**. Settings opens from the profile button in the header. A floating **urge button** is available on every tab except the Maruti tab.

### 3.1 Now: what to do right now

- **Day orbit:** a compact view of where you are in your own day, shaped by your learned rhythm.
- **Next card (next-best-action engine):** the *one* thing the app leads with. Candidates are scored (not hard-ordered) so rhythm can move things. Priority, high to low: the floor version of a habit after a slip, a deadline task, a risk-window guard, "close today" near your usual check-in time, a habit, the next task, a check-in nudge. "Not now" skips it and the next candidate rises. If nothing is left you get an honest "all clear".
- **Habit checklist and task list** in one card.
- **Quick add:** type a sentence ("lab report friday 5pm", "call nani every few days") and the AI turns it into structured tasks.
- **Inference chip:** if you haven't logged last night, the app says what the phone already knows and asks one yes/no ("~6.5h, right?") instead of showing an empty form.
- **Status chips and a 7-day weave:** a colour-coded strip, one dot per domain per day.
- **Gentle prompts and journey nudges** that appear as your account matures (see [slow unlock](#37-journey-seasons-exam-radar-snapshot-shelf)).
- **Show everything:** one tap to skip the slow-unlock ladder.

### 3.2 The unified daily check-in

- **Opt-out defaults:** computed from your own declared baseline and history; correct only what differs.
- **Habits** with done / skipped / partial plus a note. Schedules can be weekday-based or "n per week".
- **Sleep** (bedtime, wake time, quality 1–5), **screen time** (minutes plus optional category breakdown), **study** (subject, planned vs actual minutes), **mood** (a 1–5 "how it felt" tap), **urges**, and an **encrypted journal** note.
- **Three ways to capture instead of typing into fields:**
  - **Typed sentence** → parsed into a proposed check-in.
  - **Voice** → recorded, transcribed (Groq Whisper), then parsed.
  - **Screenshot** of your phone's screen-time page → read by a vision model.
  - All three only **pre-fill** the form. You still lock it in.
- **"Lock it / Rough day"** one-tap close from the evening notification.
- **Fix a wrong default after the fact**, not just before.
- **Bounce-back protocol:** after a slip, unlogged habits are proposed at their floor version and the app says so plainly.

### 3.3 Maruti: the agentic companion

- **Chat grounded in your own logs.** Ask "why do I keep failing at gym?" and the answer comes from your data. Numbers the model invents are caught and replaced with a fallback.
- **It can act, not just answer.** Say "log gym as done" or "move my lab report to tomorrow". Supported actions include logging habits and sleep, capturing, completing, snoozing and rescheduling tasks, and setting if-then plans.
  - Unambiguous actions apply immediately with an **Undo**.
  - Ambiguous ones come back as a **confirmation card** and are re-validated server-side before anything is written.
- **Stored threads**, encrypted at rest, with rename, delete one and delete all. Idle threads are pruned after `CHAT_RETENTION_DAYS` (default 90).
- **Tone dial:** *Auto* (blunt by default, gentler after a rough stretch), *Direct* (always blunt), *Coach* (always warmer, same facts).
- **Maruti on screen:** an animated, Hanuman-inspired mascot with moods, idle activities, quick reactions and tab-aware lines. A calm mode and reduced-motion support are respected.

### 3.4 Mirror: reflect and review

Mirror has three sub-tabs: **Overview**, **Growth** and **Journey**.

**Overview**
- **Weekly retrospective:** the chain that actually happened that week (see [section 4](#4-how-the-intelligence-works)). Includes a **rough-week mode** and a prompt to rate last week's insights.
- **Active mission:** a goal-scoped sprint with phases and checkpoints.
- **14-day chain weave.**
- **Experiments (N-of-1):** "does going to bed earlier improve my mood?" with an honest verdict.
- **Patterns and insights:** cross-domain correlations, each citing the logs it is based on, each rateable (*accurate / not quite / unsure*).
- **Log and review tiles:** Habits, Sleep, Screen, Study, Urges, Pauses.

**Growth** (reflective extras, kept out of the main view)
- **Mini journal** ("jar"): one note per day, encrypted, the same field as the check-in journal.
- **Identity layer:** "who you want to become": why now, importance 0–10, confidence 0–10, and a saved identity sentence surfaced in your weekly review.
- **Habit check-up (autopsy):** after about three weeks of struggling, an optional check: *too big / wrong time / wrong trigger / don't care*, then it helps fix the habit. "Later" and "skip" are always available.
- **Notes to future self:** a text note or a ~20s voice note delivered at your usual slip time. The push never contains the note itself.

**Journey** ([details](#37-journey-seasons-exam-radar-snapshot-shelf))

### 3.5 Crew: a small, gentle social layer

Optional and opt-in. Needs a real account (not available in demo mode).

- **Usernames:** 3–20 characters, lowercase letters, digits and underscores, starting with a letter.
- **Crews:** up to **3 crews** per person, up to **6 people** per crew. Invite by username or by a time-limited invite code.
- **Share controls:** you choose what a crew can see. **Quiet** a crew to mute it. **Block** a user.
- **Sunday card:** a weekly snapshot per crew built around *showing up* (planned days respect pauses and floor days; study hours are capped per day so nobody trades sleep for a number).
- **Preset cheers:** `showed_up`, `proud`, `hard_week`, `rooting`. One per person per day. No free text.
- **Boost requests**, **buddy deals** (max two active at once), a shared **crew goal**, and optional **duels** (max two at once).
- **Privacy by design:** cross-user data only moves through audited `SECURITY DEFINER` SQL functions; the crew tables are closed to the API role. Nothing you missed is visible to others.

### 3.6 Tasks, reminders and nudges

- **Free-text capture:** one sentence in, structured tasks out (title, importance 1–3, due, remind, repeat). If the model is down or over budget, your own words are kept as plain tasks.
- **Cadence chores:** "every few days" tasks come due again N days after **completion**, so being late never piles tasks up.
- **Focus view:** *Now / Small things / Later today / Stopped nudging.*
- **Snooze** from 5 minutes to 7 days.
- **Nudge policy:** a task is nudged only after its trigger passes. Gaps grow (2h/6h/24h base × 2ⁿ); pushing stops after 5 / 3 / 2 nudges by importance. "Small things" never ping individually: one digest. If more than 3 pushes are due at once the extras collapse into one digest.
- **Calendar and exams:** import an `.ics` file or photograph a printed timetable. Events are classified as *exam / class / other*.
- **Exam awareness:** at most one nudge, scaled by how close the nearest exam is. It never pretends to know your syllabus.

### 3.7 Journey: seasons, exam radar, snapshot, shelf

- **Seasons:** 6 focus weeks plus 1 easy week (49 days). At most **3 focus habits**; others are *benched* (still loggable, just quiet). The cap only refuses *new* habits, never deletes or archives anything. When a season ends the app invites the next one.
- **Exam radar:** *not* a study helper. You list the subject and the **topic names** that will come up; the app brings that list back at **+1, +3, +7 and +14 days** as "a quick look". Never on easy-week days, pauses or exam days; at most 2 per day; missed reviews are rescheduled forward, never shown as overdue.
- **Monthly life snapshot:** a short set of questions with 30/60/90-day change. A low wellbeing score points to people and support, **not** coaching.
- **Graduation shelf ("done becoming"):** the app *offers*, you decide. Retired habits get check-ins at +30 and +90 days and can be revived.
- **Slow unlock:** a new account grows into the app. Stage 0 is one card plus the check-in; stages 1–4 add tasks, the weave and chips, Growth and Journey, then everything (gated by account age and real check-ins). Existing accounts start at the top stage.

### 3.8 Study, sleep, screen time, urges

- **Study:** per-user subjects (empty by default, created inline or by pasting a comma-separated list), sessions with planned vs actual minutes, weekly summary.
- **Sleep:** manual logs, passive logs from phone automations, and inference from your own activity gaps.
- **Screen time:** manual, screenshot-parsed, or automation-fed.
- **Urges:** a genuine **2-tap quick capture** (*resisted / relapsed*) that is a complete, valid log on its own. Detail (intensity, trigger, coping, note) can be added later, and free-text fields are **field-level encrypted**. Available from a home-screen shortcut and the floating button.
- **Risk windows:** the hours when *your own* urges cluster, learned from your own log. They fade when your behaviour changes.

### 3.9 Goals, if-then plans, pauses

- **Goals** per domain (e.g. gym 5×/week, study hours/week) that also seed the check-in defaults.
- **Implementation intentions (if-then plans)** for habits, urges, study and sleep. Surfaced when relevant, and they go quiet while their habit is paused.
- **Pauses:** per-habit or global, with presets ("just today", "until Sunday"), one-tap quick pause and resume. Paused days shrink the plan instead of becoming misses.

### 3.10 The companion's push notifications

All of these share **one daily budget** and obey quiet hours, pauses and the anti-nag rules:

| Moment | What it says |
|---|---|
| Morning | One thing, once, shortly after you usually wake (*Start / Not today*) |
| Habit | One open habit, with your if-then plan or floor version |
| Check-in | Evening "Does today look normal?" (*Lock it / Rough day*) |
| Risk guard | ~30 min before an hour your urges cluster, with your own plan, neutral on the lock screen |
| Wind-down | ~40 min before your usual bedtime |
| Study | Only when this week's study goal is falling behind |
| Comeback | After 2+ silent days: one habit, floor version only |
| Insight | A neutral "a pattern showed up". It never names the pattern on the lock screen |
| Crew | Sunday card, boost request, buddy-deal prompt |
| Future self | Your own note, at your usual slip time |

- **Actionable pushes:** buttons on the notification call the API with a **signed, single-use, short-lived token** (no session needed in the service worker). Tapping the body deep-links into the right screen.
- **Adaptive send time:** the app learns which hour you actually respond to (Thompson sampling with an exploration floor) and drifts toward it.

### 3.11 Account and data

- **Email + password** sign-in via Supabase Auth, email confirmation, magic link ("forgot password" too), silent token refresh.
- **Demo mode:** try everything with mock data; nothing is saved.
- **Export** all your data as JSON (journals decrypted). **Delete** your account and all data irreversibly.
- **Timezone** setting, **tone** preference, notification preferences (quiet hours, digest hour, daily cap, devices).

---

## 4. How the intelligence works

Lock'in uses an LLM **only where language helps**, and never as the source of truth.

```
deterministic code computes the facts
        ↓
LLM narrates ONLY from those facts      (JSON mode, user text isolated as data)
        ↓
validators in code: cited days must exist in the facts, tone gate rejects
prescriptive/shaming language, length caps, one retry
        ↓
deterministic fallback if the model is down, over budget, or fails validation
```

- **Chain tracer (weekly retro):** for each slip, checks same-day sleep, same-day screen, previous-day screen and previous-day urges. If none explain it, it goes into `unexplained_slips`. The retro never invents a cause.
- **Rough-week mode:** detected deterministically (two independent signals plus enough data). The shift is in *scope* (one thing that held, at most one chain, one minimum next step), not softness.
- **Pattern finder and same-day insights:** run after you confirm a check-in; de-duplicated over 7 days; gated by "rate your old insights first".
- **Experiments:** two-sided permutation test on the difference of means. Metrics: sleep hours, screen minutes, mood, habit completion, task completion. Needs at least 5 baseline and 4 test days or it says **"not enough data"**.
- **Rhythm model:** times of day on a circle (23:50 and 00:10 are 20 minutes apart); no rhythm is invented when your times are all over the place.
- **Voice and tone** live in a small versioned config, so tone can be tuned without touching app logic.
- **LLM budget:** a per-user daily call cap (`LLM_DAILY_CALL_CAP`, default 80, resets 00:00 UTC) plus per-minute and per-hour limits. Prompts, completions and keys are never logged.

---

## 5. Privacy and safety

- **Row Level Security on every table**, applied per request (`SET LOCAL ROLE authenticated` with the user's JWT claims). Background jobs open one transaction per user with that user's RLS context.
- **Field-level encryption** (Fernet) for journals, urge details, chat threads, notes, topics and other free text. Supports **key rotation** via `FIELD_ENCRYPTION_OLD_KEYS`.
- **Crisis safety net (hard requirement):** detection is a deliberately **high-recall, hard-coded** pass that runs *before* any model call, is never rate-limited, never touches the AI cap, and answers with fixed text plus real helplines. No model is involved. India resources (112, Tele-MANAS and others) are curated; other regions get a generic emergency and find-a-helpline fallback. Re-verify the numbers periodically (`VERIFIED_ON` in `safety.py`).
- **Prompt-injection isolation:** journal and chat text are passed as data, never concatenated into system context.
- **Calendar import is untrusted input:** a small bounded `.ics` parser with hard caps; location, description, attendees and links are never read.
- **Push SSRF guard:** subscription endpoints must be https on known push services (`PUSH_ALLOWED_HOST_SUFFIXES`).
- **Ingest tokens are write-only:** they can add sleep/screen events (or mark one habit done) and cannot read anything. Per-device, revocable, and redacted from access logs.
- **Request hardening:** 256 KB body cap (5 MB on the upload routes), request IDs, `Cache-Control: no-store`, `nosniff`, CORS pinned to your frontend origin, rate limiting on every router.
- **Lock-screen privacy:** pushes never carry journal text, future-self notes or the name of a detected pattern.

---

## 6. Tech stack

**Backend**

| Piece | Choice |
|---|---|
| Language | Python 3.12 (`.python-version` pins 3.12.7) |
| Framework | FastAPI 0.115, Uvicorn 0.30 (standard extras) |
| Validation | Pydantic 2.9, pydantic-settings 2.5 |
| Database access | SQLAlchemy 2.0 (async) + asyncpg 0.29 (statement cache off for the Supabase pooler) |
| Database and auth | Supabase (Postgres, RLS, GoTrue email auth) |
| Auth verification | python-jose: HS256 shared secret **or** JWKS (ES256/RS256) |
| Encryption | `cryptography` (Fernet) |
| LLM | Groq (OpenAI-compatible) over httpx: chat/JSON `llama-3.3-70b-versatile`, speech `whisper-large-v3-turbo`, vision `meta-llama/llama-4-scout-17b-16e-instruct` (all configurable) |
| Push | pywebpush 2.0 (VAPID), service worker on the client |
| Testing | pytest 8, pytest-asyncio |

**Frontend**

| Piece | Choice |
|---|---|
| UI | React 18 + TypeScript 5 |
| Build | Vite 5 (code-split per tab and sheet) |
| Styling | Tailwind CSS 3.4, `clsx`, `tailwind-merge` |
| Icons and fonts | `lucide-react`, Material Symbols, Bricolage Grotesque and Hanken Grotesk (Google Fonts) |
| Auth | Supabase GoTrue over plain `fetch` (no SDK) |
| PWA | `manifest.json` with shortcuts, a service worker with a per-build cache ID |

**Architecture notes:** pure-function domain logic (`domain*.py`, rhythm, policies, math) kept apart from services, repositories (behind Protocol interfaces) and routers, so rules are testable without a database. Raw SQL migrations, an ORM↔DB schema-drift check at startup, and in-memory fakes for tests.

---

## 7. Requirements

**To run locally**

- Python **3.12**
- Node.js **18+** (developed on Node 22) and npm
- A **Supabase** project (free tier is fine): Postgres database, JWT secret (or JWKS URL), project URL and anon key
- Optional but recommended:
  - A **Groq API key** (without it, everything falls back to deterministic text; voice and screenshot capture need it)
  - **VAPID keys** for push (without them the app works, it just never pushes)

**To deploy**

- A host for the API (Render is the setup this project is designed for) plus a scheduler that can run four commands
- A static host for the frontend (Vercel is the setup this project is designed for)
- HTTPS on both. Service workers and push require it.

**Platform notes**

- Built for **Android first** (installable PWA, web push).
- **iOS** requires the PWA to be **added to the home screen** before it can grant push permission, and notification buttons are limited there, so tapping the notification body is how a push finishes the job.

---

## 8. Repository layout

```
lockin/
├── README.md
├── SPEC.md                    # original product spec (problem, non-goals, tone ceiling)
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   ├── .python-version
│   ├── migrations/            # 001 → 027, raw SQL, run in order
│   ├── tests/                 # in-memory fakes, no database needed for most suites
│   └── app/
│       ├── main.py            # app, middleware, error handlers, /health, /ready
│       ├── config.py          # every setting, from env vars
│       ├── db.py              # one transaction per request, RLS context
│       ├── security.py        # JWT verification, field encryption
│       ├── safety.py          # hard-coded crisis path
│       ├── ratelimit.py       # per-user sliding window
│       ├── schema_check.py    # ORM ↔ DB drift guard
│       ├── domain*.py         # plain dataclasses, no DB dependency
│       ├── models*.py         # SQLAlchemy models
│       ├── schemas*.py        # Pydantic request/response models
│       ├── routers/           # HTTP endpoints
│       ├── services/          # business logic (mostly pure)
│       ├── repositories/      # DB access behind Protocols
│       └── jobs/              # cron entry points (never imported by the HTTP app)
└── frontend/
    ├── package.json
    ├── .env.example
    ├── vite.config.ts         # also stamps a build ID into dist/sw.js
    ├── tailwind.config.js
    ├── public/                # manifest, service worker, favicon, Maruti artwork
    └── src/
        ├── App.tsx            # shell, tabs, deep links
        ├── views/             # Now, Maruti (chat), Mirror, Crew
        ├── components/        # incl. growth/, journey/, crew/, maruti/
        ├── api/               # typed client, live and demo modes
        ├── context/           # app and crew state
        ├── hooks/ lib/ store/ types/
```

---

## 9. Quick start (local)

### 1) Supabase

1. Create a project at [supabase.com](https://supabase.com).
2. Note: the **Postgres connection string**, the **JWT secret** (Settings → API), the **project URL** and the **anon key**.
3. Run all migrations **in order** (see [section 11](#11-database-and-migrations)) in the SQL editor.

### 2) Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# generate the field-encryption key and paste it into FIELD_ENCRYPTION_KEY:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

uvicorn app.main:app --reload
```

- API: <http://localhost:8000>
- Interactive docs: <http://localhost:8000/docs>
- Liveness: `GET /health` · Readiness (checks the database): `GET /ready`

### 3) Frontend

```bash
cd frontend
npm ci
cp .env.example .env.local           # set VITE_* values
npm run dev                          # http://localhost:5173
```

Production build: `npm run build` (type-checks with `tsc`, then bundles to `dist/`).

### 4) First run

Open <http://localhost:5173>, create an account (or tap **Try the demo**), and follow [Using the app](#15-using-the-app).

> **Set `FIELD_ENCRYPTION_KEY` once and never lose it.** Journals, urge notes, chats and other encrypted text cannot be decrypted without it.

---

## 10. Configuration reference

### Backend (`backend/.env`)

**Core and auth**

| Variable | Default | Notes |
|---|---|---|
| `APP_ENV` | `development` | Set `production` when deployed |
| `DATABASE_URL` | *(required)* | `postgresql+asyncpg://…` Use the **pooler** URL if your host needs IPv4 |
| `AUTH_MODE` | `hs256` | `hs256` (shared secret) or `jwks` (asymmetric) |
| `SUPABASE_JWT_SECRET` | | Required for `hs256` |
| `SUPABASE_JWKS_URL` | | Required for `jwks`, e.g. `https://<ref>.supabase.co/auth/v1/.well-known/jwks.json` |
| `SUPABASE_JWT_AUDIENCE` | `authenticated` | |
| `SUPABASE_JWT_ISSUER` | | Optional, e.g. `https://<ref>.supabase.co/auth/v1` |
| `FIELD_ENCRYPTION_KEY` | *(required)* | Fernet key. **Never lose it.** |
| `FIELD_ENCRYPTION_OLD_KEYS` | | Comma-separated previous keys, for rotation |
| `CORS_ALLOW_ORIGINS` | `["http://localhost:5173"]` | JSON list. In production: the exact frontend origin, no trailing slash |

**Safety rails**

| Variable | Default | Notes |
|---|---|---|
| `RLS_ENFORCED` | `true` | Keep `true` outside local debugging |
| `SCHEMA_CHECK_MODE` | `warn` | `off` / `warn` / `strict`. `strict` refuses to boot on ORM/DB drift |
| `RATE_LIMIT_ENABLED` | `true` | |
| `RATE_LIMIT_PER_MINUTE` | `120` | Per user, all routes |
| `RATE_LIMIT_EXPORT_PER_HOUR` | `5` | |
| `RATE_LIMIT_INSIGHTS_REFRESH_PER_HOUR` | `10` | |
| `RATE_LIMIT_CHAT_PER_MINUTE` / `_PER_HOUR` | `6` / `60` | |
| `RATE_LIMIT_CAPTURE_PER_MINUTE` | `10` | Task capture |
| `RATE_LIMIT_MEDIA_PER_MINUTE` / `_PER_HOUR` | `6` / `40` | Voice and image uploads |
| `RATE_LIMIT_PUSH_TEST_PER_HOUR` | `6` | |
| `RATE_LIMIT_INGEST_PER_MINUTE` | `20` | Per ingest token |
| `RATE_LIMIT_CREW_LOOKUP_PER_HOUR` | `30` | Username, invite and block lookups |
| `RATE_LIMIT_CREW_CODE_PER_HOUR` | `10` | Invite-code join attempts |
| `RATE_LIMIT_PUSH_ACTION_PER_MINUTE` | `30` | Per client IP (action endpoint has no session) |

**LLM (Groq)**

| Variable | Default | Notes |
|---|---|---|
| `GROQ_API_KEY` | *(empty)* | Empty = deterministic fallbacks everywhere |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Check Groq's current model list before deploy |
| `GROQ_TRANSCRIBE_MODEL` | `whisper-large-v3-turbo` | Voice check-in |
| `GROQ_VISION_MODEL` | `meta-llama/llama-4-scout-17b-16e-instruct` | Screenshot and timetable parsing |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | |
| `GROQ_TIMEOUT_SECONDS` | `10` | A request holds its DB connection while Groq answers: keep it short |
| `GROQ_MAX_RETRIES` | `0` | Transport retries per call (max 2) |
| `LLM_DAILY_CALL_CAP` | `80` | Per user per UTC day, all features |
| `CHAT_RETENTION_DAYS` | `90` | `0` = keep forever |
| `MAX_AUDIO_BYTES` / `MAX_IMAGE_BYTES` | `4000000` | |

**Push**

| Variable | Default | Notes |
|---|---|---|
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` | *(empty)* | Empty = push is off; everything else still works |
| `VAPID_SUBJECT` | | `mailto:you@example.com` |
| `PUSH_ACTION_SECRET` | *(empty)* | Signs actionable-push tokens. Empty = derived from `FIELD_ENCRYPTION_KEY` |
| `PUBLIC_API_URL` | *(empty)* | Origin the service worker POSTs actions to. Empty = same origin as the app. **Set this when the API is on a different domain** |
| `PUSH_ALLOWED_HOST_SUFFIXES` | FCM, Mozilla, Apple, Windows | SSRF allow-list for subscription endpoints |

### Frontend (`frontend/.env.local`; baked in at **build time**)

| Variable | Notes |
|---|---|
| `VITE_API_BASE_URL` | Deployed API origin, no trailing slash. Required in production |
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Public anon key (safe to expose) |
| `VITE_BUILD_ID` | Optional. Overrides the build ID stamped into the service worker (otherwise the git commit SHA on Render/Vercel, else a timestamp) |

Without the two Supabase variables the login screen explains sign-in isn't configured and only the demo works.

---

## 11. Database and migrations

Raw SQL in `backend/migrations/`. Run **every file, in numeric order**, in the Supabase SQL editor (or `psql`) before the first boot. They are written to be idempotent.

| # | Migration | Adds |
|---|---|---|
| 001 | `init_habit_and_checkin` | Habits, habit logs, daily check-ins, encrypted journal |
| 002 | `sleep_and_screen_time` | Sleep and screen-time logs |
| 003 | `missions_defaults_grants` | Missions, default grants |
| 004 | `study` | Subjects and study sessions |
| 005 | `urges` | Urge logs (encrypted detail) |
| 006 | `goals_and_intentions` | Goals, if-then plans |
| 007 | `weekly_retros` | Weekly retrospectives |
| 008 | `pattern_insights` | Insights plus user feedback |
| 009 | `llm_usage` | Per-user daily LLM accounting |
| 010 | `pauses` | Global pauses |
| 011 | `chat_threads` | Encrypted stored chat |
| 012 | `pauses_per_habit` | Per-habit pauses |
| 013 | `tasks_and_nudges` | Tasks, push subscriptions, notification prefs |
| 014 | `batch_a_tiers_tone` | Habit tiers (floor versions), tone preference |
| 015 | `batch_b_mood_and_screenshot` | Mood, screenshot screen time |
| 016 | `companion` | Companion events and push ledger |
| 017 | `ingest_tokens` | Write-only automation tokens |
| 018 | `event_spine` | App-activity event spine |
| 019 | `experiments` | N-of-1 experiments |
| 020 | `calendar_events` | Imported classes and exams |
| 021 | `send_time_and_inference` | Adaptive send-time outcomes |
| 022 | `habit_tokens_and_push_dismissal` | Habit-bound tokens, push dismissal |
| 023 | `growth` | Journal, identity, check-ups, notes to future self |
| 024 | `crew_core` | Usernames, crews, members, blocks |
| 025 | `crew_weekly` | Weekly crew cards, cheers, boosts |
| 026 | `crew_deals_goals_duels` | Buddy deals, crew goals, duels |
| 027 | `journey` | Seasons, exam radar, snapshots, graduation shelf |

> The comment at the top of `backend/.env.example` still says "migrations 001 → 015". **Ignore it: run all 27.**

At startup the API compares ORM columns to the live database (`SCHEMA_CHECK_MODE`). Use `warn` while you settle in, then switch to `strict` once every migration is applied.

---

## 12. Scheduled jobs

The HTTP app never runs these; each is a plain command run on a schedule with **the same environment variables as the API**. The minute offsets are deliberate: the three push jobs all touch the daily push counter, so they must not overlap.

| Job | Schedule (cron) | Command | What it does |
|---|---|---|---|
| Task nudges and companion dispatch | `*/5 * * * *` | `python -m app.jobs.send_nudges` | Task reminders plus the companion moments, under one daily budget, for every user with a device |
| Companion moments | `2-59/5 * * * *` | `python -m app.jobs.companion_tick` | Morning/evening moments, same-day insight pulse, crew moments; trims old usage events nightly |
| Notes to future self | `4-59/5 * * * *` | `python -m app.jobs.future_self_tick` | Delivers a note at the person's usual slip time |
| Weekly retros | daily | `python -m app.jobs.generate_retros` | Generates each user's weekly retro. Idempotent (daily because people finish their Sunday at different times) |

One-off helper: `python -m app.jobs.gen_vapid` prints a fresh VAPID key pair.

---

## 13. Web push setup

```bash
cd backend
python -m app.jobs.gen_vapid
# VAPID_PUBLIC_KEY=...
# VAPID_PRIVATE_KEY=...
```

1. Put both keys in the API **and** cron-job environments, plus `VAPID_SUBJECT=mailto:you@example.com`.
2. Set `PUBLIC_API_URL` to the API's public origin if the frontend is on another domain (so the service worker can post notification-button actions).
3. Schedule the three push jobs from [section 12](#12-scheduled-jobs).
4. In the app: **Settings → Notifications → turn on**, then send a **test push**.

Without VAPID keys the app is fully usable; it just never pushes. Subscriptions are limited to 10 per user, and failing endpoints are dropped after repeated failures.

---

## 14. Deployment guide

This is the setup the project is designed for: **Supabase** (DB and auth) + **Render** (API and cron) + **Vercel** (frontend).

### Step 1: Supabase

1. Create the project. Run migrations **001 → 027** in order.
2. **Authentication → Providers:** keep Email enabled.
3. **Authentication → URL configuration:** set the **Site URL** and add a **Redirect URL** for your deployed frontend (confirmation and magic-link emails return there).
4. Collect: Postgres connection string (use the **pooler** URL if your host is IPv4-only), JWT secret (or JWKS URL), project URL, anon key.

### Step 2: Generate secrets

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # FIELD_ENCRYPTION_KEY
python -m app.jobs.gen_vapid                                                                  # VAPID keys
```

Store `FIELD_ENCRYPTION_KEY` somewhere safe and permanent.

### Step 3: API on Render (Web Service)

| Setting | Value |
|---|---|
| Root directory | `backend` |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` (use `/ready` to also verify the DB) |
| Python | 3.12 |

Environment (minimum for production):

```
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://...
AUTH_MODE=hs256                    # or jwks + SUPABASE_JWKS_URL
SUPABASE_JWT_SECRET=...
FIELD_ENCRYPTION_KEY=...
CORS_ALLOW_ORIGINS=["https://your-frontend.example.com"]
RLS_ENFORCED=true
SCHEMA_CHECK_MODE=warn
GROQ_API_KEY=...
VAPID_PUBLIC_KEY=...  VAPID_PRIVATE_KEY=...  VAPID_SUBJECT=mailto:you@example.com
PUBLIC_API_URL=https://your-api.example.com
```

> **Run a single instance / single worker.** Rate limiting is in-memory and per-process.

### Step 4: Cron jobs on Render

Create four Cron Jobs (same repo, root `backend`, same env vars as the API) using the commands and schedules in [section 12](#12-scheduled-jobs).

### Step 5: Frontend on Vercel

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Build command | `npm run build` |
| Output directory | `dist` |
| Env (build time) | `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` |

The app uses in-page tabs (no client-side routes), and notification deep links use `/?a=<where>`, so no SPA rewrite rules are needed.

### Step 6: Pre-launch checklist

- [ ] All 27 migrations applied on the production database
- [ ] `FIELD_ENCRYPTION_KEY` stored safely (backed up outside the host)
- [ ] `CORS_ALLOW_ORIGINS` is the **exact** frontend origin (no trailing slash)
- [ ] `RLS_ENFORCED=true`
- [ ] **`UNLOCK_EPOCH` set to your ship date** in `backend/app/services/unlock.py` (see below)
- [ ] Supabase Site URL and Redirect URL point to the frontend
- [ ] Groq model names checked against Groq's current list
- [ ] VAPID keys set on the API **and** all cron jobs
- [ ] All four cron jobs scheduled
- [ ] `GET /ready` returns `ready`
- [ ] Smoke test: sign up → confirm email → add a habit → lock a check-in → add a task → enable push → send test push → install the PWA on a phone
- [ ] Switch `SCHEMA_CHECK_MODE` to `strict` once everything is applied
- [ ] Crisis helpline numbers re-verified (`VERIFIED_ON` in `safety.py`)

### About `UNLOCK_EPOCH`

The slow-unlock ladder ([section 3.7](#37-journey-seasons-exam-radar-snapshot-shelf)) treats any account created **before** `UNLOCK_EPOCH` as an existing user who keeps every feature. New accounts start at stage 0 and unlock as they use the app.

```python
# backend/app/services/unlock.py
UNLOCK_EPOCH = date(2026, 11, 1)   # set to the day you ship
```

If the epoch is *after* your launch day, everyone who signs up before it skips the ladder and sees everything. Set it to your actual ship date. (Users can always tap **Show everything**.)

### Updating the frontend and PWA

Every build stamps a unique cache name into `dist/sw.js`. HTML is fetched network-first, so a new deploy appears on the very next open; old caches are purged on activate.

---

## 15. Using the app

### First five minutes

1. **Sign up** (email + password, at least 8 characters) and confirm the email. Or tap **Try the demo**.
2. **Set your timezone** (Settings → Timezone).
3. **Add a few habits.** Start small; the "floor version" is the tiny version that still counts on a hard day.
4. **Do your first check-in.** Everything starts at "same as usual". Fix only what's different, then lock it.
5. **Install the app:** in Chrome on Android use *Add to Home screen* / *Install app*. On iPhone you must add it to the Home Screen before notifications can be enabled.
6. **Turn on notifications** (Settings → Notifications) and set quiet hours.
7. **Pick how Maruti talks to you** (Settings → How I talk to you): *Auto*, *Direct* or *Coach*.

### Day to day

| I want to… | Do this |
|---|---|
| Close my day in ~10 seconds | Tap the check-in (or the evening notification's **Lock it**) |
| Say it instead of tapping | In the check-in, type or record a sentence, or upload a screen-time screenshot. It pre-fills; you confirm |
| Add a task | **Quick add** on Now: "dentist appointment thursday 4pm", "water plants every 3 days" |
| Log an urge | Floating urge button (or the home-screen **Urge** shortcut) → *resisted* or *relapsed*. Add detail later if you want |
| Have a rough day | Choose **Rough day** at check-in. The next day shrinks to the floor versions |
| Pause something | Mirror → **Pauses**, or the pause presets on a habit |
| Ask why I keep slipping | Open **Maruti** and ask. Answers come from your logs |
| Make Maruti do something | "log gym done", "snooze the lab report to tomorrow", "if I open Instagram while studying, close the laptop" |
| Undo a Maruti action | Tap **Undo** on the confirmation |

### Weekly and monthly

- **Mirror → Overview:** read your retro, rate last week's insights (this keeps new insights honest), check the 14-day weave.
- **Mirror → Overview → Experiments:** pick a metric and a change, run it, read the verdict.
- **Mirror → Growth:** write in the jar, set your identity sentence, record a note to your future self.
- **Mirror → Journey:** start a **season**, add **exam topic names**, take the monthly **snapshot**, graduate a habit you've "done becoming".

### Calendar and exams

Settings → **Calendar and exams**: import an `.ics` file (Google/Apple/Outlook calendar exports) or photograph a printed timetable. Exams get an exam-aware nudge as they approach.

### Crew

Crew tab → pick a **username** → start a crew or **join with a code** → choose what you share. Everything is optional, and you can quiet or leave a crew any time.

### Your data

Settings → **Your data**: export everything as JSON, or delete your account permanently.

---

## 16. Hands-free capture (phone automations)

A PWA can't read your phone's sleep or screen-time data, but your phone can call a URL. Lock'in gives each automation its **own write-only token**.

1. Settings → **Automations** → pick **Android** (Tasker / MacroDroid) or **iOS** (Shortcuts) and what to automate (**Sleep** or a **Habit**). The app shows copy-ready URLs and step-by-step instructions.
2. Event kinds:

| Kind | Meaning |
|---|---|
| `sleep_start` | Bedtime (e.g. Sleep Focus turns on, or screen locked for the night) |
| `sleep_end` | Wake (e.g. alarm stopped) |
| `screen_time` | A day's total minutes |
| `habit_done` | Marks **one specific habit** done today (habit-bound tokens only) |

3. URL form: `https://<your-api>/ingest/u/<token>/<kind>` (GET or POST), or `POST /ingest/event` with `Authorization: Bearer <token>`.

Token rules: up to **8** active tokens, shown **once**, revocable individually, and events older than **36 hours** are rejected. A token **cannot read anything**, never overwrites a log you made yourself, and its replies never echo a habit's name.

---

## 17. API overview

Interactive docs live at `/docs` (Swagger) on any running instance. All routes except `/health`, `/ready`, `/support/resources`, the push-action endpoint and ingest-by-token require a Supabase JWT (`Authorization: Bearer <access_token>`).

| Area | Prefix | Highlights |
|---|---|---|
| Meta | `/health`, `/ready` | Liveness and DB readiness |
| Account | `/me` | Profile, timezone, tone, **export**, **delete** |
| Habits | `/habits` | CRUD, per-date logs |
| Check-ins | `/checkins` | `/parse` (text), `/voice`, `/{date}/defaults`, `/{date}/confirm`, `/{date}/journal` |
| Sleep / Screen | `/sleep`, `/screen-time` | Logs; `/screen-time/parse-screenshot` |
| Mood | `/mood` | Daily 1–5 |
| Study | `/study` | Subjects (and bulk), sessions, summary |
| Urges | `/urges` | Quick capture, encrypted detail, summary |
| Goals / If-then | `/goals`, `/intentions` | Targets and progress; plans and due plans |
| Pauses | `/pauses` | Create/end/delete, shortcuts, quick pause, resume |
| Missions | `/missions` | Goal-scoped sprints |
| Tasks | `/tasks` | `/capture`, `/focus`, CRUD, done, snooze |
| Notifications | `/notifications` | VAPID key, prefs, subscription, test push |
| Actions | `/actions` | Signed push actions; in-app actions |
| Companion | `/companion` | `/now`, `/events`, `/inference` |
| Chat | `/chat`, `/chat/actions` | Stateless and threaded chat; `/confirm` and `/undo` for agent actions |
| Stats | `/stats` | Consistency, chain, patterns, bounce-back |
| Insights / Retros | `/insights`, `/retros` | Feed and feedback; generate, latest, tone, complete |
| Experiments | `/experiments` | Metrics, active, create, finish, abandon |
| Calendar | `/calendar` | `.ics` import, photo import, events, exams, sources |
| Ingest | `/ingest` | Token management; event endpoints |
| Growth | `/growth` | Prompt, identity, journal, check-ups, future-self notes |
| Journey | `/journey` | State, season, recall, snapshot, shelf, graduate |
| Crew | `/crew` | Overview, username, crews, invites, week, inbox, cheers, boosts, buddy deals, duels, blocks |
| Support | `/support/resources` | Public crisis helplines (`?region=`) |

Errors are JSON `{ "detail": ... }` with sensible codes: 404 not found, 409 conflict, 422 validation, 429 rate limit (with `Retry-After`; a separate message when the daily AI allowance is used), 503 service unavailable. Every response carries an `X-Request-ID`.

---

## 18. Testing

```bash
cd backend
pip install -r requirements.txt
python -m pytest -v
```

The suite (about 490 tests) covers unit, service, security, policy and API-integration layers. Most suites use in-memory fakes and need no database or network. Every pure module (rhythm, nudge policy, companion policy, next-best-action, recall plan, season, unlock, experiments, calendar import, retro engine) has direct tests, and `test_orm_parity.py` catches drift between ORM classes and SQL without a database.

Frontend: `npm run build` runs the TypeScript type-check and a production bundle.

---

## 19. Known limits

- **Rate limiting is in-memory and per-process.** Run one API instance (or add a Redis-backed limiter). Pre-auth abuse isn't covered; put Cloudflare or your host's protections in front.
- **LLM calls hold a DB connection** while Groq answers (kept short by `GROQ_TIMEOUT_SECONDS`).
- **Screen time is self-reported, screenshot-read, or automation-fed.** There is no OS-level enforcement or blocking (web-first by design).
- **One push endpoint per browser:** a browser shared between two accounts gets a clear 409 until the first account turns notifications off.
- **iOS** needs the PWA on the Home Screen for push, and has no lock-screen action buttons.
- **The chain tracer is deliberately simple** (four upstream signals). `unexplained_slips` is the honest "I can't see why."
- **Crisis-language detection is best-effort** (a safety net, not a clinical screen). Extend the pattern list, especially for other languages and slang.
- **Helplines are curated for India;** other regions get a generic fallback.
- **Complex calendar recurrences** (e.g. "second Tuesday") import their first occurrence only, and say so.

---

## 20. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| API won't start: `AUTH_MODE=hs256 requires SUPABASE_JWT_SECRET` | Set the secret, or use `AUTH_MODE=jwks` with `SUPABASE_JWKS_URL` |
| Browser shows a **CORS error** | `CORS_ALLOW_ORIGINS` must be a JSON list with the exact frontend origin, no trailing slash. Redeploy the API after changing it |
| Login screen says sign-in isn't configured | `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` were missing **at build time**. Set them and rebuild |
| Startup warns about schema drift / API errors about a missing column | A migration wasn't applied. Run 001 → 027 in order |
| Journals or chats won't decrypt | `FIELD_ENCRYPTION_KEY` changed. Restore the old key (or move it to `FIELD_ENCRYPTION_OLD_KEYS`) |
| Database connection errors behind a pooler | Use Supabase's pooler URL; the app already disables the asyncpg statement cache for it |
| No push notifications | Check VAPID keys on the API **and** cron jobs, that the three push jobs are scheduled, quiet hours and the daily cap in Settings, and (iOS) that the app is on the Home Screen |
| Action buttons on a push do nothing | Set `PUBLIC_API_URL` to the API's public origin |
| AI features answer with plain deterministic text | `GROQ_API_KEY` is empty, the model is down or over budget, or output failed validation. That's the safe fallback, not a bug |
| "You've used today's AI allowance" | Per-user daily cap hit (`LLM_DAILY_CALL_CAP`). Resets at 00:00 UTC |
| New signups see everything immediately | `UNLOCK_EPOCH` is later than your ship date |
| Old UI after a deploy | Close and reopen the app; the service worker fetches HTML network-first and purges old caches on activate |

---

## 21. Roadmap

- **Chrome extension (Manifest V3)** using `chrome.tabs` + `chrome.idle` for real per-domain screen time, replacing self-reported entry.
- **Redis-backed rate limiting** for multi-instance deployments.
- More helpline regions and crisis-language coverage.

---

## License

*Add your license here before publishing.*
