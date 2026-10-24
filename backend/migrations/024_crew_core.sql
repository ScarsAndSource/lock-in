-- Lock'in — migration 024: Crew core (usernames, crews, members, blocks). Idempotent.
-- Tables are closed to API roles; every cross-user read/write goes through SECURITY DEFINER crew_* functions.

create table if not exists public.user_handles (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  username   text not null check (username ~ '^[a-z][a-z0-9_]{2,19}$'),
  share      jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists user_handles_username_key on public.user_handles (username);

create table if not exists public.crews (
  id                uuid primary key default gen_random_uuid(),
  name              text not null check (char_length(name) between 1 and 40),
  created_by        uuid not null references auth.users(id) on delete cascade,
  invite_code       text,
  invite_expires_at timestamptz,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
create unique index if not exists crews_invite_code_key on public.crews (invite_code) where invite_code is not null;

create table if not exists public.crew_members (
  crew_id    uuid not null references public.crews(id) on delete cascade,
  user_id    uuid not null references auth.users(id) on delete cascade,
  role       text not null default 'member' check (role in ('owner', 'member')),
  status     text not null default 'invited' check (status in ('invited', 'active')),
  invited_by uuid references auth.users(id) on delete set null,
  quiet      boolean not null default false,
  joined_at  timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (crew_id, user_id)
);
create index if not exists crew_members_user_idx on public.crew_members (user_id, status);

create table if not exists public.user_blocks (
  blocker_id uuid not null references auth.users(id) on delete cascade,
  blocked_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (blocker_id, blocked_id),
  check (blocker_id <> blocked_id)
);

drop trigger if exists user_handles_set_updated_at on public.user_handles;
create trigger user_handles_set_updated_at before update on public.user_handles
  for each row execute function set_updated_at();
drop trigger if exists crew_members_set_updated_at on public.crew_members;
create trigger crew_members_set_updated_at before update on public.crew_members
  for each row execute function set_updated_at();

-- Default deny: RLS on, no policies, no grants. Only the functions below touch these tables.
alter table public.user_handles enable row level security;
alter table public.crews        enable row level security;
alter table public.crew_members enable row level security;
alter table public.user_blocks  enable row level security;
revoke all on table public.user_handles, public.crews, public.crew_members, public.user_blocks from anon, authenticated;

-- ---------------------------------------------------------------- helpers
create or replace function public._crew_blocked(a uuid, b uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.user_blocks
    where (blocker_id = a and blocked_id = b) or (blocker_id = b and blocked_id = a)
  )
$$;

create or replace function public._crew_active_count(p_user uuid) returns int
language sql stable security definer set search_path = public as $$
  select count(*)::int from public.crew_members where user_id = p_user and status = 'active'
$$;

-- ---------------------------------------------------------------- username + share menu
create or replace function public.crew_set_username(p_username text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_uid  uuid := auth.uid();
  v_name text := lower(btrim(coalesce(p_username, '')));
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  if v_name !~ '^[a-z][a-z0-9_]{2,19}$' then return jsonb_build_object('error', 'invalid'); end if;
  if v_name = any (array['admin','administrator','root','support','help','lockin','lock_in','official','staff',
                         'mod','moderator','system','null','undefined','crew','team','you','me','everyone',
                         'anonymous','deleted','api','app']) then
    return jsonb_build_object('error', 'reserved');
  end if;
  insert into public.user_handles (user_id, username) values (v_uid, v_name)
    on conflict (user_id) do update set username = excluded.username;
  return jsonb_build_object('ok', true, 'username', v_name);
exception when unique_violation then
  return jsonb_build_object('error', 'taken');
end $$;

create or replace function public.crew_set_share(p_share jsonb) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_uid uuid := auth.uid();
  v_new jsonb;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  select jsonb_object_agg(k, case when jsonb_typeof(p_share -> k) = 'boolean' then (p_share -> k)::boolean else false end)
    into v_new
    from unnest(array['days','hours','proud','focus','habits']) as k;
  update public.user_handles set share = v_new where user_id = v_uid;
  if not found then return jsonb_build_object('error', 'need_username'); end if;
  return jsonb_build_object('ok', true, 'share', v_new);
end $$;

-- ---------------------------------------------------------------- crews
create or replace function public.crew_create(p_name text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_uid  uuid := auth.uid();
  v_name text := btrim(coalesce(p_name, ''));
  v_id   uuid;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  if char_length(v_name) not between 1 and 40 then return jsonb_build_object('error', 'invalid'); end if;
  if not exists (select 1 from public.user_handles where user_id = v_uid) then
    return jsonb_build_object('error', 'need_username');
  end if;
  perform pg_advisory_xact_lock(hashtextextended('crew_user:' || v_uid::text, 0));
  if public._crew_active_count(v_uid) >= 3 then return jsonb_build_object('error', 'crew_limit'); end if;
  insert into public.crews (name, created_by) values (v_name, v_uid) returning id into v_id;
  insert into public.crew_members (crew_id, user_id, role, status, joined_at)
    values (v_id, v_uid, 'owner', 'active', now());
  return jsonb_build_object('ok', true, 'crew_id', v_id);
end $$;

create or replace function public.crew_invite(p_crew uuid, p_username text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_uid    uuid := auth.uid();
  v_name   text := lower(btrim(coalesce(p_username, '')));
  v_target uuid;
  v_cnt    int;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  if not exists (select 1 from public.crew_members where crew_id = p_crew and user_id = v_uid and status = 'active') then
    return jsonb_build_object('error', 'not_found');
  end if;
  perform pg_advisory_xact_lock(hashtextextended('crew:' || p_crew::text, 0));
  delete from public.crew_members
    where crew_id = p_crew and status = 'invited' and created_at < now() - interval '14 days';
  select user_id into v_target from public.user_handles where username = v_name;
  if v_target is null then return jsonb_build_object('error', 'not_found'); end if;
  if v_target = v_uid then return jsonb_build_object('error', 'self'); end if;
  if public._crew_blocked(v_uid, v_target) then return jsonb_build_object('ok', true); end if;  -- silent
  if exists (select 1 from public.crew_members where crew_id = p_crew and user_id = v_target) then
    return jsonb_build_object('error', 'already');
  end if;
  select count(*) into v_cnt from public.crew_members where crew_id = p_crew;  -- active + live invites
  if v_cnt >= 6 then return jsonb_build_object('error', 'crew_full'); end if;
  insert into public.crew_members (crew_id, user_id, role, status, invited_by)
    values (p_crew, v_target, 'member', 'invited', v_uid);
  return jsonb_build_object('ok', true);
end $$;

create or replace function public.crew_respond(p_crew uuid, p_accept boolean) returns jsonb
language plpgsql security definer set search_path = public as $$
declare v_uid uuid := auth.uid();
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  perform pg_advisory_xact_lock(hashtextextended('crew_user:' || v_uid::text, 0));
  perform pg_advisory_xact_lock(hashtextextended('crew:' || p_crew::text, 0));
  if not exists (
    select 1 from public.crew_members
    where crew_id = p_crew and user_id = v_uid and status = 'invited' and created_at >= now() - interval '14 days'
  ) then
    return jsonb_build_object('error', 'not_found');
  end if;
  if not coalesce(p_accept, false) then   -- ignoring is silent: the row just disappears
    delete from public.crew_members where crew_id = p_crew and user_id = v_uid;
    return jsonb_build_object('ok', true);
  end if;
  if public._crew_active_count(v_uid) >= 3 then return jsonb_build_object('error', 'crew_limit'); end if;
  if (select count(*) from public.crew_members where crew_id = p_crew and status = 'active') >= 6 then
    return jsonb_build_object('error', 'crew_full');
  end if;
  update public.crew_members set status = 'active', joined_at = now() where crew_id = p_crew and user_id = v_uid;
  return jsonb_build_object('ok', true, 'crew_id', p_crew);
end $$;

create or replace function public.crew_make_code(p_crew uuid, p_revoke boolean default false) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_uid  uuid := auth.uid();
  v_code text;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  if not exists (
    select 1 from public.crew_members
    where crew_id = p_crew and user_id = v_uid and role = 'owner' and status = 'active'
  ) then
    return jsonb_build_object('error', 'forbidden');
  end if;
  if coalesce(p_revoke, false) then
    update public.crews set invite_code = null, invite_expires_at = null, updated_at = now() where id = p_crew;
    return jsonb_build_object('ok', true);
  end if;
  v_code := substr(replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''), 1, 24);
  update public.crews
    set invite_code = v_code, invite_expires_at = now() + interval '7 days', updated_at = now()
    where id = p_crew;
  return jsonb_build_object('ok', true, 'code', v_code, 'expires_at', now() + interval '7 days');
end $$;

create or replace function public.crew_join_code(p_code text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_uid  uuid := auth.uid();
  v_crew uuid;
  v_cnt  int;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  select id into v_crew from public.crews
    where invite_code = lower(btrim(coalesce(p_code, ''))) and invite_expires_at > now();
  if v_crew is null then return jsonb_build_object('error', 'not_found'); end if;
  if not exists (select 1 from public.user_handles where user_id = v_uid) then
    return jsonb_build_object('error', 'need_username');
  end if;
  perform pg_advisory_xact_lock(hashtextextended('crew_user:' || v_uid::text, 0));
  perform pg_advisory_xact_lock(hashtextextended('crew:' || v_crew::text, 0));
  if exists (select 1 from public.crew_members where crew_id = v_crew and user_id = v_uid and status = 'active') then
    return jsonb_build_object('ok', true, 'crew_id', v_crew);
  end if;
  if public._crew_active_count(v_uid) >= 3 then return jsonb_build_object('error', 'crew_limit'); end if;
  delete from public.crew_members
    where crew_id = v_crew and status = 'invited' and created_at < now() - interval '14 days';
  select count(*) into v_cnt from public.crew_members where crew_id = v_crew and user_id <> v_uid;
  if v_cnt >= 6 then return jsonb_build_object('error', 'crew_full'); end if;
  insert into public.crew_members (crew_id, user_id, role, status, joined_at)
    values (v_crew, v_uid, 'member', 'active', now())
    on conflict (crew_id, user_id) do update set status = 'active', joined_at = now();
  return jsonb_build_object('ok', true, 'crew_id', v_crew);
end $$;

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

create or replace function public.crew_set_quiet(p_crew uuid, p_quiet boolean) returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then return jsonb_build_object('error', 'unauthorized'); end if;
  update public.crew_members set quiet = coalesce(p_quiet, false)
    where crew_id = p_crew and user_id = auth.uid() and status = 'active';
  if not found then return jsonb_build_object('error', 'not_found'); end if;
  return jsonb_build_object('ok', true);
end $$;

-- ---------------------------------------------------------------- blocks
create or replace function public.crew_block(p_username text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_uid    uuid := auth.uid();
  v_target uuid;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  select user_id into v_target from public.user_handles where username = lower(btrim(coalesce(p_username, '')));
  if v_target is null then return jsonb_build_object('error', 'not_found'); end if;
  if v_target = v_uid then return jsonb_build_object('error', 'self'); end if;
  insert into public.user_blocks (blocker_id, blocked_id) values (v_uid, v_target) on conflict do nothing;
  delete from public.crew_members
    where status = 'invited'
      and ((user_id = v_target and invited_by = v_uid) or (user_id = v_uid and invited_by = v_target));
  return jsonb_build_object('ok', true);
end $$;

create or replace function public.crew_unblock(p_username text) returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then return jsonb_build_object('error', 'unauthorized'); end if;
  delete from public.user_blocks
    where blocker_id = auth.uid()
      and blocked_id = (select user_id from public.user_handles where username = lower(btrim(coalesce(p_username, ''))));
  return jsonb_build_object('ok', true);
end $$;

-- ---------------------------------------------------------------- one-call overview for the Crew panel
create or replace function public.crew_overview() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  v_uid   uuid := auth.uid();
  v_name  text;
  v_share jsonb;
  v_crews jsonb;
  v_inv   jsonb;
  v_blk   jsonb;
begin
  if v_uid is null then return jsonb_build_object('error', 'unauthorized'); end if;
  select username, share into v_name, v_share from public.user_handles where user_id = v_uid;

  select coalesce(jsonb_agg(jsonb_build_object(
      'id', c.id, 'name', c.name, 'role', m.role, 'quiet', m.quiet,
      'invite_code', case when m.role = 'owner' and c.invite_expires_at > now() then c.invite_code end,
      'invite_expires_at', case when m.role = 'owner' and c.invite_expires_at > now() then c.invite_expires_at end,
      'members', (
        select coalesce(jsonb_agg(jsonb_build_object(
                 'username', h.username, 'role', mm.role, 'status', mm.status, 'is_me', mm.user_id = v_uid
               ) order by mm.status, h.username), '[]'::jsonb)
        from public.crew_members mm join public.user_handles h on h.user_id = mm.user_id
        where mm.crew_id = c.id and (mm.status = 'active' or mm.created_at >= now() - interval '14 days')
      )
    ) order by c.created_at), '[]'::jsonb)
  into v_crews
  from public.crew_members m join public.crews c on c.id = m.crew_id
  where m.user_id = v_uid and m.status = 'active';

  select coalesce(jsonb_agg(jsonb_build_object(
      'crew_id', c.id, 'crew_name', c.name, 'from_username', h.username, 'created_at', m.created_at
    ) order by m.created_at desc), '[]'::jsonb)
  into v_inv
  from public.crew_members m
  join public.crews c on c.id = m.crew_id
  left join public.user_handles h on h.user_id = m.invited_by
  where m.user_id = v_uid and m.status = 'invited' and m.created_at >= now() - interval '14 days';

  select coalesce(jsonb_agg(h.username order by h.username), '[]'::jsonb)
  into v_blk
  from public.user_blocks b join public.user_handles h on h.user_id = b.blocked_id
  where b.blocker_id = v_uid;

  return jsonb_build_object(
    'username', v_name, 'share', coalesce(v_share, '{}'::jsonb),
    'crews', v_crews, 'invites', v_inv, 'blocks', v_blk
  );
end $$;

-- ---------------------------------------------------------------- grants: execute only for signed-in users
revoke all on function public._crew_blocked(uuid, uuid), public._crew_active_count(uuid) from public, anon, authenticated;

revoke all on function public.crew_set_username(text) from public, anon;
revoke all on function public.crew_set_share(jsonb) from public, anon;
revoke all on function public.crew_create(text) from public, anon;
revoke all on function public.crew_invite(uuid, text) from public, anon;
revoke all on function public.crew_respond(uuid, boolean) from public, anon;
revoke all on function public.crew_make_code(uuid, boolean) from public, anon;
revoke all on function public.crew_join_code(text) from public, anon;
revoke all on function public.crew_leave(uuid) from public, anon;
revoke all on function public.crew_set_quiet(uuid, boolean) from public, anon;
revoke all on function public.crew_block(text) from public, anon;
revoke all on function public.crew_unblock(text) from public, anon;
revoke all on function public.crew_overview() from public, anon;

grant execute on function public.crew_set_username(text) to authenticated;
grant execute on function public.crew_set_share(jsonb) to authenticated;
grant execute on function public.crew_create(text) to authenticated;
grant execute on function public.crew_invite(uuid, text) to authenticated;
grant execute on function public.crew_respond(uuid, boolean) to authenticated;
grant execute on function public.crew_make_code(uuid, boolean) to authenticated;
grant execute on function public.crew_join_code(text) to authenticated;
grant execute on function public.crew_leave(uuid) to authenticated;
grant execute on function public.crew_set_quiet(uuid, boolean) to authenticated;
grant execute on function public.crew_block(text) to authenticated;
grant execute on function public.crew_unblock(text) to authenticated;
grant execute on function public.crew_overview() to authenticated;
