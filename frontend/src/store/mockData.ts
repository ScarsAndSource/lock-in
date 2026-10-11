import type {
  Habit,
  CheckinView,
  Subject,
  StudySession,
  UrgeLog,
  UrgeSummary,
  ConsistencyOut,
  ChainOut,
  PatternsOut,
  Insight,
  RetroDetail,
  Thread,
  ChatMessage,
  Intention,
  MissionDetail,
  PauseShortcut,
  PauseOverview,
  Profile,
} from '../types';

export const INITIAL_PROFILE: Profile = {
  timezone: 'Asia/Kolkata',
  tone_preference: 'direct',
  today: '2026-12-31',
};

export const INITIAL_HABITS: Habit[] = [
  {
    id: 'habit-1',
    name: 'Gym: upper body push',
    target_frequency: { type: 'n_per_week', count: 5 },
    archived_at: null,
  },
  {
    id: 'habit-2',
    name: 'Reading / Research review',
    target_frequency: { type: 'weekdays', days: [0, 1, 2, 3, 4] },
    archived_at: null,
  },
  {
    id: 'habit-3',
    name: 'No screens past 11:15 pm',
    target_frequency: { type: 'n_per_week', count: 7 },
    archived_at: null,
  },
];

export const INITIAL_CHECKIN_VIEW: CheckinView = {
  checkin_date: '2026-12-31',
  already_confirmed: false,
  entries: [
    {
      habit_id: 'habit-1',
      habit_name: 'Gym: same as usual.',
      status: 'done',
      is_default: true,
      is_low_confidence: false,
      reason: 'Logged done 4 of last 5 Thursdays',
      is_scheduled: true,
    },
    {
      habit_id: 'habit-2',
      habit_name: 'Reading / Research review',
      status: 'partial',
      is_default: true,
      is_low_confidence: false,
      reason: 'Thursday schedule pattern',
      is_scheduled: true,
    },
    {
      habit_id: 'habit-3',
      habit_name: 'No screens past 11:15 pm',
      status: null,
      is_default: false,
      is_low_confidence: true,
      reason: 'Awaiting day close',
      is_scheduled: true,
    },
  ],
  sleep: {
    logged: {
      log_date: '2026-12-31',
      time_to_bed: '23:30',
      time_woke: '06:45',
      self_rated_quality: 4,
      duration_minutes: 435,
      is_default: false,
    },
    proposal: {
      time_to_bed: '23:30',
      time_woke: '06:45',
      self_rated_quality: 4,
      based_on_count: 14,
      is_low_confidence: false,
      reason: 'Median bedtime across last 14 days',
    },
  },
  screen_time: {
    logged: {
      log_date: '2026-12-31',
      total_minutes: 190,
      source: 'manual',
      category_breakdown: { Productivity: 120, Social: 45, Entertainment: 25 },
      is_default: true,
    },
    proposal: {
      total_minutes: 190,
      based_on_count: 7,
      is_low_confidence: true,
      reason: 'Calculated guess from weekday average',
    },
  },
};

export const INITIAL_CHAIN: ChainOut = {
  end_date: '2026-12-31',
  days: [
    {
      day: '2026-12-25',
      habits: 'good',
      sleep: 'good',
      screen_time: 'partial',
      habit_ratio: 1.0,
      sleep_minutes: 460,
      screen_minutes: 240,
      sleep_defaulted: false,
      screen_time_defaulted: false,
      habits_defaulted: false,
    },
    {
      day: '2026-12-26',
      habits: 'partial',
      sleep: 'good',
      screen_time: 'missed',
      habit_ratio: 0.5,
      sleep_minutes: 480,
      screen_minutes: 360,
      sleep_defaulted: false,
      screen_time_defaulted: false,
      habits_defaulted: false,
    },
    {
      day: '2026-12-27',
      habits: 'missed',
      sleep: 'partial',
      screen_time: 'good',
      habit_ratio: 0.0,
      sleep_minutes: 340,
      screen_minutes: 130,
      sleep_defaulted: false,
      screen_time_defaulted: false,
      habits_defaulted: false,
    },
    {
      day: '2026-12-28',
      habits: 'good',
      sleep: 'good',
      screen_time: 'good',
      habit_ratio: 1.0,
      sleep_minutes: 450,
      screen_minutes: 140,
      sleep_defaulted: false,
      screen_time_defaulted: false,
      habits_defaulted: false,
    },
    {
      day: '2026-12-29',
      habits: 'good',
      sleep: 'partial',
      screen_time: 'good',
      habit_ratio: 1.0,
      sleep_minutes: 390,
      screen_minutes: 160,
      sleep_defaulted: false,
      screen_time_defaulted: false,
      habits_defaulted: false,
    },
    {
      day: '2026-12-30',
      habits: 'good',
      sleep: 'good',
      screen_time: 'partial',
      habit_ratio: 0.8,
      sleep_minutes: 440,
      screen_minutes: 220,
      sleep_defaulted: false,
      screen_time_defaulted: false,
      habits_defaulted: false,
    },
    {
      day: '2026-12-31',
      habits: 'good',
      sleep: 'good',
      screen_time: 'partial',
      habit_ratio: 1.0,
      sleep_minutes: 435,
      screen_minutes: 190,
      sleep_defaulted: false,
      screen_time_defaulted: true,
      habits_defaulted: false,
    },
  ],
};

export const INITIAL_CONSISTENCY: ConsistencyOut = {
  end_date: '2026-12-31',
  window_days: 30,
  overall_pct: 84.6,
  habits: [
    {
      habit_id: 'habit-1',
      habit_name: 'Gym: upper body push',
      consistency_pct: 88.0,
      coverage_pct: 100.0,
      longest_run: 12,
      current_run: 5,
      run_unit: 'days',
      comeback_rate: 0.9,
    },
    {
      habit_id: 'habit-2',
      habit_name: 'Reading / Research review',
      consistency_pct: 79.2,
      coverage_pct: 95.0,
      longest_run: 8,
      current_run: 3,
      run_unit: 'days',
      comeback_rate: 0.8,
    },
    {
      habit_id: 'habit-3',
      habit_name: 'No screens past 11:15 pm',
      consistency_pct: 86.7,
      coverage_pct: 100.0,
      longest_run: 14,
      current_run: 4,
      run_unit: 'days',
      comeback_rate: 0.85,
    },
  ],
};

export const INITIAL_PATTERNS: PatternsOut = {
  end_date: '2026-12-31',
  days: 30,
  patterns: [
    {
      key: 'screen_spikes_lead_to_missed_gym',
      trigger: 'Late-night screen time > 120 min',
      outcome: 'Skipped next morning gym workout',
      lag_days: 1,
      trigger_days: 6,
      hits: 5,
      rate_after_trigger: 0.833,
      baseline_days: 24,
      baseline_rate: 0.125,
      evidence_dates: ['2026-12-26', '2026-12-20', '2026-12-14', '2026-12-08', '2026-12-02'],
      statement: 'You skipped gym 5 of the last 6 days when screen time exceeded 2 hours the night before.',
    },
    {
      key: 'low_sleep_triggers_urges',
      trigger: 'Sleep under 6 hours',
      outcome: 'Reported high-intensity urge spike',
      lag_days: 0,
      trigger_days: 5,
      hits: 4,
      rate_after_trigger: 0.8,
      baseline_days: 25,
      baseline_rate: 0.16,
      evidence_dates: ['2026-12-27', '2026-12-21', '2026-12-15', '2026-12-09'],
      statement: 'Sleep deprivation directly triples recorded craving occurrences on the following afternoon.',
    },
  ],
};

export const INITIAL_INSIGHTS: Insight[] = [
  {
    id: 'insight-1',
    generated_on: '2026-12-31',
    generated_at: '2026-12-31T08:00:00Z',
    pattern_key: 'screen_spikes_lead_to_missed_gym',
    insight_text: 'You skipped gym 4 of the last 5 days when you slept under 6 hours following a late-night phone session.',
    next_step: 'Set phone into charge mode at 10:45 pm outside arm reach.',
    source_domains: ['screen_time', 'sleep', 'habit'],
    narrated: true,
    user_feedback: null,
  },
  {
    id: 'insight-2',
    generated_on: '2026-12-30',
    generated_at: '2026-12-30T08:00:00Z',
    pattern_key: 'study_after_gym_highest_completion',
    insight_text: 'Study sessions booked immediately following morning exercise had a 94% planned-to-actual follow-through.',
    next_step: 'Protect the 10:00 am study window right after post-workout breakfast.',
    source_domains: ['study', 'habit'],
    narrated: true,
    user_feedback: 'accurate',
  },
];

export const INITIAL_RETRO: RetroDetail = {
  id: 'retro-w52',
  week_start: '2026-12-28',
  week_end: '2026-12-31',
  generated_at: '2026-12-31T20:00:00Z',
  narrative: 'Strong momentum on physical discipline with 4 clean gym sessions. Screen time crept up Tuesday and Wednesday nights, creating friction for Thursday morning focus. You resisted 3 distinct craving triggers without relapse.',
  next_step: 'Lock in sleep timing Friday night before the weekend shift.',
  summary: {
    gym_consistency: '88%',
    avg_sleep: '7h 12m',
    screen_total: '12.4h',
    urges_resisted: 4,
    urges_relapsed: 0,
  },
  evidence_refs: {
    days_examined: 7,
    key_turning_points: ['2026-12-28', '2026-12-30'],
  },
  narrated: true,
  completed_at: null,
  status: 'ready',
  week_mode: {
    mode: 'normal',
    reasons: ['Consistency above 80%', 'No consecutive misses'],
    source: 'auto',
  },
  pending_ratings: [INITIAL_INSIGHTS[0]],
};

export const INITIAL_SUBJECTS: Subject[] = [
  { id: 'subj-1', name: 'Algorithms & Data Structures', archived_at: null },
  { id: 'subj-2', name: 'AISC / Machine Learning', archived_at: null },
  { id: 'subj-3', name: 'Computer Networks', archived_at: null },
  { id: 'subj-4', name: 'Predictive Analytics', archived_at: null },
];

export const INITIAL_STUDY_SESSIONS: StudySession[] = [
  {
    id: 'sess-1',
    log_date: '2026-12-31',
    subject_id: 'subj-1',
    subject_name: 'Algorithms & Data Structures',
    planned_minutes: 90,
    actual_minutes: 85,
  },
  {
    id: 'sess-2',
    log_date: '2026-12-30',
    subject_id: 'subj-2',
    subject_name: 'AISC / Machine Learning',
    planned_minutes: 60,
    actual_minutes: 60,
  },
];

export const INITIAL_URGES: UrgeLog[] = [
  {
    id: 'urge-1',
    occurred_at: '2026-12-31T20:15:00Z',
    log_date: '2026-12-31',
    outcome: 'resisted',
    intensity: 6,
    has_detail: true,
    trigger_context: 'Tired after work and scrolling social feed',
    coping_strategy: 'Cold water wash and 10 pushups',
    note: 'Urge subsided within 8 minutes.',
  },
  {
    id: 'urge-2',
    occurred_at: '2026-12-30T22:40:00Z',
    log_date: '2026-12-30',
    outcome: 'resisted',
    intensity: 7,
    has_detail: true,
    trigger_context: 'Late night boredom',
    coping_strategy: 'Closed laptop immediately',
    note: 'Went directly to bed.',
  },
];

export const INITIAL_URGE_SUMMARY: UrgeSummary = {
  end_date: '2026-12-31',
  window_days: 14,
  total: 6,
  resisted: 5,
  relapsed: 1,
  resist_rate_pct: 83.3,
  relapse_free_days_pct: 92.8,
  prev_resist_rate_pct: 71.4,
};

export const INITIAL_INTENTIONS: Intention[] = [
  {
    id: 'intent-1',
    linked_domain: 'urge',
    linked_entity_id: null,
    cue: 'When I feel an urge to endlessly browse late at night',
    action: 'Place phone face-down across the room and drink a full glass of cold water',
    active: true,
    created_at: '2026-12-15T10:00:00Z',
  },
  {
    id: 'intent-2',
    linked_domain: 'study',
    linked_entity_id: 'subj-1',
    cue: 'If I feel like opening YouTube while working on Algorithms',
    action: 'Close the browser window, stand up for 60 seconds, and write down the next 1 tiny task',
    active: true,
    created_at: '2026-12-18T14:30:00Z',
  },
];

export const INITIAL_MISSION: MissionDetail = {
  mission: {
    id: 'miss-1',
    title: 'January 21-Day Lock-In Sprint',
    start_date: '2026-12-25',
    end_date: '2027-01-14',
    status: 'running',
    ended_at: null,
  },
  progress: {
    state: 'running',
    day_number: 7,
    days_total: 21,
    days_left: 14,
    elapsed_pct: 33.3,
    phase: 'Phase 1: Foundation Baseline',
    next_checkpoint: {
      label: 'Checkpoint 1 (Day 10 Audit)',
      day: 10,
      checkpoint_date: '2027-01-03',
    },
  },
  consistency_pct: 84.6,
  habits: INITIAL_CONSISTENCY.habits,
};

export const INITIAL_PAUSE_SHORTCUTS: PauseShortcut[] = [
  { key: 'today', label: 'Today only', start_date: '2026-12-31', end_date: '2026-12-31', days: 1 },
  { key: '3_days', label: '3 days (recovery)', start_date: '2026-12-31', end_date: '2027-01-02', days: 3 },
  { key: 'this_week', label: 'Rest of this week', start_date: '2026-12-31', end_date: '2027-01-03', days: 4 },
  { key: '1_week', label: '1 full week', start_date: '2026-12-31', end_date: '2027-01-06', days: 7 },
  { key: '2_weeks', label: '2 weeks (exam / travel)', start_date: '2026-12-31', end_date: '2027-01-13', days: 14 },
];

export const INITIAL_PAUSE_OVERVIEW: PauseOverview = {
  today: '2026-12-31',
  global_pause: null,
  habits: [
    {
      habit_id: 'habit-1',
      name: 'Gym: upper body push',
      state: 'active',
      effective_paused: false,
      paused_by: null,
      pause: null,
    },
    {
      habit_id: 'habit-2',
      name: 'Reading / Research review',
      state: 'active',
      effective_paused: false,
      paused_by: null,
      pause: null,
    },
    {
      habit_id: 'habit-3',
      name: 'No screens past 11:15 pm',
      state: 'active',
      effective_paused: false,
      paused_by: null,
      pause: null,
    },
  ],
};

export const INITIAL_THREADS: Thread[] = [
  {
    id: 'thread-1',
    title: 'Workout consistency vs. late sleep',
    created_at: '2026-12-30T14:00:00Z',
    last_message_at: '2026-12-31T09:30:00Z',
    message_count: 4,
  },
];

export const INITIAL_CHAT_MESSAGES: ChatMessage[] = [
  {
    id: 'msg-1',
    role: 'user',
    content: 'Why did I miss Thursday gym despite planning it?',
    cited_days: [],
    narrated: false,
    created_at: '2026-12-31T09:28:00Z',
  },
  {
    id: 'msg-2',
    role: 'assistant',
    content: 'Looking at your logged chain: your phone screen was active for 220 minutes Wednesday evening until 1:10 am. Your sleep duration dropped from your 7.5 hr baseline down to 5.2 hrs. In your data, whenever you sleep under 6 hrs, your morning workout completion is under 20%.',
    next_step: 'Place the phone across the room tonight at 10:45 pm.',
    mode: 'answer',
    cited_days: ['2026-12-30', '2026-12-26'],
    narrated: true,
    model: 'llama-3.3-70b-versatile',
    created_at: '2026-12-31T09:30:00Z',
  },
];
