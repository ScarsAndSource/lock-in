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
  try {
    return await request<CheckinView>(`/checkins/${dateStr}/defaults`);
  } catch (e) {
    return { ...currentCheckinView, checkin_date: dateStr };
  }
}

export async function confirmCheckin(
  dateStr: string,
  payload: CheckinConfirmRequest
): Promise<CheckinConfirmResponse> {
  if (isDemoMode()) {
    currentCheckinView.already_confirmed = true;
    if (payload.overrides) {
      for (const override of payload.overrides) {
        const entry = currentCheckinView.entries.find((e) => e.habit_id === override.habit_id);
        if (entry) {
          entry.status = override.status;
          entry.is_default = false;
        }
      }
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
    return { checkin_date: dateStr, journal_text: 'Solid disciplined day. Kept distractions low.' };
  }
  return request<{ checkin_date: string; journal_text: string | null }>(`/checkins/${dateStr}/journal`);
}
