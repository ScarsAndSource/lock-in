-- Lock'in — migration 013: tasks, notification prefs, push subscriptions (slice 11).
-- Also widens llm_usage.feature so the task-capture AI call ('tasks') and media calls ('media') can be metered.
-- Idempotent. Run after 012 and before 014. Depends on 001 (set_updated_at) and 009 (llm_usage).

-- ------------------------------------------------------------
-- 1. llm_usage.feature: 'tasks' (AI task capture) and 'media' (voice / screenshot parsing)
-- ------------------------------------------------------------
alter table public.llm_usage drop constraint if exists llm_usage_feature_check;
alter table public.llm_usage
  add constraint llm_usage_feature_check
  check (feature in ('chat', 'retro', 'insight', 'tasks', 'media'));

-- ------------------------------------------------------------
-- 2. tasks
--    importance: 1 small chore, 2 normal, 3 real deadline.
--    due_has_time = false means a date only (due_at is that day 23:59 local).
--    repeat_days counts from COMPLETION, never from a fixed calendar slot.
-- ------------------------------------------------------------
create table if not exists public.tasks (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users(id) on delete cascade,
  title          text not null check (char_length(title) between 1 and 200),
  notes          text check (notes is null or char_length(notes) <= 500),
  source_text    text,
  importance     smallint not null default 2 check (importance between 1 and 3),
  status         text not null default 'open' check (status in ('open', 'done', 'dropped')),
  due_at         timestamptz,
  due_has_time   boolean not null default true,
  remind_at      timestamptz,
  repeat_days    smallint check (repeat_days is null or repeat_days between 1 and 365),
  snoozed_until  timestamptz,
  nudge_count    smallint not null default 0 check (nudge_count >= 0),
  last_nudged_at timestamptz,
  last_done_at   timestamptz,
  done_count     integer not null default 0 check (done_count >= 0),
  completed_at   timestamptz,
  ai_parsed      boolean not null default false,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create index if not exists tasks_user_status_idx on public.tasks (user_id, status, created_at desc);
-- the nudge job scans open tasks that carry a due time or a reminder
create index if not exists tasks_open_triggers_idx on public.tasks (user_id)
  where status = 'open' and (due_at is not null or remind_at is not null);

alter table public.tasks enable row level security;

drop policy if exists "tasks_owner_all" on public.tasks;
create policy "tasks_owner_all"
  on public.tasks
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop trigger if exists tasks_set_updated_at on public.tasks;
create trigger tasks_set_updated_at
  before update on public.tasks
  for each row execute function set_updated_at();

grant select, insert, update, delete on public.tasks to authenticated;

-- ------------------------------------------------------------
-- 3. notification_prefs: one row per user (no row = app defaults)
-- ------------------------------------------------------------
create table if not exists public.notification_prefs (
  user_id         uuid primary key references auth.users(id) on delete cascade,
  push_enabled    boolean not null default true,
  quiet_start     time not null default '22:00',
  quiet_end       time not null default '08:00',
  nudge_hour      smallint not null default 18 check (nudge_hour between 0 and 23),
  max_per_day     smallint not null default 4 check (max_per_day between 1 and 20),
  pushes_sent_day date,
  pushes_sent     smallint not null default 0 check (pushes_sent >= 0),
  updated_at      timestamptz not null default now()
);

alter table public.notification_prefs enable row level security;

drop policy if exists "notification_prefs_owner_all" on public.notification_prefs;
create policy "notification_prefs_owner_all"
  on public.notification_prefs
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop trigger if exists notification_prefs_set_updated_at on public.notification_prefs;
create trigger notification_prefs_set_updated_at
  before update on public.notification_prefs
  for each row execute function set_updated_at();

grant select, insert, update, delete on public.notification_prefs to authenticated;

-- ------------------------------------------------------------
-- 4. push_subscriptions: one row per browser endpoint.
--    The unique endpoint + RLS means another account cannot take over a registered browser
--    (the upsert fails and the API reports a conflict).
-- ------------------------------------------------------------
create table if not exists public.push_subscriptions (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  endpoint    text not null,
  p256dh      text not null,
  auth        text not null,
  user_agent  text,
  fail_count  smallint not null default 0 check (fail_count >= 0),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint push_subscriptions_endpoint_key unique (endpoint)
);

create index if not exists push_subscriptions_user_idx on public.push_subscriptions (user_id);

alter table public.push_subscriptions enable row level security;

drop policy if exists "push_subscriptions_owner_all" on public.push_subscriptions;
create policy "push_subscriptions_owner_all"
  on public.push_subscriptions
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop trigger if exists push_subscriptions_set_updated_at on public.push_subscriptions;
create trigger push_subscriptions_set_updated_at
  before update on public.push_subscriptions
  for each row execute function set_updated_at();

grant select, insert, update, delete on public.push_subscriptions to authenticated;
