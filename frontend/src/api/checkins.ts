import { request, isDemoMode } from './client';
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
  return request<CheckinView>(`/checkins/${dateStr}/defaults`);
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
    return {
      checkin_date: dateStr,
      confirmed_at: new Date().toISOString(),
      entries: currentCheckinView.entries,
      sleep: currentCheckinView.sleep.logged,
      screen_time: currentCheckinView.screen_time.logged,
      support: null,
    };
  }
  return request<CheckinConfirmResponse>(`/checkins/${dateStr}/confirm`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getJournal(dateStr: string): Promise<{ checkin_date: string; journal_text: string | null }> {
  if (isDemoMode()) {
    return { checkin_date: dateStr, journal_text: null };
  }
  return request<{ checkin_date: string; journal_text: string | null }>(`/checkins/${dateStr}/journal`);
}
