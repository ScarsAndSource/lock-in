-- Lock'in — migration 026: crew goals, buddy deals, handicapped duels, push moments. Idempotent.

create table if not exists public.crew_goals (
  crew_id        uuid not null references public.crews(id) on delete cascade,
  week_start     date not null check (extract(isodow from week_start) = 1),
  target_minutes integer not null check (target_minutes between 60 and 12000),
  set_by         uuid references auth.users(id) on delete set null,
  updated_at     timestamptz not null default now(),
  primary key (crew_id, week_start)
);

create table if not exists public.crew_buddy_deals (
  id             uuid primary key default gen_random_uuid(),
  crew_id        uuid not null references public.crews(id) on delete cascade,
  owner_id       uuid not null references auth.users(id) on delete cascade,
  buddy_id       uuid not null references auth.users(id) on delete cascade,
  status         text not null default 'pending' check (status in ('pending', 'active')),
  miss_threshold smallint not null default 3 check (miss_threshold between 2 and 7),
  message        text not null check (char_length(message) between 1 and 140),
  auto_send      boolean not null default false,
  armed_from     date,
  last_sent_at   timestamptz,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  check (owner_id <> buddy_id)
);
create unique index if not exists crew_buddy_deals_live_pair on public.crew_buddy_deals (owner_id, buddy_id);
create index if not exists crew_buddy_deals_buddy_idx on public.crew_buddy_deals (buddy_id);

create table if not exists public.crew_buddy_messages (
  id         uuid primary key default gen_random_uuid(),
  deal_id    uuid not null references public.crew_buddy_deals(id) on delete cascade,
  from_user  uuid not null references auth.users(id) on delete cascade,
  to_user    uuid not null references auth.users(id) on delete cascade,
  body       text not null check (char_length(body) between 1 and 140),
  created_at timestamptz not null default now(),
  seen_at    timestamptz
);
create index if not exists crew_buddy_messages_to_idx on public.crew_buddy_messages (to_user, created_at desc);

create table if not exists public.crew_duels (
  id            uuid primary key default gen_random_uuid(),
  crew_id       uuid not null references public.crews(id) on delete cascade,
  challenger_id uuid not null references auth.users(id) on delete cascade,
  opponent_id   uuid not null references auth.users(id) on delete cascade,
  week_start    date not null check (extract(isodow from week_start) = 1),
  status        text not null default 'pending' check (status in ('pending', 'active')),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  check (challenger_id <> opponent_id)
);
create unique index if not exists crew_duels_live_pair
  on public.crew_duels (least(challenger_id, opponent_id), greatest(challenger_id, opponent_id), week_start);
create index if not exists crew_duels_challenger_idx on public.crew_duels (challenger_id);
create index if not exists crew_duels_opponent_idx on public.crew_duels (opponent_id);

create table if not exists public.crew_duel_scores (
  duel_id        uuid not null references public.crew_duels(id) on delete cascade,
  user_id        uuid not null references auth.users(id) on delete cascade,
  ratio_milli    smallint not null check (ratio_milli between 0 and 1000),
  baseline_milli smallint not null check (baseline_milli between 0 and 1000),
  created_at     timestamptz not null default now(),
  primary key (duel_id, user_id)
);

drop trigger if exists crew_buddy_deals_set_updated_at on public.crew_buddy_deals;
create trigger crew_buddy_deals_set_updated_at before update on public.crew_buddy_deals
  for each row execute function set_updated_at();
drop trigger if exists crew_duels_set_updated_at on public.crew_duels;
create trigger crew_duels_set_updated_at before update on public.crew_duels
  for each row execute function set_updated_at();

alter table public.crew_goals         enable row level security;
alter table public.crew_buddy_deals   enable row level security;
alter table public.crew_buddy_messages enable row level security;
alter table public.crew_duels         enable row level security;
alter table public.crew_duel_scores   enable row level security;
revoke all on table public.crew_goals, public.crew_buddy_deals, public.crew_buddy_messages,
  public.crew_duels, public.crew_duel_scores from anon, authenticated;

-- ---------------------------------------------------------------- crew goal (owner sets, members read)
create or replace function public.crew_set_goal(p_crew uuid, p_week date, p_hours integer) returns jsonb
language plpgsql security definer set search_path = public as $$
declare v_uid uuid := auth.uid();
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  if not exists (select 1 from public.crew_members
                 where crew_id = p_crew and user_id = v_uid and role = 'owner' and status = 'active') then
    return jsonb_build_object('error', 'forbidden');
  end if;
  if p_week is null or extract(isodow from p_week) <> 1 then return jsonb_build_object('error', 'invalid'); end if;
  if p_hours is null then
    delete from public.crew_goals where crew_id = p_crew and week_start = p_week;
    return jsonb_build_object('ok', true);
  end if;
  if p_hours not between 1 and 200 then return jsonb_build_object('error', 'invalid'); end if;
  insert into public.crew_goals (crew_id, week_start, target_minutes, set_by)
    values (p_crew, p_week, p_hours * 60, v_uid)
    on conflict (crew_id, week_start) do update
      set target_minutes = excluded.target_minutes, set_by = excluded.set_by, updated_at = now();
  return jsonb_build_object('ok', true);
end $$;

create or replace function public.crew_goal(p_crew uuid, p_week date) returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  if auth.uid() is null
     or not exists (select 1 from public.crew_members where crew_id = p_crew and user_id = auth.uid() and status = 'active') then
    return jsonb_build_object('error', 'not_found');
  end if;
  return jsonb_build_object('ok', true, 'target_minutes',
    (select target_minutes from public.crew_goals where crew_id = p_crew and week_start = p_week));
end $$;

-- ---------------------------------------------------------------- buddy deals
create or replace function public.crew_buddy_propose(
  p_crew uuid, p_to text, p_threshold integer, p_message text, p_auto boolean
) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_uid uuid := auth.uid();
  v_to  uuid;
  v_msg text := btrim(coalesce(p_message, ''));
  v_id  uuid;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  if char_length(v_msg) not between 1 and 140 or p_threshold is null or p_threshold not between 2 and 7 then
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
  delete from public.crew_buddy_deals
    where owner_id = v_uid and status = 'pending' and created_at < now() - interval '14 days';
  if (select count(*) from public.crew_buddy_deals where owner_id = v_uid) >= 2 then
    return jsonb_build_object('error', 'deal_limit');
  end if;
  insert into public.crew_buddy_deals (crew_id, owner_id, buddy_id, miss_threshold, message, auto_send)
    values (p_crew, v_uid, v_to, p_threshold, v_msg, coalesce(p_auto, false))
    returning id into v_id;
  return jsonb_build_object('ok', true, 'deal_id', v_id);
exception when unique_violation then
  return jsonb_build_object('error', 'already');
end $$;

create or replace function public.crew_buddy_respond(p_deal uuid, p_accept boolean, p_today date) returns jsonb
language plpgsql security definer set search_path = public as $$
declare v_uid uuid := auth.uid();
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  if not exists (select 1 from public.crew_buddy_deals
                 where id = p_deal and buddy_id = v_uid and status = 'pending'
                   and created_at >= now() - interval '14 days') then
    return jsonb_build_object('error', 'not_found');
  end if;
  if not coalesce(p_accept, false) then   -- declining is silent: the row just disappears
    delete from public.crew_buddy_deals where id = p_deal;
    return jsonb_build_object('ok', true);
  end if;
  update public.crew_buddy_deals
    set status = 'active', armed_from = coalesce(p_today, (now() at time zone 'utc')::date)
    where id = p_deal;
  return jsonb_build_object('ok', true);
end $$;

create or replace function public.crew_buddy_cancel(p_deal uuid) returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then return jsonb_build_object('error', 'unauthorized'); end if;
  delete from public.crew_buddy_deals where id = p_deal and (owner_id = auth.uid() or buddy_id = auth.uid());
  if not found then return jsonb_build_object('error', 'not_found'); end if;
  return jsonb_build_object('ok', true);
end $$;

create or replace function public.crew_buddy_dismiss(p_deal uuid, p_today date) returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then return jsonb_build_object('error', 'unauthorized'); end if;
  update public.crew_buddy_deals
    set armed_from = coalesce(p_today, (now() at time zone 'utc')::date)
    where id = p_deal and owner_id = auth.uid() and status = 'active';
  if not found then return jsonb_build_object('error', 'not_found'); end if;
  return jsonb_build_object('ok', true);
end $$;

-- The owner's tap (or their own auto-send switch). Nothing reaches the buddy any other way.
create or replace function public.crew_buddy_send(p_deal uuid, p_today date) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_uid   uuid := auth.uid();
  v_buddy uuid;
  v_crew  uuid;
  v_msg   text;
  v_last  timestamptz;
  v_day   date := coalesce(p_today, (now() at time zone 'utc')::date);
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  select buddy_id, crew_id, message, last_sent_at into v_buddy, v_crew, v_msg, v_last
    from public.crew_buddy_deals where id = p_deal and owner_id = v_uid and status = 'active' for update;
  if not found then return jsonb_build_object('error', 'not_found'); end if;
  if v_last is not null and v_last > now() - interval '20 hours' then
    return jsonb_build_object('error', 'too_many');
  end if;
  if not public._crew_blocked(v_uid, v_buddy) then
    insert into public.crew_buddy_messages (deal_id, from_user, to_user, body) values (p_deal, v_uid, v_buddy, v_msg);
    -- the buddy gets the same silent "could use a hello" nudge as any boost
    insert into public.crew_boosts (batch_id, from_user, to_user, crew_id)
      values (gen_random_uuid(), v_uid, v_buddy, v_crew);
  end if;
  update public.crew_buddy_deals set armed_from = v_day, last_sent_at = now() where id = p_deal;
  return jsonb_build_object('ok', true);
end $$;

create or replace function public.crew_buddy_list() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  v_uid   uuid := auth.uid();
  v_deals jsonb;
  v_msgs  jsonb;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  select coalesce(jsonb_agg(jsonb_build_object(
      'id', d.id, 'crew_id', d.crew_id,
      'role', case when d.owner_id = v_uid then 'owner' else 'buddy' end,
      'other', h.username, 'status', d.status, 'threshold', d.miss_threshold,
      'auto_send', d.auto_send, 'message', d.message, 'created_at', d.created_at,
      'armed_from', case when d.owner_id = v_uid then d.armed_from end,
      'last_sent_at', case when d.owner_id = v_uid then d.last_sent_at end
    ) order by d.created_at desc), '[]'::jsonb)
  into v_deals
  from public.crew_buddy_deals d
  join public.user_handles h on h.user_id = case when d.owner_id = v_uid then d.buddy_id else d.owner_id end
  where (d.owner_id = v_uid or d.buddy_id = v_uid)
    and (d.status = 'active' or d.created_at >= now() - interval '14 days');

  select coalesce(jsonb_agg(jsonb_build_object(
      'id', m.id, 'crew_id', d.crew_id, 'from_username', h.username, 'body', m.body,
      'at', m.created_at, 'seen', m.seen_at is not null
    ) order by m.created_at desc), '[]'::jsonb)
  into v_msgs
  from (select * from public.crew_buddy_messages
        where to_user = v_uid and created_at >= now() - interval '14 days'
        order by created_at desc limit 10) m
  join public.crew_buddy_deals d on d.id = m.deal_id
  join public.user_handles h on h.user_id = m.from_user
  where not public._crew_blocked(v_uid, m.from_user);

  return jsonb_build_object('deals', v_deals, 'messages', v_msgs);
end $$;

-- ---------------------------------------------------------------- handicapped duels
create or replace function public.crew_duel_propose(p_crew uuid, p_to text, p_week date) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_uid uuid := auth.uid();
  v_to  uuid;
  v_id  uuid;
  v_today date := (now() at time zone 'utc')::date;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  if p_week is null or extract(isodow from p_week) <> 1 or p_week + 6 < v_today then
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
  delete from public.crew_duels
    where (status = 'pending' and created_at < now() - interval '14 days') or week_start < v_today - 90;
  if (select count(*) from public.crew_duels
      where (challenger_id = v_uid or opponent_id = v_uid) and week_start + 6 >= v_today) >= 2 then
    return jsonb_build_object('error', 'duel_limit');
  end if;
  insert into public.crew_duels (crew_id, challenger_id, opponent_id, week_start)
    values (p_crew, v_uid, v_to, p_week) returning id into v_id;
  return jsonb_build_object('ok', true, 'duel_id', v_id);
exception when unique_violation then
  return jsonb_build_object('error', 'already');
end $$;

create or replace function public.crew_duel_respond(p_duel uuid, p_accept boolean) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_uid   uuid := auth.uid();
  v_today date := (now() at time zone 'utc')::date;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  if not exists (select 1 from public.crew_duels
                 where id = p_duel and opponent_id = v_uid and status = 'pending'
                   and created_at >= now() - interval '14 days' and week_start + 6 >= v_today) then
    return jsonb_build_object('error', 'not_found');
  end if;
  if not coalesce(p_accept, false) then   -- declining is silent
    delete from public.crew_duels where id = p_duel;
    return jsonb_build_object('ok', true);
  end if;
  if (select count(*) from public.crew_duels
      where status = 'active' and (challenger_id = v_uid or opponent_id = v_uid) and week_start + 6 >= v_today) >= 2 then
    return jsonb_build_object('error', 'duel_limit');
  end if;
  update public.crew_duels set status = 'active' where id = p_duel;
  return jsonb_build_object('ok', true);
end $$;

create or replace function public.crew_duel_cancel(p_duel uuid) returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then return jsonb_build_object('error', 'unauthorized'); end if;
  delete from public.crew_duels where id = p_duel and (challenger_id = auth.uid() or opponent_id = auth.uid());
  if not found then return jsonb_build_object('error', 'not_found'); end if;
  return jsonb_build_object('ok', true);
end $$;

create or replace function public.crew_duel_score(p_duel uuid, p_ratio integer, p_baseline integer) returns jsonb
language plpgsql security definer set search_path = public as $$
declare v_uid uuid := auth.uid();
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  if p_ratio is null or p_baseline is null or p_ratio < 0 or p_ratio > 1000 or p_baseline < 0 or p_baseline > 1000 then
    return jsonb_build_object('error', 'invalid');
  end if;
  if not exists (select 1 from public.crew_duels
                 where id = p_duel and status = 'active' and (challenger_id = v_uid or opponent_id = v_uid)) then
    return jsonb_build_object('error', 'not_found');
  end if;
  insert into public.crew_duel_scores (duel_id, user_id, ratio_milli, baseline_milli)
    values (p_duel, v_uid, p_ratio, p_baseline) on conflict do nothing;
  return jsonb_build_object('ok', true);
end $$;

-- The result exists only once BOTH sides have scored; before that nobody sees anybody's number.
create or replace function public.crew_duel_list() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  v_uid uuid := auth.uid();
  v_out jsonb;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  select coalesce(jsonb_agg(jsonb_build_object(
      'id', d.id, 'crew_id', d.crew_id,
      'role', case when d.challenger_id = v_uid then 'challenger' else 'opponent' end,
      'other', h.username, 'week_start', d.week_start, 'status', d.status,
      'my_scored', ms.user_id is not null,
      'result', case when ms.user_id is not null and ts.user_id is not null then jsonb_build_object(
          'mine', jsonb_build_object('ratio_pct', round(ms.ratio_milli / 10.0, 1),
                                     'baseline_pct', round(ms.baseline_milli / 10.0, 1),
                                     'delta_pct', round((ms.ratio_milli - ms.baseline_milli) / 10.0, 1)),
          'theirs', jsonb_build_object('ratio_pct', round(ts.ratio_milli / 10.0, 1),
                                       'baseline_pct', round(ts.baseline_milli / 10.0, 1),
                                       'delta_pct', round((ts.ratio_milli - ts.baseline_milli) / 10.0, 1))
        ) end
    ) order by d.week_start desc, d.created_at desc), '[]'::jsonb)
  into v_out
  from public.crew_duels d
  join public.user_handles h on h.user_id = case when d.challenger_id = v_uid then d.opponent_id else d.challenger_id end
  left join public.crew_duel_scores ms on ms.duel_id = d.id and ms.user_id = v_uid
  left join public.crew_duel_scores ts on ts.duel_id = d.id and ts.user_id <> v_uid
  where (d.challenger_id = v_uid or d.opponent_id = v_uid)
    and d.week_start >= (now() at time zone 'utc')::date - 42
    and (d.status = 'active' or d.created_at >= now() - interval '14 days');
  return jsonb_build_object('duels', v_out);
end $$;

-- ---------------------------------------------------------------- one cheap call for the push planner
create or replace function public.crew_moments(p_week date) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  v_uid    uuid := auth.uid();
  v_in     boolean;
  v_closed boolean;
  v_boosts jsonb;
  v_deals  jsonb;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  v_in := exists (select 1 from public.crew_members where user_id = v_uid and status = 'active');
  v_closed := exists (select 1 from public.weekly_snapshots where user_id = v_uid and week_start = p_week);

  select coalesce(jsonb_agg(jsonb_build_object('id', b.id, 'from_username', h.username, 'crew_id', b.crew_id)
                            order by b.created_at desc), '[]'::jsonb)
  into v_boosts
  from (select * from public.crew_boosts
        where to_user = v_uid and created_at > now() - interval '24 hours'
        order by created_at desc limit 5) b
  join public.user_handles h on h.user_id = b.from_user
  where not public._crew_blocked(v_uid, b.from_user);

  select coalesce(jsonb_agg(jsonb_build_object(
      'id', d.id, 'buddy_username', h.username, 'threshold', d.miss_threshold,
      'armed_from', d.armed_from, 'auto_send', d.auto_send
    )), '[]'::jsonb)
  into v_deals
  from public.crew_buddy_deals d join public.user_handles h on h.user_id = d.buddy_id
  where d.owner_id = v_uid and d.status = 'active'
    and (d.last_sent_at is null or d.last_sent_at < now() - interval '20 hours');

  return jsonb_build_object('in_crew', v_in, 'closed', v_closed, 'boosts', v_boosts, 'deals', v_deals);
end $$;

-- ---------------------------------------------------------------- redefined from 024/025 (same bodies plus the new tables)
create or replace function public.crew_leave(p_crew uuid) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_uid  uuid := auth.uid();
  v_next uuid;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  perform pg_advisory_xact_lock(hashtextextended('crew:' || p_crew::text, 0));
  delete from public.crew_members where crew_id = p_crew and user_id = v_uid;
  if not found then return jsonb_build_object('error', 'not_found'); end if;
  delete from public.crew_buddy_deals where crew_id = p_crew and (owner_id = v_uid or buddy_id = v_uid);
  delete from public.crew_duels where crew_id = p_crew and (challenger_id = v_uid or opponent_id = v_uid);
  select user_id into v_next from public.crew_members
    where crew_id = p_crew and status = 'active'
    order by (role = 'owner') desc, joined_at asc limit 1;
  if v_next is null then
    delete from public.crews where id = p_crew;
  else
    update public.crew_members set role = 'owner' where crew_id = p_crew and user_id = v_next and role <> 'owner';
  end if;
  return jsonb_build_object('ok', true);
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
  update public.crew_buddy_messages set seen_at = now() where to_user = v_uid and seen_at is null;
  return jsonb_build_object('ok', true);
end $$;

-- ---------------------------------------------------------------- grants
revoke all on function public.crew_set_goal(uuid, date, integer) from public, anon;
revoke all on function public.crew_goal(uuid, date) from public, anon;
revoke all on function public.crew_buddy_propose(uuid, text, integer, text, boolean) from public, anon;
revoke all on function public.crew_buddy_respond(uuid, boolean, date) from public, anon;
revoke all on function public.crew_buddy_cancel(uuid) from public, anon;
revoke all on function public.crew_buddy_dismiss(uuid, date) from public, anon;
revoke all on function public.crew_buddy_send(uuid, date) from public, anon;
revoke all on function public.crew_buddy_list() from public, anon;
revoke all on function public.crew_duel_propose(uuid, text, date) from public, anon;
revoke all on function public.crew_duel_respond(uuid, boolean) from public, anon;
revoke all on function public.crew_duel_cancel(uuid) from public, anon;
revoke all on function public.crew_duel_score(uuid, integer, integer) from public, anon;
revoke all on function public.crew_duel_list() from public, anon;
revoke all on function public.crew_moments(date) from public, anon;
revoke all on function public.crew_leave(uuid) from public, anon;
revoke all on function public.crew_inbox_seen() from public, anon;

grant execute on function public.crew_set_goal(uuid, date, integer) to authenticated;
grant execute on function public.crew_goal(uuid, date) to authenticated;
grant execute on function public.crew_buddy_propose(uuid, text, integer, text, boolean) to authenticated;
grant execute on function public.crew_buddy_respond(uuid, boolean, date) to authenticated;
grant execute on function public.crew_buddy_cancel(uuid) to authenticated;
grant execute on function public.crew_buddy_dismiss(uuid, date) to authenticated;
grant execute on function public.crew_buddy_send(uuid, date) to authenticated;
grant execute on function public.crew_buddy_list() to authenticated;
grant execute on function public.crew_duel_propose(uuid, text, date) to authenticated;
grant execute on function public.crew_duel_respond(uuid, boolean) to authenticated;
grant execute on function public.crew_duel_cancel(uuid) to authenticated;
grant execute on function public.crew_duel_score(uuid, integer, integer) to authenticated;
grant execute on function public.crew_duel_list() to authenticated;
grant execute on function public.crew_moments(date) to authenticated;
grant execute on function public.crew_leave(uuid) to authenticated;
grant execute on function public.crew_inbox_seen() to authenticated;
