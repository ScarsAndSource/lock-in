import { request, isDemoMode } from './client';
import type { NextAction, NextTarget } from '../lib/nextAction';

// ---------------------------------------------------------------- wire types (snake_case, as the API sends them)
export interface RiskWindowDto {
  start: number; // minute of the local day
  end: number; // exclusive; smaller than start when the window crosses midnight
  weight: number; // 0..1
}

export interface RhythmDto {
  wake: number | null;
  bed: number | null;
  checkin: number | null;
  first_open: number | null;
  windows: RiskWindowDto[];
  samples: number;
  confidence: 'low' | 'medium' | 'high';
}

export interface NextActionDto {
  key: string;
  kind: NextAction['kind'];
  eyebrow: string;
  title: string;
  detail: string | null;
  cta: string | null;
  target: {
    type: 'habit' | 'task' | 'checkin' | 'urge' | 'none';
    habit_id: string | null;
    status: 'done' | 'floor' | null;
    task_id: string | null;
  };
  why: string | null;
  voice: string | null;
}

export interface CompanionNow {
  next_action: NextActionDto;
  rhythm: RhythmDto;
  local_minute: number;
  tone: 'direct' | 'coach';
  habits_done: number;
  habits_total: number;
  confirmed: boolean;
}

export type CompanionEventKind = 'app_open' | 'nba_shown' | 'nba_acted' | 'nba_skipped' | 'push_opened';

/** A believable day shape for demo mode, so the orbit has something to draw. Clearly labelled as demo in the UI. */
export const DEMO_RHYTHM: RhythmDto = {
  wake: 6 * 60 + 45,
  bed: 23 * 60 + 15,
  checkin: 22 * 60,
  first_open: 7 * 60,
  windows: [{ start: 23 * 60, end: 60, weight: 0.7 }],
  samples: 42,
  confidence: 'medium',
};

// ---------------------------------------------------------------- calls
/** Null in demo mode (no backend): callers fall back to the on-device ranking. */
export async function getCompanionNow(skipped: string[]): Promise<CompanionNow | null> {
  if (isDemoMode()) return null;
  const qs = new URLSearchParams();
  skipped.forEach((k) => qs.append('skip', k));
  const tail = qs.toString();
  return request<CompanionNow>(`/companion/now${tail ? `?${tail}` : ''}`);
}

/** Fire-and-forget usage signal. Never throws and never blocks the UI: a lost event only means a slower-learning rhythm. */
export function postCompanionEvent(kind: CompanionEventKind, ref?: string): void {
  if (isDemoMode()) return;
  void request<void>('/companion/events', {
    method: 'POST',
    body: JSON.stringify(ref ? { kind, ref } : { kind }),
  }).catch(() => undefined);
}

/** Server action -> the card's shape. A malformed target degrades to "nothing to tap", never a crash. */
export function fromServer(dto: NextActionDto): NextAction {
  const t = dto.target;
  let target: NextTarget = { type: 'none' };
  if (t.type === 'habit' && t.habit_id && t.status) target = { type: 'habit', habitId: t.habit_id, status: t.status };
  else if (t.type === 'task' && t.task_id) target = { type: 'task', taskId: t.task_id };
  else if (t.type === 'checkin') target = { type: 'checkin' };
  else if (t.type === 'urge') target = { type: 'urge' };
  return {
    key: dto.key,
    kind: dto.kind,
    eyebrow: dto.eyebrow,
    title: dto.title,
    detail: dto.detail,
    cta: dto.cta,
    target,
    voice: dto.voice,
    why: dto.why,
  };
}
