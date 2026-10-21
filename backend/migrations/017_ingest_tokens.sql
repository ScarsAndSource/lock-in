-- Lock'in — migration 017: ingest tokens for OS automations (Apple Shortcuts, Tasker, webhooks).
-- Idempotent. Run after 016. Depends on 001.

create table if not exists public.ingest_tokens (
  id           uuid primary key,
  user_id      uuid not null references auth.users(id) on delete cascade,
  label        text not null check (char_length(label) between 1 and 64),
  created_at   timestamptz not null default now(),
  last_used_at timestamptz,
  revoked_at   timestamptz
);

create index if not exists ingest_tokens_user_id_idx on public.ingest_tokens (user_id);

alter table public.ingest_tokens enable row level security;

drop policy if exists "ingest_tokens_owner_all" on public.ingest_tokens;
create policy "ingest_tokens_owner_all"
  on public.ingest_tokens
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

grant select, insert, update, delete on public.ingest_tokens to authenticated;
