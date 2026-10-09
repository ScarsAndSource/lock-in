-- Lock'in — migration 006: goals + implementation intentions (if-then plans). Idempotent.

create table if not exists public.goals (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  domain     text not null check (domain in ('habit', 'screen_time', 'urge', 'study', 'sleep')),
  definition text not null check (char_length(trim(definition)) between 1 and 200),
  target     jsonb not null,    -- shape depends on domain; validated in app (services/goal_targets.py)
  status     text not null default 'active' check (status in ('active', 'paused', 'achieved', 'archived')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists goals_user_status_idx on public.goals (user_id, status);

create table if not exists public.implementation_intentions (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references auth.users(id) on delete cascade,
  linked_domain    text not null check (linked_domain in ('habit', 'screen_time', 'urge', 'study', 'sleep')),
  linked_entity_id uuid,        -- habit id or subject id; null = whole domain. Ownership checked in app.
  cue              text not null check (char_length(trim(cue)) between 1 and 200),
  action           text not null check (char_length(trim(action)) between 1 and 200),
  active           boolean not null default true,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create index if not exists intentions_user_active_idx on public.implementation_intentions (user_id, active);

alter table public.goals enable row level security;
drop policy if exists "goals_owner_all" on public.goals;
create policy "goals_owner_all" on public.goals
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop trigger if exists goals_set_updated_at on public.goals;
create trigger goals_set_updated_at before update on public.goals
  for each row execute function set_updated_at();

alter table public.implementation_intentions enable row level security;
drop policy if exists "intentions_owner_all" on public.implementation_intentions;
create policy "intentions_owner_all" on public.implementation_intentions
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop trigger if exists intentions_set_updated_at on public.implementation_intentions;
create trigger intentions_set_updated_at before update on public.implementation_intentions
  for each row execute function set_updated_at();

grant select, insert, update, delete on public.goals, public.implementation_intentions to authenticated;
