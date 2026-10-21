-- Lock'in — migration 019 (N-of-1 experiments)
-- Idempotent. Depends on 001 only for the auth.users reference.
--
-- experiments  one row per "test this change on me" run. The window is [start_date - baseline_days, start_date - 1]
--              as baseline and [start_date, start_date + treatment_days - 1] as the test. result freezes the verdict
--              when the run is finished; an abandoned run keeps no result. One active run per person.

create table if not exists public.experiments (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users(id) on delete cascade,
  title          text not null check (char_length(title) between 1 and 120),
  change_text    text not null check (char_length(change_text) between 1 and 200),
  metric         text not null check (metric in ('sleep_hours', 'screen_minutes', 'mood', 'habit_ratio', 'task_rate')),
  direction      text not null check (direction in ('higher', 'lower')),
  baseline_days  smallint not null default 14 check (baseline_days between 7 and 30),
  treatment_days smallint not null default 7 check (treatment_days between 5 and 21),
  start_date     date not null,
  status         text not null default 'active' check (status in ('active', 'done', 'abandoned')),
  result         jsonb,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create index if not exists experiments_user_start_idx on public.experiments (user_id, start_date desc);

create unique index if not exists experiments_one_active_idx
  on public.experiments (user_id)
  where status = 'active';

alter table public.experiments enable row level security;

drop policy if exists "experiments_owner_all" on public.experiments;
create policy "experiments_owner_all"
  on public.experiments
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

grant select, insert, update, delete on public.experiments to authenticated;
