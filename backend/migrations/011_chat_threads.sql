-- Lock'in — migration 011: stored chat threads (encrypted at rest). Idempotent.
create table if not exists public.chat_threads (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    title_encrypted bytea,
    last_message_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint chat_threads_id_user_key unique (id, user_id)
);

create index if not exists chat_threads_user_last_idx on public.chat_threads (user_id, last_message_at desc);

create table if not exists public.chat_messages (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    thread_id uuid not null,
    role text not null check (role in ('user', 'assistant')),
    content_encrypted bytea not null,
    next_step_encrypted bytea,
    meta jsonb not null default '{}'::jsonb, -- {mode, cited_days, narrated, model}: no free text
    created_at timestamptz not null,
    -- composite FK: a message can only live in a thread owned by the SAME user
    constraint chat_messages_thread_owner_fk foreign key (thread_id, user_id) references public.chat_threads (id, user_id) on delete cascade
);

create index if not exists chat_messages_thread_created_idx on public.chat_messages (thread_id, created_at);

alter table public.chat_threads enable row level security;
alter table public.chat_messages enable row level security;

drop policy if exists "chat_threads_owner_all" on public.chat_threads;
create policy "chat_threads_owner_all" on public.chat_threads
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "chat_messages_owner_all" on public.chat_messages;
create policy "chat_messages_owner_all" on public.chat_messages
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop trigger if exists chat_threads_set_updated_at on public.chat_threads;
create trigger chat_threads_set_updated_at
    before update on public.chat_threads
    for each row execute function set_updated_at();

grant select, insert, update, delete on public.chat_threads, public.chat_messages to authenticated;
