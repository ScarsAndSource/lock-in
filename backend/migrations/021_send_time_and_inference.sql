-- Lock'in — migration 021 (Agent C: adaptive send time). Idempotent. Run after 018 (needs companion_moments, events).
--
-- send_outcomes  one row per SENT companion moment, settled the day after it was sent:
--                acted = the person opened the app within the act window of the push.
--                The per-hour acted / ignored counts that drive send-time learning are a GROUP BY over this table,
--                so there is no counter to drift. No free text is stored here.

create table if not exists public.send_outcomes (
  user_id     uuid not null references auth.users(id) on delete cascade,
  kind        text not null check (kind in ('morning', 'evening')),
  moment_date date not null,
  hour        smallint not null check (hour between 0 and 23),
  acted       boolean not null,
  settled_at  timestamptz not null default now(),
  primary key (user_id, kind, moment_date)
);

alter table public.send_outcomes enable row level security;

drop policy if exists "send_outcomes_owner_all" on public.send_outcomes;
create policy "send_outcomes_owner_all"
  on public.send_outcomes
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

grant select, insert, update, delete on public.send_outcomes to authenticated;
