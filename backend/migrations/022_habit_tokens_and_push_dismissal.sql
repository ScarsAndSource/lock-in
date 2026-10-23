-- Lock'in — migration 022: habit-bound ingest tokens + push dismissal. Idempotent. Run after 021.
-- Depends on 001 (habit_definitions), 016 (companion_pushes), 017 (ingest_tokens).
--
-- ingest_tokens.habit_id    NULL  = the usual write-only sleep / screen-time automation key.
--                           set   = a key that can do exactly ONE thing: mark that one habit done for today
--                                   (an iPhone/Android "arrive at gym" or "Focus on" automation). It cannot touch
--                                   sleep, screen time, any other habit, or read anything back.
-- companion_pushes.dismissed_at  the person swiped the notification away without acting. The anti-nag backoff
--                           treats that as "ignored" at once instead of waiting out the 3 h grace.

alter table public.ingest_tokens
  add column if not exists habit_id uuid references public.habit_definitions(id) on delete cascade;

create index if not exists ingest_tokens_habit_idx on public.ingest_tokens (habit_id) where habit_id is not null;

alter table public.companion_pushes
  add column if not exists dismissed_at timestamptz;
