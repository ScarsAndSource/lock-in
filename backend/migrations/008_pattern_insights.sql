-- Lock'in — migration 008: pattern insights (persisted) + feedback loop. Idempotent.

create table if not exists public.pattern_insights (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users(id) on delete cascade,
  generated_at   timestamptz not null,
  generated_on   date not null,                       -- user-local day it was generated
  pattern_key    text not null check (char_length(pattern_key) between 1 and 80),
  insight_text   text not null check (char_length(insight_text) between 1 and 800),
  next_step      text not null check (char_length(next_step) between 1 and 300),
  source_domains text[] not null default '{}',
  evidence_refs  jsonb not null default '{}'::jsonb,
  narrated       boolean not null default false,      -- false = deterministic text
  voice_version  text not null,
  model          text,
  user_feedback  text check (user_feedback in ('accurate', 'not_quite', 'unsure')),
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint pattern_insights_user_key_day unique (user_id, pattern_key, generated_on)
);

create index if not exists pattern_insights_user_generated_idx
  on public.pattern_insights (user_id, generated_at desc);
create index if not exists pattern_insights_unrated_idx
  on public.pattern_insights (user_id) where user_feedback is null;

alter table public.pattern_insights enable row level security;

drop policy if exists "pattern_insights_owner_all" on public.pattern_insights;
create policy "pattern_insights_owner_all" on public.pattern_insights
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop trigger if exists pattern_insights_set_updated_at on public.pattern_insights;
create trigger pattern_insights_set_updated_at before update on public.pattern_insights
  for each row execute function set_updated_at();

grant select, insert, update, delete on public.pattern_insights to authenticated;
