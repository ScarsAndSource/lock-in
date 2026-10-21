-- Lock'in — migration 018 (Phase 2: the companion spine)
-- Idempotent. Depends on 001 only for the auth.users reference.
--
-- events             small append-only log of how the person actually uses the app (opens, what the companion
--                    suggested, what they did with it). It feeds the rhythm model; nothing here is journal text.
-- companion_moments  one row per person per local day per moment ('morning' | 'evening'), so the companion
--                    never says the same thing twice in a day, even if the cron job runs every few minutes.

create table if not exists public.events (
  id      uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  ts      timestamptz not null default now(),
  kind    text not null check (kind in ('app_open', 'nba_shown', 'nba_acted', 'nba_skipped', 'push_opened')),
  ref     text check (ref is null or char_length(ref) <= 80),
  meta    jsonb not null default '{}'::jsonb
);

create index if not exists events_user_ts_idx on public.events (user_id, ts desc);

alter table public.events enable row level security;

drop policy if exists "events_owner_all" on public.events;
create policy "events_owner_all"
  on public.events
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

grant select, insert, update, delete on public.events to authenticated;

create table if not exists public.companion_moments (
  user_id     uuid not null references auth.users(id) on delete cascade,
  moment_date date not null,
  moment      text not null check (moment in ('morning', 'evening')),
  outcome     text not null check (outcome in ('sent', 'skipped')),
  created_at  timestamptz not null default now(),
  primary key (user_id, moment_date, moment)
);

alter table public.companion_moments enable row level security;

drop policy if exists "companion_moments_owner_all" on public.companion_moments;
create policy "companion_moments_owner_all"
  on public.companion_moments
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

grant select, insert, update, delete on public.companion_moments to authenticated;
