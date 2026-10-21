-- Lock'in — migration 016: companion pushes (habit / check-in / risk-window / wind-down / study), actionable
-- push ledger, and the new notification preferences. Idempotent. Run after 015.
-- Depends on 013 (notification_prefs, set_updated_at).

-- ------------------------------------------------------------
-- 1. notification_prefs: companion controls
--    checkin_hour        local hour the evening "Does today look normal?" push may start
--    companion_enabled   master switch for everything that is not a task reminder
--    plan_cues_in_quiet  let the person's OWN if-then plans through quiet hours (off by default:
--                        quiet hours still win unless the person opts in)
--    discreet_push       lock-screen text for urge-related pushes stays neutral ("Your plan")
-- ------------------------------------------------------------
alter table public.notification_prefs
  add column if not exists companion_enabled boolean  not null default true,
  add column if not exists checkin_hour      smallint not null default 21,
  add column if not exists plan_cues_in_quiet boolean not null default false,
  add column if not exists discreet_push     boolean  not null default true;

alter table public.notification_prefs drop constraint if exists notification_prefs_checkin_hour_check;
alter table public.notification_prefs
  add constraint notification_prefs_checkin_hour_check check (checkin_hour between 0 and 23);

-- ------------------------------------------------------------
-- 2. companion_pushes: one row per actionable push that was SENT.
--    * (user_id, key) is unique  -> the same moment can never push twice, even if two cron runs overlap
--    * id is the single-use handle inside a signed action token -> acted_at is set exactly once
--    * acted/ignored history is what the anti-nag backoff reads
--    No free text is stored here, ever.
-- ------------------------------------------------------------
create table if not exists public.companion_pushes (
  id         uuid primary key,
  user_id    uuid not null references auth.users(id) on delete cascade,
  kind       text not null check (char_length(kind) between 1 and 32),
  key        text not null check (char_length(key) between 1 and 120),
  local_date date not null,
  sent_at    timestamptz not null default now(),
  acted_at   timestamptz,
  action     text check (action is null or char_length(action) <= 32),
  constraint companion_pushes_user_key unique (user_id, key)
);

create index if not exists companion_pushes_user_sent_idx on public.companion_pushes (user_id, sent_at desc);

alter table public.companion_pushes enable row level security;

drop policy if exists "companion_pushes_owner_all" on public.companion_pushes;
create policy "companion_pushes_owner_all"
  on public.companion_pushes
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

grant select, insert, update, delete on public.companion_pushes to authenticated;
