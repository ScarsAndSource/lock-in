-- Lock'in — migration 020 (Agent B: calendar import and exam awareness). Idempotent. Depends on 001 (auth.users) only.
--
-- calendar_events  events imported from an .ics file (a Google / Outlook / Apple / university timetable export).
--                  * source        a short label per imported file ("timetable", "exams"). Re-importing the same source REPLACES its
--                                  future events, so re-exporting an updated timetable never duplicates anything.
--                  * kind          exam | class | other. Guessed from the title at import; the person can correct it, and a corrected
--                                  row (kind_locked) keeps the person's choice across re-imports.
--                  * stored        title, start, end, all-day flag. Never location, description, attendees or links.

create table if not exists public.calendar_events (
  id          uuid primary key,
  user_id     uuid not null references auth.users(id) on delete cascade,
  source      text not null check (char_length(source) between 1 and 40),
  uid         text not null check (char_length(uid) between 1 and 200),
  title       text not null check (char_length(title) between 1 and 120),
  starts_at   timestamptz not null,
  ends_at     timestamptz,
  all_day     boolean not null default false,
  kind        text not null default 'other' check (kind in ('exam', 'class', 'other')),
  kind_locked boolean not null default false,
  imported_at timestamptz not null default now(),
  constraint calendar_events_source_uid_start unique (user_id, source, uid, starts_at)
);

create index if not exists calendar_events_user_start_idx on public.calendar_events (user_id, starts_at);
create index if not exists calendar_events_user_kind_start_idx on public.calendar_events (user_id, kind, starts_at);

alter table public.calendar_events enable row level security;

drop policy if exists "calendar_events_owner_all" on public.calendar_events;
create policy "calendar_events_owner_all"
  on public.calendar_events
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

grant select, insert, update, delete on public.calendar_events to authenticated;
