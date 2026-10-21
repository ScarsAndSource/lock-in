import { request, isDemoMode } from './client';
import { qs } from '../lib/dates';

export type ExperimentMetric = 'sleep_hours' | 'screen_minutes' | 'mood' | 'habit_ratio' | 'task_rate';
export type VerdictKind = 'helped' | 'hurt' | 'no_clear_effect' | 'not_enough_data' | 'not_followed';
export type Adherence = 'mostly' | 'partly' | 'barely';

export interface MetricInfo {
  key: ExperimentMetric;
  label: string;
  unit: string;
  better: 'higher' | 'lower';
  usable_days: number;
}

export interface ExperimentPoint {
  day: string;
  value: number | null;
  phase: 'baseline' | 'test';
}

export interface ExperimentVerdict {
  kind: VerdictKind;
  sentence: string;
  n_baseline: number;
  n_treatment: number;
  baseline_mean: number | null;
  treatment_mean: number | null;
  delta: number | null;
  p_value: number | null;
  effect_size: number | null;
  caveats: string[];
}

export interface Experiment {
  id: string;
  title: string;
  change: string;
  metric: ExperimentMetric;
  metric_label: string;
  unit: string;
  direction: 'higher' | 'lower';
  status: 'active' | 'done' | 'abandoned';
  start_date: string;
  end_date: string;
  baseline_days: number;
  treatment_days: number;
  phase: 'waiting' | 'running' | 'complete';
  day_number: number;
  days_left: number;
  provisional: boolean;
  verdict: ExperimentVerdict | null;
  points: ExperimentPoint[];
}

export interface StartExperimentBody {
  title: string;
  change: string;
  metric: ExperimentMetric;
  direction?: 'higher' | 'lower';
  baseline_days?: number;
  treatment_days?: number;
  start?: 'today' | 'tomorrow';
}

const DEMO_MSG = 'Experiments need a live account (demo data has nothing to compare against).';

const DEMO_METRICS: MetricInfo[] = [
  { key: 'sleep_hours', label: 'Sleep', unit: 'h', better: 'higher', usable_days: 14 },
  { key: 'screen_minutes', label: 'Screen time', unit: 'min', better: 'lower', usable_days: 14 },
  { key: 'mood', label: 'Mood', unit: '/5', better: 'higher', usable_days: 14 },
  { key: 'habit_ratio', label: 'Habit completion', unit: '%', better: 'higher', usable_days: 14 },
  { key: 'task_rate', label: 'Tasks done', unit: '%', better: 'higher', usable_days: 0 },
];

export async function getExperimentMetrics(): Promise<MetricInfo[]> {
  if (isDemoMode()) return DEMO_METRICS;
  return request<MetricInfo[]>('/experiments/metrics');
}

export async function getActiveExperiment(): Promise<Experiment | null> {
  if (isDemoMode()) return null;
  return request<Experiment | null>('/experiments/active');
}

export async function listExperiments(limit: number = 20): Promise<Experiment[]> {
  if (isDemoMode()) return [];
  return request<Experiment[]>(`/experiments${qs({ limit })}`);
}

export async function startExperiment(body: StartExperimentBody): Promise<Experiment> {
  if (isDemoMode()) throw new Error(DEMO_MSG);
  return request<Experiment>('/experiments', { method: 'POST', body: JSON.stringify(body) });
}

export async function finishExperiment(id: string, adherence: Adherence): Promise<Experiment> {
  if (isDemoMode()) throw new Error(DEMO_MSG);
  return request<Experiment>(`/experiments/${id}/finish`, { method: 'POST', body: JSON.stringify({ adherence }) });
}

export async function abandonExperiment(id: string): Promise<void> {
  if (isDemoMode()) throw new Error(DEMO_MSG);
  await request<void>(`/experiments/${id}/abandon`, { method: 'POST' });
}
