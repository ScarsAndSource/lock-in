-- Lock'in — migration 003
-- Depends on 001 + 002. Safe to re-run (idempotent).

-- 1) Auto-filled sleep/screen rows are marked so pattern math can ignore them.
alter table public.sleep_logs
  add column if not exists is_default boolean not null default false;
alter table public.screen_time_logs
  add column if not exists is_default boolean not null default false;

-- 2) Missions: the time-boxed "become your best in N days" container.
create table if not exists public.missions (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  title      text not null check (char_length(trim(title)) between 1 and 120),
  start_date date not null,
  end_date   date not null,
  status     text not null default 'active'
               check (status in ('active', 'completed', 'ended_early')),
  ended_at   timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (end_date >= start_date),
  check ((end_date - start_date) between 6 and 364)   -- 7..365 days inclusive
);

-- At most one active mission per user, enforced by the database, not just app code.
create unique index if not exists missions_one_active_per_user
  on public.missions (user_id) where status = 'active';
create index if not exists missions_user_start_idx
  on public.missions (user_id, start_date desc);

alter table public.missions enable row level security;

drop policy if exists "missions_owner_all" on public.missions;
create policy "missions_owner_all"
  on public.missions
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop trigger if exists missions_set_updated_at on public.missions;
create trigger missions_set_updated_at
  before update on public.missions
  for each row execute function set_updated_at();

-- 3) The backend now runs each request as the `authenticated` role so RLS is
--    actually enforced (see app/db.py). That role needs table privileges;
--    RLS policies still decide which ROWS it can touch.
grant usage on schema public to authenticated;
grant select, insert, update, delete on
  public.profiles, public.habit_definitions, public.habit_logs,
  public.daily_checkins, public.sleep_logs, public.screen_time_logs,
  public.missions
to authenticated;
