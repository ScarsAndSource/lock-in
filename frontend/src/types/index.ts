export type Domain = 'habit' | 'screen_time' | 'urge' | 'study' | 'sleep';

export type HabitStatus = 'done' | 'skipped' | 'partial' | 'floor' | 'stretch';

export type ScreenTimeSource = 'manual' | 'extension' | 'screenshot' | 'automation';

export type UrgeOutcome = 'resisted' | 'relapsed';

export type GoalStatus = 'active' | 'archived';

export type MissionStatus = 'active' | 'completed' | 'ended_early';

export type WeekMode = 'auto' | 'rough' | 'normal';

export type InsightFeedback = 'accurate' | 'not_quite' | 'unsure';

export type PausePreset = 'today' | '3_days' | 'this_week' | '1_week' | '2_weeks';

export interface WeekdaysFrequency {
  type: 'weekdays';
  days: number[]; // 0=Mon ... 6=Sun
}

export interface NPerWeekFrequency {
  type: 'n_per_week';
  count: number;
}

export type TargetFrequency = WeekdaysFrequency | NPerWeekFrequency;

export interface Habit {
  id: string;
  name: string;
  target_frequency: TargetFrequency;
  archived_at: string | null;
  floor_text?: string | null;
  stretch_text?: string | null;
}

export interface HabitLog {
  habit_id: string;
  log_date: string;
  status: HabitStatus;
  note: string | null;
  is_default: boolean;
}

export interface MoodEntry {
  valence: number; // 1 rough .. 5 great
  energy: number; // 1 drained .. 5 buzzing
}

export interface MoodLog extends MoodEntry {
  log_date: string;
}

export interface SleepLog {
  log_date: string;
  time_to_bed: string | null;
  time_woke: string | null;
  self_rated_quality: number | null;
  duration_minutes: number | null;
  is_default: boolean;
}

export interface SleepProposal {
  time_to_bed: string | null;
  time_woke: string | null;
  self_rated_quality: number | null;
  based_on_count: number;
  is_low_confidence: boolean;
  reason: string;
}

export interface ScreenTimeLog {
  log_date: string;
  total_minutes: number;
  source: ScreenTimeSource;
  category_breakdown: Record<string, number> | null;
  is_default: boolean;
}

export interface ScreenTimeProposal {
  total_minutes: number;
  based_on_count: number;
  is_low_confidence: boolean;
  reason: string;
}

export interface Subject {
  id: string;
  name: string;
  archived_at: string | null;
}

export interface StudySession {
  id: string;
  log_date: string;
  subject_id: string;
  subject_name: string;
  planned_minutes: number | null;
  actual_minutes: number;
}

export interface SubjectMinutes {
  subject_id: string;
  name: string;
  minutes: number;
}

export interface StudySummary {
  start_date: string;
  end_date: string;
  total_actual: number;
  total_planned: number;
  follow_through_pct: number | null;
  days_studied: number;
  by_subject: SubjectMinutes[];
}

export interface UrgeLog {
  id: string;
  occurred_at: string;
  log_date: string;
  outcome: UrgeOutcome;
  intensity: number | null;
  has_detail: boolean;
  trigger_context?: string | null;
  coping_strategy?: string | null;
  note?: string | null;
  queued?: boolean;
  support?: SupportPayload | null;
}

export interface UrgeSummary {
  end_date: string;
  window_days: number;
  total: number;
  resisted: number;
  relapsed: number;
  resist_rate_pct: number | null;
  relapse_free_days_pct: number | null;
  prev_resist_rate_pct: number | null;
}

export interface CheckinEntry {
  habit_id: string;
  habit_name: string;
  status: HabitStatus | null;
  is_default: boolean;
  is_low_confidence: boolean;
  reason: string;
  is_scheduled: boolean;
  floor_text?: string | null;
  stretch_text?: string | null;
}

/** Set when yesterday's last scheduled day slipped: today's proposals are already lowered to the floor. */
export interface Bounce {
  active: boolean;
  slip_streak: number;
  tone: 'direct' | 'coach';
  title: string | null;
  message: string | null;
}

export interface SleepSection {
  logged: SleepLog | null;
  proposal: SleepProposal | null;
}

export interface ScreenTimeSection {
  logged: ScreenTimeLog | null;
  proposal: ScreenTimeProposal | null;
}

export interface CheckinView {
  checkin_date: string;
  already_confirmed: boolean;
  entries: CheckinEntry[];
  sleep: SleepSection;
  screen_time: ScreenTimeSection;
  bounce?: Bounce;
  mood?: MoodLog | null;
  from_cache?: boolean;
}

export interface CheckinOverride {
  habit_id: string;
  status: HabitStatus;
  note?: string | null;
}

export interface CheckinConfirmRequest {
  overrides?: CheckinOverride[];
  journal_text?: string | null;
  sleep?: {
    time_to_bed?: string | null;
    time_woke?: string | null;
    self_rated_quality?: number | null;
  } | null;
  screen_time?: {
    total_minutes: number;
    source?: ScreenTimeSource;
    category_breakdown?: Record<string, number> | null;
  } | null;
  mood?: MoodEntry | null; // omit/null = leave today's mood untouched
  accept_sleep_default?: boolean;
  accept_screen_time_default?: boolean;
}

export interface SupportResource {
  name: string;
  contact: string;
  detail: string;
}

export interface SupportPayload {
  region: string;
  message: string;
  resources: SupportResource[];
  verified_on: string;
}

export interface CheckinConfirmResponse {
  checkin_date: string;
  confirmed_at: string;
  entries: CheckinEntry[];
  sleep: SleepLog | null;
  screen_time: ScreenTimeLog | null;
  mood?: MoodLog | null;
  support?: SupportPayload | null;
  queued?: boolean;
}

export interface HabitConsistency {
  habit_id: string;
  habit_name: string;
  consistency_pct: number | null;
  coverage_pct: number | null;
  longest_run: number;
  current_run: number;
  run_unit: 'days' | 'weeks';
  comeback_rate: number | null;
}

export interface ConsistencyOut {
  end_date: string;
  window_days: number;
  overall_pct: number | null;
  habits: HabitConsistency[];
}

export type ChainDomainStatus = 'good' | 'partial' | 'missed' | 'none';

/** Raw backend values: good | ok | bad | none (mapped to ChainDomainStatus in the UI). */
export type ChainBackendStatus = 'good' | 'ok' | 'bad' | 'none' | ChainDomainStatus;

export interface ChainDay {
  day: string;
  habits: ChainBackendStatus;
  sleep: ChainBackendStatus;
  screen_time: ChainBackendStatus;
  study?: ChainBackendStatus;
  urges?: ChainBackendStatus;
  habit_ratio: number | null;
  sleep_minutes: number | null;
  screen_minutes: number | null;
  sleep_defaulted: boolean;
  screen_time_defaulted: boolean;
  habits_defaulted: boolean;
}

export interface ChainOut {
  end_date: string;
  days: ChainDay[];
}

export interface Pattern {
  key: string;
  trigger: string;
  outcome: string;
  lag_days: number;
  trigger_days: number;
  hits: number;
  rate_after_trigger: number;
  baseline_days: number;
  baseline_rate: number;
  evidence_dates: string[];
  statement: string;
}

export interface PatternsOut {
  end_date: string;
  days: number;
  patterns: Pattern[];
}

export interface Insight {
  id: string;
  generated_on: string;
  generated_at: string;
  pattern_key: string;
  insight_text: string;
  next_step: string;
  source_domains: string[];
  narrated: boolean;
  user_feedback: InsightFeedback | null;
}

export interface WeekModeInfo {
  mode: 'normal' | 'rough';
  reasons: string[];
  source: 'auto' | 'user';
}

export interface Retro {
  id: string;
  week_start: string;
  week_end: string;
  generated_at: string;
  narrative: string;
  next_step: string;
  summary: Record<string, any>;
  evidence_refs: Record<string, any>;
  narrated: boolean;
  completed_at: string | null;
  week_mode?: WeekModeInfo | null;
}

export interface RetroDetail extends Retro {
  status: 'ready' | 'completed';
  pending_ratings: Insight[];
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  next_step?: string | null;
  mode?: 'answer' | 'support' | 'no_data' | 'fallback' | 'action' | null;
  actions?: ActionCard[];
  cited_days: string[];
  narrated: boolean;
  model?: string | null;
  created_at: string;
}

export interface Thread {
  id: string;
  title: string;
  created_at: string;
  last_message_at: string;
  message_count: number;
}

export interface ThreadDetail {
  thread: Thread;
  messages: ChatMessage[];
  has_more: boolean;
  support?: SupportPayload | null;
}

export interface Goal {
  id: string;
  domain: Domain;
  definition: string;
  target: Record<string, any>;
  status: GoalStatus;
  created_at: string;
}

export interface GoalProgress {
  goal: Goal;
  current: number | null;
  target_value: number;
  unit: string;
  on_track: boolean | null;
  detail: string;
}

export interface Intention {
  id: string;
  linked_domain: Domain;
  linked_entity_id: string | null;
  cue: string;
  action: string;
  active: boolean;
  created_at: string;
}

export interface DueIntention {
  intention: Intention;
  level: 'full' | 'light';
  reason: string;
}

export interface Mission {
  id: string;
  title: string;
  start_date: string;
  end_date: string;
  status: MissionStatus;
  ended_at: string | null;
}

export interface Checkpoint {
  label: string;
  day: number;
  checkpoint_date: string;
}

export interface MissionDetail {
  mission: Mission;
  progress: {
    state: 'upcoming' | 'running' | 'finished';
    day_number: number;
    days_total: number;
    days_left: number;
    elapsed_pct: number;
    phase: string | null;
    next_checkpoint: Checkpoint | null;
  };
  consistency_pct: number | null;
  habits: HabitConsistency[];
}

export interface PauseItem {
  id: string;
  start_date: string;
  end_date: string;
  active: boolean;
  habit_id: string | null;
}

export interface PauseShortcut {
  key: PausePreset;
  label: string;
  start_date: string;
  end_date: string;
  days: number;
}

export interface HabitPauseRow {
  habit_id: string;
  name: string;
  state: 'active' | 'paused' | 'upcoming';
  effective_paused: boolean;
  paused_by: 'habit' | 'all' | null;
  pause: PauseItem | null;
}

export interface PauseOverview {
  today: string;
  global_pause: PauseItem | null;
  habits: HabitPauseRow[];
}

export type TonePreference = 'auto' | 'direct' | 'coach';

export interface Profile {
  timezone: string;
  tone_preference: string;
  today: string;
}

// ---------------------------------------------------------------- tasks, reminders, nudges
export type TaskState = 'backlog' | 'upcoming' | 'due' | 'stale' | 'snoozed' | 'done' | 'dropped';

export interface Task {
  id: string;
  title: string;
  notes: string | null;
  importance: 1 | 2 | 3; // 1 small chore, 2 normal, 3 real deadline
  status: 'open' | 'done' | 'dropped';
  state: TaskState;
  due: string | null; // local "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM"
  due_has_time: boolean;
  remind: string | null; // local "YYYY-MM-DDTHH:MM"
  repeat_days: number | null;
  snoozed_until: string | null;
  nudge_count: number;
  last_done_at: string | null;
  done_count: number;
  ai_parsed: boolean;
  created_at: string;
}

export interface TaskCaptureResult {
  mode: 'parsed' | 'fallback' | 'support';
  tasks: Task[];
  skipped_duplicates: number;
  support: SupportPayload | null;
}

export interface TaskFocus {
  now: Task[];
  small: Task[];
  later_today: Task[];
  stale: Task[];
  hidden_now: number;
  backlog_count: number;
}

export interface NotificationPrefs {
  push_enabled: boolean;
  quiet_start: string; // "HH:MM:SS"
  quiet_end: string;
  nudge_hour: number;
  max_per_day: number;
  devices: number;
  push_available: boolean;
  companion_enabled: boolean;
  checkin_hour: number;
  plan_cues_in_quiet: boolean;
  discreet_push: boolean;
}

/** What the Companion did (applied, with an undo payload) or wants to do (pending, with args to confirm). */
export interface ActionCard {
  id: string;
  tool: string;
  status: 'applied' | 'pending' | 'failed';
  summary: string;
  reason?: string | null;
  args?: Record<string, unknown> | null;
  undo?: Record<string, unknown> | null;
}
