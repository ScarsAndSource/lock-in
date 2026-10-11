-- Lock'in — migration 012: per-habit pauses. habit_id NULL = pauses everything (the old behavior). Idempotent.
alter table public.pauses add column if not exists habit_id uuid;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'habit_definitions_id_user_key') then
    alter table public.habit_definitions add constraint habit_definitions_id_user_key unique (id, user_id);
  end if;

  -- composite FK: a pause can only point at a habit owned by the same user.
  -- (With habit_id NULL the FK is not checked, so global pauses are unaffected.)
  if not exists (select 1 from pg_constraint where conname = 'pauses_habit_owner_fk') then
    alter table public.pauses add constraint pauses_habit_owner_fk
      foreign key (habit_id, user_id) references public.habit_definitions (id, user_id) on delete cascade;
  end if;
end $$;

create index if not exists pauses_user_habit_idx on public.pauses (user_id, habit_id) where habit_id is not null;
