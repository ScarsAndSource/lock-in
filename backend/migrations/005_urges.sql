-- Lock'in — migration 005: urge logs. Idempotent.
-- Most sensitive table in the schema: every free-text field is app-layer encrypted (Fernet),
-- Postgres only ever sees ciphertext. A bare {outcome} row is a complete, valid log.

create table if not exists public.urge_logs (
  id                        uuid primary key default gen_random_uuid(),
  user_id                   uuid not null references auth.users(id) on delete cascade,
  occurred_at               timestamptz not null,
  log_date                  date not null,          -- user-LOCAL calendar date of occurred_at
  outcome                   text not null check (outcome in ('resisted', 'relapsed')),
  intensity                 smallint check (intensity between 1 and 10),
  trigger_context_encrypted bytea,
  coping_strategy_encrypted bytea,
  note_encrypted            bytea,
  created_at                timestamptz not null default now(),
  updated_at                timestamptz not null default now()
);

create index if not exists urge_logs_user_date_idx on public.urge_logs (user_id, log_date);
create index if not exists urge_logs_user_occurred_idx on public.urge_logs (user_id, occurred_at desc);

alter table public.urge_logs enable row level security;
drop policy if exists "urge_logs_owner_all" on public.urge_logs;
create policy "urge_logs_owner_all" on public.urge_logs
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop trigger if exists urge_logs_set_updated_at on public.urge_logs;
create trigger urge_logs_set_updated_at before update on public.urge_logs
  for each row execute function set_updated_at();

grant select, insert, update, delete on public.urge_logs to authenticated;
