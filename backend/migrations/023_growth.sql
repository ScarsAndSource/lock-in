-- Lock'in — migration 023: growth layer (identity, habit check-ups, notes to future self, journal stickers). Idempotent.

create table if not exists public.identity_profiles (
  user_id            uuid primary key references auth.users(id) on delete cascade,
  matters_encrypted  bytea not null,
  why_now_encrypted  bytea not null,
  importance         smallint not null check (importance between 0 and 10),
  confidence         smallint not null check (confidence between 0 and 10),
  sentence_encrypted bytea not null,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

create table if not exists public.habit_autopsies (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  habit_id        uuid not null references public.habit_definitions(id) on delete cascade,
  status          text not null default 'open' check (status in ('open', 'applied', 'snoozed', 'dismissed')),
  reason          text check (reason in ('too_big', 'wrong_time', 'wrong_trigger', 'dont_care')),
  fix             jsonb not null default '{}'::jsonb,
  consistency_pct real,
  opened_on       date not null,
  resolved_at     timestamptz,
  cooldown_until  date,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create unique index if not exists habit_autopsies_one_open_idx
  on public.habit_autopsies (habit_id) where status = 'open';
create index if not exists habit_autopsies_user_idx
  on public.habit_autopsies (user_id, opened_on desc);

create table if not exists public.future_messages (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  text_encrypted  bytea,
  audio_encrypted bytea,
  audio_mime      text,
  duration_s      smallint,
  send_at         time,                       -- local wall clock; null = follow my usual slip time (default 23:00)
  active          boolean not null default true,
  last_sent_on    date,
  last_played_at  timestamptz,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint future_messages_content_check check (text_encrypted is not null or audio_encrypted is not null),
  constraint future_messages_audio_check check ((audio_encrypted is null) = (audio_mime is null))
);
create index if not exists future_messages_user_active_idx
  on public.future_messages (user_id) where active;

create table if not exists public.journal_stickers (
  user_id    uuid not null references auth.users(id) on delete cascade,
  entry_date date not null,
  sticker    text not null check (char_length(sticker) between 1 and 8),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, entry_date)
);

-- RLS + triggers + grants, same pattern as 007
alter table public.identity_profiles enable row level security;
alter table public.habit_autopsies   enable row level security;
alter table public.future_messages   enable row level security;
alter table public.journal_stickers  enable row level security;

drop policy if exists "identity_profiles_owner_all" on public.identity_profiles;
create policy "identity_profiles_owner_all" on public.identity_profiles
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "habit_autopsies_owner_all" on public.habit_autopsies;
create policy "habit_autopsies_owner_all" on public.habit_autopsies
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "future_messages_owner_all" on public.future_messages;
create policy "future_messages_owner_all" on public.future_messages
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "journal_stickers_owner_all" on public.journal_stickers;
create policy "journal_stickers_owner_all" on public.journal_stickers
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop trigger if exists identity_profiles_set_updated_at on public.identity_profiles;
create trigger identity_profiles_set_updated_at before update on public.identity_profiles
  for each row execute function set_updated_at();
drop trigger if exists habit_autopsies_set_updated_at on public.habit_autopsies;
create trigger habit_autopsies_set_updated_at before update on public.habit_autopsies
  for each row execute function set_updated_at();
drop trigger if exists future_messages_set_updated_at on public.future_messages;
create trigger future_messages_set_updated_at before update on public.future_messages
  for each row execute function set_updated_at();
drop trigger if exists journal_stickers_set_updated_at on public.journal_stickers;
create trigger journal_stickers_set_updated_at before update on public.journal_stickers
  for each row execute function set_updated_at();

grant select, insert, update, delete on public.identity_profiles to authenticated;
grant select, insert, update, delete on public.habit_autopsies   to authenticated;
grant select, insert, update, delete on public.future_messages   to authenticated;
grant select, insert, update, delete on public.journal_stickers  to authenticated;
