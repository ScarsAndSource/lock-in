-- Lock'in — migration 025: weekly share snapshots, Crew Sunday card, cheers, boosts. Idempotent.

create table if not exists public.weekly_snapshots (
  user_id       uuid not null references auth.users(id) on delete cascade,
  week_start    date not null check (extract(isodow from week_start) = 1),
  days_showed   smallint check (days_showed between 0 and 7),
  days_planned  smallint check (days_planned between 0 and 7),
  marks         smallint check (marks between 0 and 127),
  study_minutes integer  check (study_minutes between 0 and 2100),
  proud         text     check (char_length(proud) <= 120),
  focus         text     check (char_length(focus) <= 120),
  habits        text[]   check (cardinality(habits) <= 5),
  created_at    timestamptz not null default now(),
  primary key (user_id, week_start),
  check (days_showed is null or days_planned is null or days_showed <= days_planned)
);

create table if not exists public.crew_cheers (
  id         uuid primary key default gen_random_uuid(),
  from_user  uuid not null references auth.users(id) on delete cascade,
  to_user    uuid not null references auth.users(id) on delete cascade,
  crew_id    uuid not null references public.crews(id) on delete cascade,
  kind       text not null check (kind in ('showed_up', 'proud', 'hard_week', 'rooting')),
  sent_on    date not null default ((now() at time zone 'utc')::date),
  created_at timestamptz not null default now(),
  seen_at    timestamptz,
  constraint crew_cheers_one_per_day unique (from_user, to_user, sent_on),
  check (from_user <> to_user)
);
create index if not exists crew_cheers_to_idx on public.crew_cheers (to_user, created_at desc);

create table if not exists public.crew_boosts (
  id         uuid primary key default gen_random_uuid(),
  batch_id   uuid not null,
  from_user  uuid not null references auth.users(id) on delete cascade,
  to_user    uuid not null references auth.users(id) on delete cascade,
  crew_id    uuid not null references public.crews(id) on delete cascade,
  created_at timestamptz not null default now(),
  seen_at    timestamptz,
  check (from_user <> to_user)
);
create index if not exists crew_boosts_to_idx on public.crew_boosts (to_user, created_at desc);
create index if not exists crew_boosts_from_idx on public.crew_boosts (from_user, created_at desc);

alter table public.weekly_snapshots enable row level security;
alter table public.crew_cheers      enable row level security;
alter table public.crew_boosts      enable row level security;
revoke all on table public.weekly_snapshots, public.crew_cheers, public.crew_boosts from anon, authenticated;

-- You may write and read ONLY your own snapshot rows. Friends read them through crew_card() below.
drop policy if exists "weekly_snapshots_owner_select" on public.weekly_snapshots;
create policy "weekly_snapshots_owner_select" on public.weekly_snapshots for select using (auth.uid() = user_id);
drop policy if exists "weekly_snapshots_owner_insert" on public.weekly_snapshots;
create policy "weekly_snapshots_owner_insert" on public.weekly_snapshots for insert with check (auth.uid() = user_id);
grant select, insert on public.weekly_snapshots to authenticated;

-- Next 19:00 in the recipient's timezone after a cheer was sent (the quiet batch). Falls back to UTC on a bad zone.
create or replace function public._crew_batch_at(p_ts timestamptz, p_tz text) returns timestamptz
language plpgsql stable set search_path = public as $$
declare
  v_tz    text := coalesce(p_tz, 'UTC');
  v_local timestamp;
  v_day   date;
begin
  begin
    v_local := p_ts at time zone v_tz;
  exception when others then
    v_tz := 'UTC';
    v_local := p_ts at time zone 'UTC';
  end;
  v_day := v_local::date + case when v_local::time < time '19:00' then 0 else 1 end;
  return (v_day + time '19:00') at time zone v_tz;
end $$;

-- ---------------------------------------------------------------- the Sunday card
create or replace function public.crew_card(p_crew uuid, p_week date) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  v_uid     uuid := auth.uid();
  v_members jsonb;
  v_min     int;
  v_sharers int;
begin
  if v_uid is null
     or not exists (select 1 from public.crew_members where crew_id = p_crew and user_id = v_uid and status = 'active') then
    return jsonb_build_object('error', 'not_found');
  end if;
  -- Crew stats unlock only after YOU closed your own week.
  if not exists (select 1 from public.weekly_snapshots where user_id = v_uid and week_start = p_week) then
    return jsonb_build_object('locked', true, 'week_start', p_week);
  end if;

  with base as (
    select h.username,
           (m.user_id = v_uid)                                   as me,
           (m.user_id = v_uid or not m.quiet)                    as vis,
           coalesce((h.share ->> 'days')   ::boolean, false)     as s_days,
           coalesce((h.share ->> 'hours')  ::boolean, false)     as s_hours,
           coalesce((h.share ->> 'proud')  ::boolean, false)     as s_proud,
           coalesce((h.share ->> 'focus')  ::boolean, false)     as s_focus,
           coalesce((h.share ->> 'habits') ::boolean, false)     as s_habits,
           s.days_showed, s.days_planned, s.marks, s.study_minutes, s.proud, s.focus, s.habits,
           (s.user_id is not null)                               as snap
    from public.crew_members m
    join public.user_handles h on h.user_id = m.user_id
    left join public.weekly_snapshots s
           on s.user_id = m.user_id and s.week_start = p_week and m.joined_at::date <= p_week + 6
    where m.crew_id = p_crew and m.status = 'active'
      and (m.user_id = v_uid or not public._crew_blocked(v_uid, m.user_id))
  )
  select
    jsonb_agg(jsonb_build_object(
      'username', username,
      'is_me', me,
      'state', case when not vis or not s_days then 'private'
                    when snap and days_showed is null then 'private'
                    when not snap or days_showed = 0 then 'resting'
                    else 'shared' end,
      'days_showed',  case when vis and s_days and snap and days_showed > 0 then days_showed end,
      'days_planned', case when vis and s_days and snap and days_showed > 0 then days_planned end,
      'marks',        case when vis and s_days and snap and days_showed > 0 then marks end,
      'proud',  case when vis and s_proud  and snap then proud end,
      'focus',  case when vis and s_focus  and snap then focus end,
      'habits', case when vis and s_habits and snap then to_jsonb(habits) end
    ) order by username),
    coalesce(sum(study_minutes) filter (where vis and s_hours and snap and study_minutes is not null), 0)::int,
    (count(*) filter (where vis and s_hours and snap and study_minutes is not null))::int
  into v_members, v_min, v_sharers
  from base;

  return jsonb_build_object(
    'locked', false, 'week_start', p_week, 'members', coalesce(v_members, '[]'::jsonb),
    'study_minutes', case when v_sharers >= 2 then v_min end,   -- a total of one person is just their number
    'hours_sharers', v_sharers
  );
end $$;

-- ---------------------------------------------------------------- cheers
create or replace function public.crew_send_cheer(p_crew uuid, p_to text, p_kind text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_uid uuid := auth.uid();
  v_to  uuid;
  v_n   int := 0;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  if p_kind is null or p_kind not in ('showed_up', 'proud', 'hard_week', 'rooting') then
    return jsonb_build_object('error', 'invalid');
  end if;
  if not exists (select 1 from public.crew_members where crew_id = p_crew and user_id = v_uid and status = 'active') then
    return jsonb_build_object('error', 'not_found');
  end if;
  select m.user_id into v_to
    from public.crew_members m join public.user_handles h on h.user_id = m.user_id
    where m.crew_id = p_crew and m.status = 'active' and h.username = lower(btrim(coalesce(p_to, '')));
  if v_to is null then return jsonb_build_object('error', 'not_found'); end if;
  if v_to = v_uid then return jsonb_build_object('error', 'self'); end if;
  if public._crew_blocked(v_uid, v_to) then return jsonb_build_object('ok', true); end if;  -- silent
  insert into public.crew_cheers (from_user, to_user, crew_id, kind)
    values (v_uid, v_to, p_crew, p_kind)
    on conflict (from_user, to_user, sent_on) do nothing;
  get diagnostics v_n = row_count;
  if v_n = 0 then return jsonb_build_object('error', 'already_today'); end if;
  return jsonb_build_object('ok', true);
end $$;

-- ---------------------------------------------------------------- "I could use a boost" (no details, ever)
create or replace function public.crew_send_boost(p_crew uuid, p_to text default null) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_uid   uuid := auth.uid();
  v_to    uuid;
  v_batch uuid := gen_random_uuid();
  v_n     int := 0;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  if not exists (select 1 from public.crew_members where crew_id = p_crew and user_id = v_uid and status = 'active') then
    return jsonb_build_object('error', 'not_found');
  end if;
  if (select count(distinct batch_id) from public.crew_boosts
        where from_user = v_uid and created_at > now() - interval '24 hours') >= 2 then
    return jsonb_build_object('error', 'too_many');
  end if;
  if p_to is null then
    insert into public.crew_boosts (batch_id, from_user, to_user, crew_id)
      select v_batch, v_uid, m.user_id, p_crew
      from public.crew_members m
      where m.crew_id = p_crew and m.status = 'active' and m.user_id <> v_uid
        and not public._crew_blocked(v_uid, m.user_id);
    get diagnostics v_n = row_count;
    if v_n = 0 then return jsonb_build_object('error', 'nobody'); end if;
  else
    select m.user_id into v_to
      from public.crew_members m join public.user_handles h on h.user_id = m.user_id
      where m.crew_id = p_crew and m.status = 'active' and m.user_id <> v_uid
        and h.username = lower(btrim(p_to));
    if v_to is null then return jsonb_build_object('error', 'not_found'); end if;
    if not public._crew_blocked(v_uid, v_to) then  -- blocked: pretend it sent
      insert into public.crew_boosts (batch_id, from_user, to_user, crew_id) values (v_batch, v_uid, v_to, p_crew);
    end if;
  end if;
  return jsonb_build_object('ok', true);
end $$;

-- ---------------------------------------------------------------- inbox (cheers arrive in the 19:00 batch; boosts instantly)
create or replace function public.crew_inbox() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  v_uid    uuid := auth.uid();
  v_tz     text;
  v_cheers jsonb;
  v_boosts jsonb;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  select timezone into v_tz from public.profiles where id = v_uid;
  v_tz := coalesce(v_tz, 'UTC');

  select coalesce(jsonb_agg(jsonb_build_object(
           'id', c.id, 'kind', c.kind, 'from_username', h.username,
           'at', c.delivered_at, 'seen', c.seen_at is not null
         ) order by c.delivered_at desc), '[]'::jsonb)
  into v_cheers
  from (
    select *, public._crew_batch_at(created_at, v_tz) as delivered_at
    from public.crew_cheers
    where to_user = v_uid and created_at >= now() - interval '30 days'
  ) c
  join public.user_handles h on h.user_id = c.from_user
  where c.delivered_at <= now() and not public._crew_blocked(v_uid, c.from_user);

  select coalesce(jsonb_agg(jsonb_build_object(
           'id', b.id, 'from_username', h.username, 'crew_id', b.crew_id, 'crew_name', cr.name,
           'at', b.created_at, 'seen', b.seen_at is not null
         ) order by b.created_at desc), '[]'::jsonb)
  into v_boosts
  from (
    select * from public.crew_boosts
    where to_user = v_uid and created_at >= now() - interval '7 days'
    order by created_at desc limit 20
  ) b
  join public.user_handles h on h.user_id = b.from_user
  join public.crews cr on cr.id = b.crew_id
  where not public._crew_blocked(v_uid, b.from_user);

  return jsonb_build_object('cheers', v_cheers, 'boosts', v_boosts);
end $$;

create or replace function public.crew_inbox_seen() returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_uid uuid := auth.uid();
  v_tz  text;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  select timezone into v_tz from public.profiles where id = v_uid;
  v_tz := coalesce(v_tz, 'UTC');
  update public.crew_cheers set seen_at = now()
    where to_user = v_uid and seen_at is null and public._crew_batch_at(created_at, v_tz) <= now();
  update public.crew_boosts set seen_at = now() where to_user = v_uid and seen_at is null;
  return jsonb_build_object('ok', true);
end $$;

revoke all on function public._crew_batch_at(timestamptz, text) from public, anon, authenticated;
revoke all on function public.crew_card(uuid, date) from public, anon;
revoke all on function public.crew_send_cheer(uuid, text, text) from public, anon;
revoke all on function public.crew_send_boost(uuid, text) from public, anon;
revoke all on function public.crew_inbox() from public, anon;
revoke all on function public.crew_inbox_seen() from public, anon;
grant execute on function public.crew_card(uuid, date) to authenticated;
grant execute on function public.crew_send_cheer(uuid, text, text) to authenticated;
grant execute on function public.crew_send_boost(uuid, text) to authenticated;
grant execute on function public.crew_inbox() to authenticated;
grant execute on function public.crew_inbox_seen() to authenticated;
