-- Lock'in — migration 015 (Batch B: mood in two taps, screenshot screen time)
-- Idempotent. Depends on 001 (set_updated_at) and 014 only for ordering convenience.
-- If your repo already has a 015, rename this file to the next free number.

-- ------------------------------------------------------------
-- 1. mood_logs: one row per user per day, two 1-5 taps (how it felt, how much energy).
--    Mood is the missing variable in almost every pattern engine; for now it is only collected.
-- ------------------------------------------------------------
create table if not exists public.mood_logs (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  log_date   date not null,
  valence    smallint not null check (valence between 1 and 5),
  energy     smallint not null check (energy between 1 and 5),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, log_date)
);

create index if not exists mood_logs_user_date_idx on public.mood_logs (user_id, log_date);

alter table public.mood_logs enable row level security;

drop policy if exists "mood_logs_owner_all" on public.mood_logs;
create policy "mood_logs_owner_all"
  on public.mood_logs
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop trigger if exists mood_logs_set_updated_at on public.mood_logs;
create trigger mood_logs_set_updated_at
  before update on public.mood_logs
  for each row execute function set_updated_at();

grant select, insert, update, delete on public.mood_logs to authenticated;

-- ------------------------------------------------------------
-- 2. screen_time_logs.source gains 'screenshot' (numbers read from a Digital Wellbeing /
--    Screen Time screenshot, confirmed by the user before saving).
-- ------------------------------------------------------------
alter table public.screen_time_logs drop constraint if exists screen_time_logs_source_check;
alter table public.screen_time_logs
  add constraint screen_time_logs_source_check
  check (source in ('manual', 'extension', 'screenshot'));
