import { request, isDemoMode } from './client';
import { PauseShortcut, PauseOverview, PausePreset } from '../types';
import { INITIAL_PAUSE_SHORTCUTS, INITIAL_PAUSE_OVERVIEW } from '../store/mockData';

let localOverview = JSON.parse(JSON.stringify(INITIAL_PAUSE_OVERVIEW)) as PauseOverview;

export async function getPauseShortcuts(): Promise<PauseShortcut[]> {
  if (isDemoMode()) return INITIAL_PAUSE_SHORTCUTS;
  try {
    return await request<PauseShortcut[]>('/pauses/shortcuts');
  } catch {
    return INITIAL_PAUSE_SHORTCUTS;
  }
}

export async function getPauseOverview(): Promise<PauseOverview> {
  if (isDemoMode()) return localOverview;
  try {
    return await request<PauseOverview>('/pauses/habits');
  } catch {
    return localOverview;
  }
}

export async function quickPause(preset: PausePreset, habitId?: string): Promise<any> {
  if (isDemoMode()) {
    if (habitId) {
      const h = localOverview.habits.find((row) => row.habit_id === habitId);
      if (h) {
        h.state = 'paused';
        h.effective_paused = true;
        h.paused_by = 'habit';
        h.pause = { id: `p-${Date.now()}`, start_date: '2026-12-31', end_date: '2027-01-02', active: true, habit_id: habitId };
      }
    } else {
      localOverview.global_pause = { id: `gp-${Date.now()}`, start_date: '2026-12-31', end_date: '2027-01-02', active: true, habit_id: null };
      localOverview.habits.forEach((h) => {
        h.effective_paused = true;
        h.paused_by = 'all';
      });
    }
    return { ok: true };
  }
  return request('/pauses/quick', {
    method: 'POST',
    body: JSON.stringify({ preset, habit_id: habitId }),
  });
}

export async function resumePause(habitId?: string): Promise<any> {
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
    body: JSON.stringify({ habit_id: habitId }),
  });
}
