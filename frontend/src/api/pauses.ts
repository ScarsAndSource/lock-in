import { request, isDemoMode } from './client';
import { PauseShortcut, PauseOverview, PausePreset } from '../types';
import { INITIAL_PAUSE_SHORTCUTS, INITIAL_PAUSE_OVERVIEW } from '../store/mockData';
import { addDaysISO, localTodayISO } from '../lib/dates';

let localOverview = JSON.parse(JSON.stringify(INITIAL_PAUSE_OVERVIEW)) as PauseOverview;

function presetEnd(preset: PausePreset, start: string): string {
  switch (preset) {
    case 'today':
      return start;
    case '3_days':
      return addDaysISO(start, 2);
    case 'this_week':
      return addDaysISO(start, 6);
    case '1_week':
      return addDaysISO(start, 6);
    case '2_weeks':
      return addDaysISO(start, 13);
    default:
      return addDaysISO(start, 2);
  }
}

export async function getPauseShortcuts(): Promise<PauseShortcut[]> {
  if (isDemoMode()) {
    const today = localTodayISO();
    return INITIAL_PAUSE_SHORTCUTS.map((s) => ({
      ...s,
      start_date: today,
      end_date: presetEnd(s.key, today),
    }));
  }
  return request<PauseShortcut[]>('/pauses/shortcuts');
}

export async function getPauseOverview(): Promise<PauseOverview> {
  if (isDemoMode()) {
    return { ...localOverview, today: localTodayISO() };
  }
  return request<PauseOverview>('/pauses/habits');
}

export async function quickPause(preset: PausePreset, habitId?: string): Promise<unknown> {
  if (isDemoMode()) {
    const today = localTodayISO();
    const end = presetEnd(preset, today);
    if (habitId) {
      const h = localOverview.habits.find((row) => row.habit_id === habitId);
      if (h) {
        h.state = 'paused';
        h.effective_paused = true;
        h.paused_by = 'habit';
        h.pause = { id: `p-${Date.now()}`, start_date: today, end_date: end, active: true, habit_id: habitId };
      }
    } else {
      localOverview.global_pause = {
        id: `gp-${Date.now()}`,
        start_date: today,
        end_date: end,
        active: true,
        habit_id: null,
      };
      localOverview.habits.forEach((h) => {
        h.effective_paused = true;
        h.paused_by = 'all';
      });
    }
    return { ok: true };
  }
  return request('/pauses/quick', {
    method: 'POST',
    body: JSON.stringify({ preset, habit_id: habitId ?? null }),
  });
}

export async function resumePause(habitId?: string): Promise<{ resumed: number; still_paused_by_all: boolean }> {
  if (isDemoMode()) {
    if (habitId) {
      const h = localOverview.habits.find((row) => row.habit_id === habitId);
      if (h) {
        h.state = 'active';
        h.effective_paused = false;
        h.paused_by = null;
        h.pause = null;
      }
    } else {
      localOverview.global_pause = null;
      localOverview.habits.forEach((h) => {
        h.effective_paused = false;
        h.paused_by = null;
      });
    }
    return { resumed: 1, still_paused_by_all: false };
  }
  return request('/pauses/resume', {
    method: 'POST',
    body: JSON.stringify({ habit_id: habitId ?? null }),
  });
}
