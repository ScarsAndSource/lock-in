-- Lock'in — migration 014 (Batch A: three-tier habits, tone dial)
-- Idempotent. No new tables, so no new RLS policies or grants are needed
-- (existing table-level grants and policies cover new columns).
-- If your repo already has a 014, rename this file to the next free number.

-- ------------------------------------------------------------
-- 1. Three-tier habits: floor / target (done) / stretch
--    habit_logs.status gains 'floor' and 'stretch'. 'partial' stays valid
--    so every old log keeps working.
-- ------------------------------------------------------------
alter table public.habit_logs drop constraint if exists habit_logs_status_check;
alter table public.habit_logs
  add constraint habit_logs_status_check
  check (status in ('done', 'skipped', 'partial', 'floor', 'stretch'));

-- Optional plain-language definitions of the tiers, e.g. floor "10 min walk",
-- stretch "full 60 min session". The habit name itself is the target.
alter table public.habit_definitions add column if not exists floor_text text;
alter table public.habit_definitions add column if not exists stretch_text text;

alter table public.habit_definitions drop constraint if exists habit_definitions_floor_text_len;
alter table public.habit_definitions
  add constraint habit_definitions_floor_text_len
  check (floor_text is null or char_length(floor_text) between 1 and 120);

alter table public.habit_definitions drop constraint if exists habit_definitions_stretch_text_len;
alter table public.habit_definitions
  add constraint habit_definitions_stretch_text_len
  check (stretch_text is null or char_length(stretch_text) between 1 and 120);

-- ------------------------------------------------------------
-- 2. Tone dial: auto | direct | coach
--    Until now 'direct' was the only allowed value, so nobody ever chose it.
--    Existing rows move to 'auto' (blunt by default, gentler after rough days).
--    'direct' becomes a real choice meaning "always blunt".
-- ------------------------------------------------------------
alter table public.profiles drop constraint if exists profiles_tone_preference_check;
alter table public.profiles alter column tone_preference set default 'auto';
update public.profiles set tone_preference = 'auto' where tone_preference = 'direct';
alter table public.profiles
  add constraint profiles_tone_preference_check
  check (tone_preference in ('auto', 'direct', 'coach'));
