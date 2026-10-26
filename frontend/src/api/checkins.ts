import { ApiError, request, isDemoMode } from './client';
import { loadCheckinSnapshot, saveCheckinSnapshot, sendOrQueue } from '../lib/offlineQueue';
import {
  CheckinView,
  CheckinConfirmRequest,
  CheckinConfirmResponse,
} from '../types';
import { INITIAL_CHECKIN_VIEW } from '../store/mockData';

let currentCheckinView: CheckinView = JSON.parse(JSON.stringify(INITIAL_CHECKIN_VIEW));

export async function getCheckinDefaults(dateStr: string): Promise<CheckinView> {
  if (isDemoMode()) {
    return { ...currentCheckinView, checkin_date: dateStr };
  }
  try {
    const view = await request<CheckinView>(`/checkins/${dateStr}/defaults`);
    void saveCheckinSnapshot(dateStr, view);
    return view;
  } catch (err) {
    // No signal: open the check-in from the copy saved the last time it loaded, so it can still be filled in and queued.
    if (err instanceof ApiError && err.status === 0) {
      const saved = await loadCheckinSnapshot(dateStr);
      if (saved) return { ...saved, from_cache: true };
    }
    throw err;
  }
}

export async function confirmCheckin(
  dateStr: string,
  payload: CheckinConfirmRequest
): Promise<CheckinConfirmResponse> {
  if (isDemoMode()) {
    currentCheckinView.already_confirmed = true;
    currentCheckinView.checkin_date = dateStr;
    if (payload.overrides) {
      for (const override of payload.overrides) {
        const entry = currentCheckinView.entries.find((e) => e.habit_id === override.habit_id);
        if (entry) {
          entry.status = override.status;
          entry.is_default = false;
        }
      }
    }
    if (payload.sleep) {
      const prev = currentCheckinView.sleep.logged;
      currentCheckinView.sleep.logged = {
        log_date: dateStr,
        time_to_bed: payload.sleep.time_to_bed ?? prev?.time_to_bed ?? null,
        time_woke: payload.sleep.time_woke ?? prev?.time_woke ?? null,
        self_rated_quality: payload.sleep.self_rated_quality ?? prev?.self_rated_quality ?? null,
        duration_minutes: prev?.duration_minutes ?? null,
        is_default: false,
      };
    }
    if (payload.screen_time) {
      currentCheckinView.screen_time.logged = {
        log_date: dateStr,
        total_minutes: payload.screen_time.total_minutes,
        source: payload.screen_time.source || 'manual',
        category_breakdown: payload.screen_time.category_breakdown ?? null,
        is_default: false,
      };
    }
    if (payload.mood) {
      currentCheckinView.mood = { log_date: dateStr, ...payload.mood };
    }
    return {
      checkin_date: dateStr,
      confirmed_at: new Date().toISOString(),
      entries: currentCheckinView.entries,
      sleep: currentCheckinView.sleep.logged,
      screen_time: currentCheckinView.screen_time.logged,
      mood: currentCheckinView.mood ?? null,
      support: null,
    };
  }
  // Confirm is an upsert per (user, date), so sending it again after a lost reply is safe. A check-in that finds an
  // unsent one for the same day waits behind it, so the last thing the person entered is the last thing applied.
  const sent = await sendOrQueue<CheckinConfirmResponse>({
    kind: 'checkin',
    path: `/checkins/${dateStr}/confirm`,
    body: payload as unknown as Record<string, unknown>,
    date: dateStr,
    keepOrder: true,
  });
  if (!sent.queued) return sent.data;
  return {
    checkin_date: dateStr,
    confirmed_at: new Date().toISOString(),
    entries: [],
    sleep: null,
    screen_time: null,
    mood: null,
    support: null,
    queued: true,
  };
}

export async function getJournal(dateStr: string): Promise<{ checkin_date: string; journal_text: string | null }> {
  if (isDemoMode()) {
    return { checkin_date: dateStr, journal_text: null };
  }
  return request<{ checkin_date: string; journal_text: string | null }>(`/checkins/${dateStr}/journal`);
}
