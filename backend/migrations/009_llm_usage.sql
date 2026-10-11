-- Lock'in — migration 009: per-user daily LLM usage (the cost cap). Idempotent.
create table if not exists public.llm_usage (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    usage_date date not null, -- UTC day
    feature text not null check (feature in ('chat', 'retro', 'insight')),
    calls integer not null default 0 check (calls >= 0),
    tokens integer not null default 0 check (tokens >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint llm_usage_user_day_feature unique (user_id, usage_date, feature)
);

create index if not exists llm_usage_user_day_idx on public.llm_usage (user_id, usage_date);

alter table public.llm_usage enable row level security;

drop policy if exists "llm_usage_owner_all" on public.llm_usage;
create policy "llm_usage_owner_all" on public.llm_usage
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop trigger if exists llm_usage_set_updated_at on public.llm_usage;
create trigger llm_usage_set_updated_at
    before update on public.llm_usage
    for each row execute function set_updated_at();

-- delete is needed: account deletion removes this table's rows too.
grant select, insert, update, delete on public.llm_usage to authenticated;
