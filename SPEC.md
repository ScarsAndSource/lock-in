# SPEC.md — Lock'in (v1, locked for build)

## Changelog — this pass
- All four open questions from the previous version's Section 9 resolved — see new **Section 9: Decisions**.
- Study tracking gets a real per-user `subjects` table instead of free text, designed around the fact that friends using this in v1 will have completely different courses than you do — see Section 6 and Section 9.
- Five low-friction additions folded in, each flagged with a short rationale — see **Section 10**.
- New **Section 11: Voice & Tone Ceiling** — a concrete, opinionated spec for how the LLM layer is allowed to talk to the user, since "decide yourself" was the answer to Section 9's tone question and that deserves a real design, not a shrug.
- This version is ready for Phase 5 — implementation. Build order is at the bottom (Section 12).

---

## 1. Problem statement (one sentence)
People trying to actually change their life are running 3-4 disconnected tools
(a habit tracker, a screen-time blocker, a NoFap counter, a notes app for
studying) that don't talk to each other, treat every missed day as total
failure, and can't see the real chain of cause-and-effect in their own
behavior — so they quietly abandon all of it within a few weeks.

## 2. Target user
Vib and his immediate circle (Her Campus / LITMUS / Cyber Space Club) first —
students, ~18-24, juggling gym/discipline goals, screen-time/focus problems,
urge control (NoFap-adjacent), and academic performance simultaneously.
Blunt, no-fluff, "lock tf in" tone — not a gentle wellness-app voice.

Not building for a general consumer market yet. Multi-user from day one
(friends will test it), but each account is a fully isolated island — this is
explicitly **not** a social product.

## 3. Core insight driving the design
Every competitor in this space (researched: Streaks, Habitica, Rewire,
Unrot/FitRot, Brain Reboot, NoFap trackers, and the existing "LOCK IN: Brain
Cortex Reset" app) does **one slice** — habits OR screen time OR urge/relapse
OR journaling — and treats a missed day as a broken streak, which triggers
shame → avoidance → total abandonment (this is a documented failure mode, not
a guess).

Lock'in's bet: one unified daily check-in across all domains, with an LLM
layer that finds cross-domain patterns a human wouldn't manually connect
(e.g. "last 3 times you skipped the gym, you'd also been on your phone past
1am the night before") — and a continuity model that never resets to zero on
a single miss.

## 4. Core workflows (v1)
1. **Unified daily check-in** — one screen, not four apps. Defaults to
   "everything on track" based on the user's own declared baseline per
   domain; the user only touches what's *different* today (see Section 10,
   item 1 — this replaced the original "fill every field" design). Fields
   when something needs detail: habits done/skipped, screen time
   (self-reported or extension-fed), study session (subject, planned vs
   actual duration), urge/trigger log (optional, intensity 1-10, context,
   coping strategy tried, outcome), free-text journal note.
2. **Domain dashboards** — habits, focus/screen-time, urges, study — each
   shows a rolling consistency view (NOT a streak counter that hits zero on
   one miss — see data model), plus the chain visualization added in
   Section 10, item 2.
3. **Pattern insight feed** — LLM-generated, runs on a schedule (not live per
   keystroke), surfaces correlations across domains from stored logs.
   Narrated per the Voice & Tone Ceiling in Section 11, never shaming. Each
   insight is now rateable by the user — see Section 10, item 5.
4. **Check-in chat** — a lightweight conversational mode where the user can
   ask "why do I keep failing at X" and get an answer grounded in their own
   logged data, not generic advice. Same tone ceiling as the insight feed.
5. **Goal setting** — user defines what "locked in" means per domain
   (e.g. gym 5x/week, <2hrs non-essential screen time, 90-day streak-free
   urge control, X hours studied/week). This also seeds the daily check-in's
   defaults from item 1.
6. **If-then pre-commitments** — user sets specific cue→action plans against
   a habit, urge, study session, or sleep routine (widened from
   habit/urge-only — see Section 10, item 3). Distinct from a reminder — the
   app surfaces the cue when relevant, doesn't just nag on a timer.
7. **Weekly retrospective** — an LLM-generated weekly summary pulling
   together the week's cross-domain pattern, framed as "here's the chain
   that actually happened," not a generic recap. Now includes a prompt to
   rate the *previous* week's insights (Section 10, item 5), closing the
   feedback loop before generating new ones.
8. **Urge quick-capture** — new, added this pass. See Section 10, item 4.

## 5. Explicit non-goals (v1)
- No social features, leaderboards, or friend comparison — the user
  explicitly rejected this.
- No OS-level app blocking (Screen Time API is iOS-native; this is web-first,
  so screen time is self-reported or browser-extension-fed, not enforced).
- No cheap gamification currency ("earn minutes by doing pushups") — this is
  the "generic reward system" the user explicitly wants to avoid.
- No streak-reset-to-zero shame mechanic.
- No claim to replace therapy or clinical addiction treatment — Lock'in is a
  tracking/insight tool, not a treatment.
- (Holding the line here on purpose: everything added in Section 10 was
  checked against this list before being folded in. None of it is a social
  feature, a points system, or a reset-based streak — if it had been, it
  would be flagged as rejected, not added.)

## 6. Data model (updated)
- `users` — id, email, created_at, timezone, tone_preference (locked to
  "direct" for v1, extensible later — see Section 11 for what that means in
  practice)
- `domains` — enum: habit, screen_time, urge, study, sleep
- `habit_definitions` — user_id, name, target_frequency, created_at, archived_at
- `habit_logs` — habit_id, date, status (done/skipped/partial), note
- `screen_time_logs` — user_id, date, total_minutes, source (manual/extension),
  category_breakdown (optional)
- **`subjects`** — *new table, replaces free-text subject entry.* id,
  user_id, name, archived_at, created_at. Per-user and empty by default for
  every new account — it is not seeded from any one person's course list,
  because friends using this in v1 are in different programs entirely (see
  Section 9, Decision 1). Created inline from the check-in flow or in a
  one-time bulk add at onboarding.
- `study_sessions` — user_id, date, `subject_id` (FK → subjects.id, was a
  free-text field), planned_minutes, actual_minutes
- `urge_logs` — user_id, timestamp, intensity (1-10), trigger_context (free
  text), coping_strategy_used, outcome (resisted/relapsed), note.
  `trigger_context` and `note` are field-level encrypted, not just RLS-
  isolated — this is the most sensitive table in the schema.
- `sleep_logs` — user_id, date, time_to_bed, time_woke, self_rated_quality
  (1-5). Manual entry v1; wearable/HealthKit-style integration is a later
  option, not v1.
- `implementation_intentions` — user_id, linked_domain (now genuinely
  supports all five domains, not just habit/urge), `linked_entity_id`
  (nullable, renamed from `linked_habit_or_urge_id` to reflect the
  widened scope — see Section 10, item 3), cue, action, active, created_at.
- `daily_checkins` — user_id, date, links to that day's logs across domains,
  free_text_journal (field-level encrypted), plus `defaults_applied` (json)
  recording which fields were auto-filled vs. manually touched that day —
  cheap to add now, useful later for tuning how good the defaults actually
  are.
- `pattern_insights` — user_id, generated_at, insight_text, source_domains
  (array), evidence_refs (which logs it's based on), **`user_feedback`**
  (new — enum: accurate / not_quite / unsure, nullable until rated) —
  generated async, not regenerated per page load.
- `goals` — user_id, domain, definition, target, created_at, status

Consistency model: replace "current streak" with a **rolling N-day
consistency %** plus a separate "longest run" stat kept for reference only —
a single miss dents the rolling percentage, it doesn't zero out a counter.

Reminder design principle: research on implementation intentions (Gollwitzer
1999; multiple follow-up studies) found reminders can *undermine* long-term
habit automaticity — people learn to wait for the nag instead of responding
to their own cue. Reminder frequency should therefore **fade as an
`implementation_intention`'s linked behavior gets more consistent**, not run
at a fixed cadence forever.

## 7. Tech stack
- Backend: FastAPI
- LLM: Groq (pattern narration + check-in chat, per the Voice & Tone Ceiling
  in Section 11)
- DB/Auth: Supabase (Postgres + built-in auth, RLS on every table — treat the
  security checklist from earlier as a hard gate per slice, not a
  once-at-the-end audit, especially given `urge_logs` and
  `daily_checkins.free_text_journal` are the most sensitive tables here)
- Frontend: React + TypeScript, built as an installable PWA (manifest +
  service worker, offline-cached check-in form that syncs when back online),
  now also using the manifest `shortcuts` field for urge quick-capture
  (Section 10, item 4)
- Notifications: **web push, confirmed for v1** (Section 9, Decision 3). One
  caveat worth knowing going in: iOS requires the PWA to be added to the
  home screen before it can grant push permission — worth a one-time
  onboarding nudge ("add this to your home screen to get reminders"),
  not something to discover after the fact.
- Deploy: Vercel (frontend) / Render (backend)
- Phase 2 (post-v1, not blocking): a Manifest V3 Chrome extension using
  `chrome.tabs` + `chrome.idle` for real per-domain active-tab screen time,
  syncing to the backend — confirmed technically feasible, replaces the
  self-reported screen-time entry once the core app is proven out.

## 8. Edge cases (must handle explicitly, not silently)
- **User misses many days in a row**: no punitive reset, no escalating guilt
  notifications. Rolling consistency % just reflects reality.
- **Malicious/injection input**: journal text and chat input feed directly
  into LLM prompts — must be sanitized/isolated as data, not concatenated
  raw into system-level prompt context, to prevent prompt injection via a
  user's own journal entry.
- **Crisis content in journal/chat**: if a check-in or chat message contains
  language indicating real self-harm risk (not just "I relapsed on my
  habit"), the LLM coaching layer must NOT respond with more "push harder"
  coaching — it needs a hard-coded fallback path that surfaces real support
  resources instead of an AI-generated pep talk. This is a hard requirement,
  not a nice-to-have.
- **A default gets it wrong**: since Section 10's opt-out check-in assumes
  "same as usual" unless corrected, there needs to be a one-tap way to
  correct a wrongly-applied default *after the fact*, not just before —
  otherwise a bad assumption silently pollutes the data it's supposed to
  make trustworthy.
- **Urge quick-capture with no detail**: a 2-tap "resisted/relapsed" log with
  no intensity/trigger/coping data must still be a fully valid log, not a
  draft waiting to be completed. Prompting for the missing detail later is
  fine; blocking on it in the moment defeats the point of adding this at all.
- **No screen-time ground truth on web**: self-reported data can be lied to.
  Spec accepts this limitation for v1 — the Phase 2 extension (Section 7)
  is the real fix, not a v1 blocker.
- **LLM produces a wrong/unsupported correlation**: insights must cite which
  logged entries they're based on (evidence_refs), and the user can now flag
  it directly (`user_feedback` — Section 10, item 5) rather than the app
  just hoping the insight was right.

## 9. Decisions (previously open questions — now resolved)

**Decision 1 — Study tracking linkage.** Yes, study sessions get a real
named subject, not a generic "studied for X minutes." But the subject list
is **not** hardcoded to any one person's actual courses (ADS, AISC, CN,
Predictive Analytics, etc.) — this is multi-user from day one, and your
friends are in different programs with completely different subjects. So:
`subjects` is its own per-user table (Section 6), empty by default, with
frictionless inline creation from the check-in screen itself — type a
subject that doesn't exist yet, get an inline "+ Create '[name]'", no
settings screen, no required fields beyond the name. A one-time bulk-add at
onboarding (paste a comma-separated list) covers the "I have eight subjects
right now and don't want to add them one at a time" case for everyone,
including you.

**Decision 2 — Chat/insight tone ceiling.** Delegated to me — decided.
Direct-accountability, not drill-sergeant, not shame. Full spec in Section
11. Short version: blunt about the *pattern in the data*, never about the
person's worth, and every callout comes with a next step, not a bare
observation.

**Decision 3 — Notification channel.** Confirmed: web push via the PWA for
v1. See the iOS caveat under Section 7.

**Decision 4 — Data export/delete.** Confirmed: self-service export/delete
in settings, as originally planned. No change.

## 10. Low-friction enhancements adopted this pass
Each of these was checked against Section 5's non-goals before being folded
in — none of them are a social feature, a points system, or a reset-based
streak. If you want to cut any of them, they're independent of each other
and of the core spec, so cutting one doesn't unravel anything else.

1. **Opt-out daily check-in.** The original design implied filling in every
   field, every day. For a consistency tool, the check-in itself is the
   single highest-friction moment — if it takes real effort daily, this
   becomes exactly the kind of tool people quietly abandon, per the
   product's own problem statement. New design: the check-in defaults to
   "same as usual" per domain based on the user's declared goals, and the
   user only touches what's different. Most days become a ~10-second
   confirmation instead of a form.
2. **Chain visualization.** The product's whole pitch is surfacing a real
   cause-and-effect chain ("bad sleep → screen spike → skipped gym"). Right
   now that claim only exists as text. Adding a compact horizontal strip —
   one dot per domain per day, color-coded, last 7-14 days — so the chain an
   insight describes is something the user can actually see lining up, not
   just take on faith. Directly strengthens the evidence_refs/falsifiability
   idea already in Section 8.
3. **Implementation intentions widened to study and sleep.** The original
   schema tied if-then plans to habit/urge only, but study procrastination
   is one of the most common places this exact mechanism helps ("if I open
   Instagram during a study block, then I close the laptop for 2 minutes and
   write down why"). Same evidence base (Gollwitzer), no new mechanic
   introduced — just not artificially restricting where an already-designed,
   already-justified feature can apply.
4. **Urge quick-capture.** The moment someone is mid-urge is the worst
   possible moment to hand them a 5-field form. Added a genuine 2-tap
   capture via a PWA home-screen shortcut: tap → "resisted" or "relapsed" →
   done. Everything else becomes an optional add-later prompt, not a
   blocker. An imperfect log beats no log because the form was too much at
   1am.
5. **Insight feedback loop.** Added a lightweight "was this actually right?"
   (accurate / not quite / unsure) on each surfaced pattern, folded into the
   weekly retro. This turns Section 8's falsifiability principle into an
   actual mechanism instead of a nice idea, and gives you real signal on
   whether the Groq-generated insights are earning trust — worth having
   before this goes past your friend group, not after.

## 11. Voice & Tone Ceiling (Groq prompts — insight feed + chat)
This was left to my judgment, so here's the actual design, not a punt.

**Does:**
- States the pattern the data shows, plainly, second person: "You skipped
  gym 4 of the last 5 days when you slept under 5 hours the night before."
- Treats a miss as data, not a verdict — every callout pairs with a concrete
  next step, never left as a bare observation.
- Matches the "lock in" register already chosen for the brand — clipped, no
  wellness-app cushioning, no exclamation-point cheerfulness.
- When a pattern repeats, gets more *specific* about the mechanism, not
  louder or angrier.

**Never:**
- No identity-level language — "you're lazy," "you always fail," anything
  that targets the person rather than the behavior. Shame-based framing is
  well-documented to increase avoidance rather than fix the behavior — it's
  the exact shame → avoidance loop this whole product exists to break, so
  putting it in the LLM's own voice would undercut the product's thesis.
- No manufactured urgency or guilt trips, and no holding up the user's own
  best days as a gotcha.
- No hedging or apologizing before stating a hard truth ("I hate to say
  this, but…") — say it straight, then move to the fix.

**Implementation note:** don't bury this as loose prose inside one big
prompt string. Keep it as a small versioned `voice_config` — a short
system-prompt fragment plus 4-5 worked before/after phrasing examples for
the same underlying data — that both the insight-generation job and the
check-in chat reference. That way the tone can be tuned from real output
later without touching app logic.

## 12. What's next
Ready for Phase 5. Build order, following the plan-then-slice approach from
earlier: start with the unified daily check-in (now with opt-out defaults)
plus the habit domain, since sleep, screen-time, study (with the new
`subjects` table), and urge all hang off that same entry flow. Ship that one
slice end-to-end — including RLS on every table it touches, field-level
encryption where it applies, and rate limits on anything that calls Groq —
before starting the next one. Run the security checklist against each slice
as you go, not once at the end; the earlier point about "friends now, public
later" using the exact same code path still applies here.
