-- Lock'in — migration 002
-- Scope: slice 3 only (sleep + screen-time domains).
-- Depends on 001_init_habit_and_checkin.sql having already run: reuses its
-- pgcrypto extension and set_updated_at() trigger function rather than
-- redefining either.
--
-- study, urge, implementation_intentions, goals, and pattern_insights
-- tables are still NOT created here -- they land in their own slices, per
-- SPEC.md section 12's build order.

-- ============================================================
-- sleep_logs
-- One row per user per date (the date attributed = wake date, see
-- app/domain.py SleepLog docstring -- this is an application-layer
-- convention, not something the DB enforces or needs to know about).
-- Manual entry only in v1 (SPEC.md section 6) -- no source column, unlike
-- screen_time_logs, since there's only one way this data enters the
-- system right now.
-- ============================================================
create table if not exists public.sleep_logs (
  id                 uuid primary key default gen_random_uuid(),
  user_id            uuid not null references auth.users(id) on delete cascade,
  log_date           date not null,
  time_to_bed        time,
  time_woke          time,
  self_rated_quality smallint check (self_rated_quality between 1 and 5),
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (user_id, log_date)
);

create index if not exists sleep_logs_user_date_idx
  on public.sleep_logs (user_id, log_date);

alter table public.sleep_logs enable row level security;

drop policy if exists "sleep_logs_owner_all" on public.sleep_logs;
create policy "sleep_logs_owner_all"
  on public.sleep_logs
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create trigger sleep_logs_set_updated_at
  before update on public.sleep_logs
  for each row execute function set_updated_at();

-- ============================================================
-- screen_time_logs
-- category_breakdown is optional jsonb (e.g. {"social": 90, "other": 30})
-- per SPEC.md section 6 -- self-reported totals are the v1 floor, a
-- breakdown is a bonus when the user bothers to give one. source exists
-- now specifically so the Phase 2 Chrome extension (SPEC.md section 7)
-- can write 'extension' rows into the exact same table later without a
-- schema change -- not used by anything in this slice yet.
-- ============================================================
create table if not exists public.screen_time_logs (
  id                 uuid primary key default gen_random_uuid(),
  user_id            uuid not null references auth.users(id) on delete cascade,
  log_date           date not null,
  total_minutes      integer not null check (total_minutes >= 0),
  source             text not null default 'manual' check (source in ('manual', 'extension')),
  category_breakdown jsonb,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (user_id, log_date)
);

create index if not exists screen_time_logs_user_date_idx
  on public.screen_time_logs (user_id, log_date);

alter table public.screen_time_logs enable row level security;

drop policy if exists "screen_time_logs_owner_all" on public.screen_time_logs;
create policy "screen_time_logs_owner_all"
  on public.screen_time_logs
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create trigger screen_time_logs_set_updated_at
  before update on public.screen_time_logs
  for each row execute function set_updated_at();
