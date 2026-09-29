-- Lock'in — migration 001
-- Scope: slice 1 only (habit domain + unified daily check-in).
-- Sleep, screen_time, study, urge, implementation_intentions, goals, and
-- pattern_insights tables are NOT created here — they land in their own
-- slices, per the vertical-slice build order in SPEC.md section 12.
--
-- Every table in this migration has RLS enabled AND a policy attached in
-- the same statement block. A table with RLS enabled but no policy denies
-- all access by default in Postgres — that's the safe failure direction,
-- but it's still called out explicitly below so a future migration can't
-- silently forget the policy while remembering the ALTER TABLE.

-- ============================================================
-- Extensions
-- ============================================================
create extension if not exists "pgcrypto";

-- ============================================================
-- updated_at trigger helper (reused by every table below)
-- ============================================================
create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ============================================================
-- profiles
-- Extends Supabase's auth.users (id, email already live there — we do not
-- duplicate them). One row per user, created on first authenticated
-- request by the backend (see app/repositories/profile_repo.py), not via
-- a DB trigger, so the app can control defaults explicitly.
-- ============================================================
create table if not exists public.profiles (
  id              uuid primary key references auth.users(id) on delete cascade,
  timezone        text not null default 'UTC',
  tone_preference text not null default 'direct'
                    check (tone_preference in ('direct')),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists "profiles_owner_all" on public.profiles;
create policy "profiles_owner_all"
  on public.profiles
  for all
  using (auth.uid() = id)
  with check (auth.uid() = id);

create trigger profiles_set_updated_at
  before update on public.profiles
  for each row execute function set_updated_at();

-- ============================================================
-- habit_definitions
-- target_frequency is structured, not free text, so the defaults engine
-- (app/services/defaults_service.py) can reason about it:
--   {"type": "weekdays", "days": [0,2,4]}   -- Mon/Wed/Fri (0=Mon)
--   {"type": "n_per_week", "count": 5}      -- any 5 days, unspecified which
-- Both shapes are validated at the Pydantic layer, not just trusted here.
-- ============================================================
create table if not exists public.habit_definitions (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references auth.users(id) on delete cascade,
  name             text not null check (char_length(trim(name)) > 0),
  target_frequency jsonb not null,
  archived_at      timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create index if not exists habit_definitions_user_active_idx
  on public.habit_definitions (user_id)
  where archived_at is null;

alter table public.habit_definitions enable row level security;

drop policy if exists "habit_definitions_owner_all" on public.habit_definitions;
create policy "habit_definitions_owner_all"
  on public.habit_definitions
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create trigger habit_definitions_set_updated_at
  before update on public.habit_definitions
  for each row execute function set_updated_at();

-- ============================================================
-- habit_logs
-- One row per habit per date. Unique constraint means "log for today"
-- is an upsert, not an insert-and-hope — this matters because the
-- opt-out check-in flow calls this repeatedly as the user corrects
-- defaults, not just once.
-- ============================================================
create table if not exists public.habit_logs (
  id          uuid primary key default gen_random_uuid(),
  habit_id    uuid not null references public.habit_definitions(id) on delete cascade,
  user_id     uuid not null references auth.users(id) on delete cascade,
  log_date    date not null,
  status      text not null check (status in ('done', 'skipped', 'partial')),
  note        text,
  is_default  boolean not null default false,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (habit_id, log_date)
);

-- user_id is denormalized onto habit_logs (rather than joining through
-- habit_definitions for every RLS check) deliberately: it lets the RLS
-- policy below be a single indexed equality check instead of a subquery
-- against habit_definitions on every row, which matters once a user has
-- months of logs. It's kept in sync at the application layer — the
-- repository always writes user_id from the authenticated session, never
-- from client input, so there's no path for it to drift from the parent
-- habit's owner.
create index if not exists habit_logs_user_date_idx
  on public.habit_logs (user_id, log_date);

alter table public.habit_logs enable row level security;

drop policy if exists "habit_logs_owner_all" on public.habit_logs;
create policy "habit_logs_owner_all"
  on public.habit_logs
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create trigger habit_logs_set_updated_at
  before update on public.habit_logs
  for each row execute function set_updated_at();

-- ============================================================
-- daily_checkins
-- One row per user per date — the anchor record for "today's check-in is
-- confirmed," independent of how many domain logs exist for that date.
-- free_text_journal is stored as raw encrypted bytes (Fernet, app-layer
-- encryption — see app/security.py) rather than pgcrypto, so the
-- decryption key never has to live in the database itself. Postgres only
-- ever sees ciphertext.
-- ============================================================
create table if not exists public.daily_checkins (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references auth.users(id) on delete cascade,
  checkin_date      date not null,
  journal_encrypted bytea,
  defaults_applied  jsonb not null default '{}'::jsonb,
  confirmed_at      timestamptz,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (user_id, checkin_date)
);

create index if not exists daily_checkins_user_date_idx
  on public.daily_checkins (user_id, checkin_date);

alter table public.daily_checkins enable row level security;

drop policy if exists "daily_checkins_owner_all" on public.daily_checkins;
create policy "daily_checkins_owner_all"
  on public.daily_checkins
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create trigger daily_checkins_set_updated_at
  before update on public.daily_checkins
  for each row execute function set_updated_at();
