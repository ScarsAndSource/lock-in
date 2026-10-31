-- Lock'in — migration 028: AI security events (what was detected, never what was said). Idempotent.
-- Written by the API's audit sink (app/audit_sql.py) as the connection owner; read by the operator.
-- RLS is ON with NO policy: the `authenticated` role (every user request) can neither read nor write it.
create table if not exists public.ai_security_events (
    id bigint generated always as identity primary key,
    user_id uuid references auth.users(id) on delete cascade,   -- null for system events (global ceiling)
    kind text not null check (char_length(kind) between 1 and 48),
    severity text not null check (severity in ('info', 'warn', 'high', 'review')),
    meta jsonb not null default '{}'::jsonb,                    -- counts, category codes, keyed hashes; never text
    request_id text,
    created_at timestamptz not null default now()
);

create index if not exists ai_security_events_user_idx on public.ai_security_events (user_id, created_at desc);
create index if not exists ai_security_events_created_idx on public.ai_security_events (created_at);
create index if not exists ai_security_events_review_idx on public.ai_security_events (created_at desc)
    where severity in ('high', 'review');

alter table public.ai_security_events enable row level security;
revoke all on public.ai_security_events from anon, authenticated;
