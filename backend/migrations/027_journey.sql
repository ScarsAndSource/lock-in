-- Lock'in — migration 027: journey layer (seasons, exam radar, life snapshots, graduation shelf). Idempotent.

create table if not exists public.seasons (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  name            text not null check (char_length(trim(name)) between 1 and 60),
  start_date      date not null,
  slots           smallint not null default 3 check (slots between 3 and 50),
  focus_habit_ids uuid[] not null default '{}',
  closed_on       date,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create unique index if not exists seasons_one_open_idx on public.seasons (user_id) where closed_on is null;
create index if not exists seasons_user_idx on public.seasons (user_id, start_date desc);

create table if not exists public.recall_sets (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references auth.users(id) on delete cascade,
  label            text not null check (char_length(trim(label)) between 1 and 60),
  topics_encrypted bytea not null,
  exam_date        date,
  archived_at      timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create index if not exists recall_sets_user_idx on public.recall_sets (user_id) where archived_at is null;

create table if not exists public.recall_reviews (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  set_id     uuid not null references public.recall_sets(id) on delete cascade,
  step       smallint not null check (step in (1, 3, 7, 14)),
  due_date   date not null,
  done_at    timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint recall_reviews_set_step_key unique (set_id, step)
);
create index if not exists recall_reviews_due_idx on public.recall_reviews (user_id, due_date) where done_at is null;

create table if not exists public.life_snapshots (
  id                     uuid primary key default gen_random_uuid(),
  user_id                uuid not null references auth.users(id) on delete cascade,
  taken_on               date not null,
  wellbeing              smallint not null check (wellbeing between 0 and 10),
  sleep                  smallint not null check (sleep between 0 and 10),
  focus                  smallint not null check (focus between 0 and 10),
  becoming               smallint not null check (becoming between 0 and 10),
  automatic              smallint not null check (automatic between 0 and 10),
  custom_label_encrypted bytea,
  custom_value           double precision,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  constraint life_snapshots_user_day_key unique (user_id, taken_on)
);

create table if not exists public.habit_graduations (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users(id) on delete cascade,
  habit_id       uuid not null references public.habit_definitions(id) on delete cascade,
  graduated_on   date not null,
  check30_on     date not null,
  check90_on     date not null,
  check30_result text check (check30_result in ('holding', 'slipping')),
  check90_result text check (check90_result in ('holding', 'slipping')),
  revived_on     date,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create unique index if not exists habit_graduations_open_idx on public.habit_graduations (habit_id) where revived_on is null;
create index if not exists habit_graduations_user_idx on public.habit_graduations (user_id, graduated_on desc);

do $$
declare t text;
begin
  foreach t in array array['seasons', 'recall_sets', 'recall_reviews', 'life_snapshots', 'habit_graduations'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "%s_owner_all" on public.%I', t, t);
    execute format('create policy "%s_owner_all" on public.%I for all using (auth.uid() = user_id) with check (auth.uid() = user_id)', t, t);
    execute format('drop trigger if exists %s_set_updated_at on public.%I', t, t);
    execute format('create trigger %s_set_updated_at before update on public.%I for each row execute function set_updated_at()', t, t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);
  end loop;
end $$;