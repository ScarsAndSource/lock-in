import { request, isDemoMode } from './client';
import type { SupportPayload } from '../types';

export const TOP_STAGE = 4;
export const SHOW_ALL_KEY = 'lockin.showAll';
export const STAGE_CACHE_KEY = 'lockin.stage';

export interface JourneySeason {
  id: string;
  name: string;
  start_date: string;
  phase: 'focus' | 'rest' | 'ended';
  week: number;
  days_left: number;
}

export interface JourneyState {
  stage: number;
  season: JourneySeason | null;
  focus_ids: string[];
  benched_ids: string[];
  slots: number;
  free_slots: number;
}

export interface RecallSet {
  id: string;
  label: string;
  topics: string[];
  exam_date: string | null;
  next_due: string | null;
  reviews_left: number;
  reviews_done: number;
}

export interface RecallDue {
  review_id: string;
  set_id: string;
  label: string;
  topics: string[];
  step: number;
  exam_date: string | null;
  days_to_exam: number | null;
}

export interface SnapshotScores {
  wellbeing: number;
  sleep: number;
  focus: number;
  becoming: number;
  automatic: number;
}

export interface SnapshotInput extends SnapshotScores {
  custom_label: string | null;
  custom_value: number | null;
}

export interface SnapshotDelta {
  days: number;
  snapshot_on: string | null;
  metrics: SnapshotScores | null;
  custom: { label: string; from: number; to: number; change: number } | null;
}

export interface SnapshotView {
  due: boolean;
  latest: (SnapshotScores & { taken_on: string; custom_label: string | null; custom_value: number | null }) | null;
  deltas: SnapshotDelta[];
  support: SupportPayload | null;
}

export interface ShelfItem {
  id: string;
  habit_id: string;
  name: string;
  graduated_on: string;
  days_on_shelf: number;
  check_due: 30 | 90 | null;
}

export interface ShelfOffer {
  habit_id: string;
  name: string;
  consistency_pct: number;
}

export interface ShelfView {
  offers: ShelfOffer[];
  shelf: ShelfItem[];
  checkin: { graduation_id: string; habit_name: string; which: 30 | 90 } | null;
}

export type JourneyNudgeData =
  | { kind: 'recall'; count: number; label: string }
  | { kind: 'shelf_check'; graduation_id: string; habit_name: string; which: 30 | 90 }
  | { kind: 'snapshot' }
  | { kind: 'graduate'; habit_id: string; name: string };

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });

const DEMO_STATE: JourneyState = {
  stage: TOP_STAGE, season: null, focus_ids: [], benched_ids: [], slots: 3, free_slots: 3,
};

export async function getJourneyState(): Promise<JourneyState> {
  if (isDemoMode()) return DEMO_STATE;
  return request<JourneyState>('/journey/state');
}

export const startSeason = (name: string | null, focusHabitIds: string[]) =>
  request<JourneyState>('/journey/season', { method: 'POST', ...json({ name, focus_habit_ids: focusHabitIds }) });
export const setFocus = (focusHabitIds: string[]) =>
  request<JourneyState>('/journey/season/focus', { method: 'PUT', ...json({ focus_habit_ids: focusHabitIds }) });

export async function getNudge(): Promise<JourneyNudgeData | null> {
  if (isDemoMode()) return null;
  return request<JourneyNudgeData | null>('/journey/nudge');
}

export const listRecall = () => request<RecallSet[]>('/journey/recall');
export const createRecall = (label: string, topics: string, examDate: string | null) =>
  request<RecallSet[]>('/journey/recall', { method: 'POST', ...json({ label, topics, exam_date: examDate }) });
export const getDueRecall = () => request<RecallDue[]>('/journey/recall/due');
export const doneReview = (reviewId: string, extraTopics: string | null) =>
  request<void>(`/journey/recall/review/${reviewId}/done`, { method: 'POST', ...json({ extra_topics: extraTopics }) });
export const archiveRecall = (setId: string) => request<void>(`/journey/recall/${setId}`, { method: 'DELETE' });

export const getSnapshot = () => request<SnapshotView>('/journey/snapshot');
export const submitSnapshot = (input: SnapshotInput) =>
  request<SnapshotView>('/journey/snapshot', { method: 'POST', ...json(input) });

export const getShelf = () => request<ShelfView>('/journey/shelf');
export const graduateHabit = (habitId: string) =>
  request<{ message: string }>(`/journey/graduate/${habitId}`, { method: 'POST' });
export const shelfCheck = (id: string, holding: boolean) =>
  request<{ message: string; which: number }>(`/journey/shelf/${id}/check`, { method: 'POST', ...json({ holding }) });
export const reviveHabit = (id: string) =>
  request<{ message: string; benched: boolean }>(`/journey/shelf/${id}/revive`, { method: 'POST' });

// Per-device snooze for graduation offers (the server keeps no state for "not yet").
const snoozeKey = (habitId: string) => `lockin.gradSnooze.${habitId}`;
export function offerSnoozed(habitId: string): boolean {
  try {
    const until = Number(localStorage.getItem(snoozeKey(habitId)) ?? 0);
    return until > Date.now();
  } catch {
    return false;
  }
}
export function snoozeOffer(habitId: string, days = 14): void {
  try {
    localStorage.setItem(snoozeKey(habitId), String(Date.now() + days * 86_400_000));
  } catch {
    /* snoozing is a convenience */
  }
}