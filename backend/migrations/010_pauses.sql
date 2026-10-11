-- Lock'in — migration 010: user pause periods (sick, travel, exam week). Idempotent.
create table if not exists public.pauses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  start_date date not null,
  end_date date not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists pauses_user_dates_idx on public.pauses (user_id, start_date, end_date);

alter table public.pauses enable row level security;
drop policy if exists "pauses_owner_all" on public.pauses;
create policy "pauses_owner_all" on public.pauses for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop trigger if exists pauses_set_updated_at on public.pauses;
create trigger pauses_set_updated_at
  before update on public.pauses
  for each row execute function set_updated_at();

grant select, insert, update, delete on public.pauses to authenticated;
