# Lock'in

Self-improvement tracker built around one real insight: every competitor in
this space tracks one domain (habits, or screen time, or urges) and treats a
missed day as a broken streak. Lock'in tracks the cross-domain chain and
never resets to zero on a miss. Full reasoning and data model: [SPEC.md](./SPEC.md).

## Build status

| Slice | Status |
|---|---|
| 1. Habit domain + unified daily check-in (opt-out defaults) | **Done** — `backend/` |
| 2. Frontend for slice 1 (PWA check-in screen) | Not started |
| 3. Sleep + screen-time domains | **Done** — `backend/` |
| 3b. Missions (goal-scoped sprints) | **Done** — `backend/` |
| 3c. Schedule service, consistency scoring, pattern detection, profile, account export/delete, rate limiting | **Done** — `backend/` |
| 4. Study domain (`subjects` table) | Next |
| 5. Urge domain (encrypted fields, quick-capture) | Next |
| 6. Implementation intentions | Next |
| 7. Groq pattern insights + check-in chat (crisis fallback required) | Next |
| 8. Weekly retrospective + insight feedback loop | **Done** — `backend/` |
| 9. Chain visualization | Next |
| 10. Phase 2: Chrome extension for real screen time | Post-v1 |

## Structure

```
lockin/
  SPEC.md              -- source of truth, read this first
  backend/             -- FastAPI app (backend slices 1, 3, 3b, 3c, 8 complete)
    app/
      domain.py         -- plain dataclasses, no DB dependency
      services/         -- business logic (defaults engine, consistency, chains, patterns, retros, insights)
      repositories/      -- DB access, isolated behind Protocol interfaces
      routers/           -- HTTP endpoints
      security.py         -- JWT verification + field-level encryption
    migrations/          -- raw SQL, run manually against Supabase
    tests/               -- 131 passing tests, see backend/README.md
  frontend/            -- not created yet (slice 2)
```

## Why backend-only so far
Slice 1 is genuinely finished and tested end-to-end (auth, ownership checks,
encryption-at-rest, the defaults algorithm's edge cases) via an in-memory
fake database. Building a UI on top of unverified business logic would mean
finding out about bugs in the defaulting algorithm through the UI instead of
through a test — backwards. Frontend is next, not skipped.

Read `backend/README.md` before deploying anything — it states plainly what
has and hasn't been verified against a real database.
