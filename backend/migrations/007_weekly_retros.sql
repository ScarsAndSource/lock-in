-- Lock'in — migration 007: weekly retrospectives. Idempotent.

create table if not exists public.weekly_retros (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  week_start    date not null,                 -- always a Monday (user-local)
  week_end      date not null,                 -- the Sunday
  generated_at  timestamptz not null,
  narrative     text not null check (char_length(narrative) between 1 and 800),
  next_step     text not null check (char_length(next_step) between 1 and 300),
  summary       jsonb not null default '{}'::jsonb,        -- exactly the facts the narration was built from
  evidence_refs jsonb not null default '{}'::jsonb,
  narrated      boolean not null default false,            -- false = deterministic fallback text
  voice_version text not null,
  model         text,
  completed_at  timestamptz,                               -- set when the user finishes the retro flow
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint weekly_retros_user_week_key unique (user_id, week_start),
  constraint weekly_retros_monday_check check (extract(isodow from week_start) = 1),
  constraint weekly_retros_span_check check (week_end = week_start + 6)
);

create index if not exists weekly_retros_user_week_idx
  on public.weekly_retros (user_id, week_start desc);

alter table public.weekly_retros enable row level security;

drop policy if exists "weekly_retros_owner_all" on public.weekly_retros;
create policy "weekly_retros_owner_all" on public.weekly_retros
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop trigger if exists weekly_retros_set_updated_at on public.weekly_retros;
create trigger weekly_retros_set_updated_at before update on public.weekly_retros
  for each row execute function set_updated_at();

grant select, insert, update, delete on public.weekly_retros to authenticated;
