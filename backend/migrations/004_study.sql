-- Lock'in — migration 004: study (subjects + sessions). Idempotent.

create table if not exists public.subjects (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  name        text not null check (char_length(trim(name)) between 1 and 80),
  archived_at timestamptz,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint subjects_id_user_key unique (id, user_id)
);

-- One ACTIVE subject per (user, case-insensitive name); archived ones don't block a re-create.
create unique index if not exists subjects_user_name_active_idx
  on public.subjects (user_id, lower(name)) where archived_at is null;

create table if not exists public.study_sessions (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  subject_id      uuid not null,
  log_date        date not null,
  planned_minutes integer check (planned_minutes between 1 and 1440),
  actual_minutes  integer not null check (actual_minutes between 0 and 1440),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  -- Composite FK: a session can only point at a subject OWNED BY THE SAME USER.
  -- (A plain FK ignores RLS, so without this a bug could attach your session to someone else's subject.)
  constraint study_sessions_subject_owner_fk
    foreign key (subject_id, user_id) references public.subjects (id, user_id) on delete cascade
);

create index if not exists study_sessions_user_date_idx on public.study_sessions (user_id, log_date);

alter table public.subjects enable row level security;
drop policy if exists "subjects_owner_all" on public.subjects;
create policy "subjects_owner_all" on public.subjects
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop trigger if exists subjects_set_updated_at on public.subjects;
create trigger subjects_set_updated_at before update on public.subjects
  for each row execute function set_updated_at();

alter table public.study_sessions enable row level security;
drop policy if exists "study_sessions_owner_all" on public.study_sessions;
create policy "study_sessions_owner_all" on public.study_sessions
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop trigger if exists study_sessions_set_updated_at on public.study_sessions;
create trigger study_sessions_set_updated_at before update on public.study_sessions
  for each row execute function set_updated_at();

grant select, insert, update, delete on public.subjects, public.study_sessions to authenticated;
