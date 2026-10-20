import { request, isDemoMode } from './client';
import { ScreenTimeLog, SleepLog } from '../types';
import { qs, rangeDays } from '../lib/dates';

/** Real logged sleep for the window ending at `endDate` (demo mode has no stored logs, so it returns none). */
export async function getSleepLogs(endDate: string, windowDays = 14): Promise<SleepLog[]> {
  if (isDemoMode()) return [];
  const { start, end } = rangeDays(endDate, windowDays);
  return request<SleepLog[]>(`/sleep/logs${qs({ start_date: start, end_date: end })}`);
}

export async function getScreenLogs(endDate: string, windowDays = 14): Promise<ScreenTimeLog[]> {
  if (isDemoMode()) return [];
  const { start, end } = rangeDays(endDate, windowDays);
  return request<ScreenTimeLog[]>(`/screen-time/logs${qs({ start_date: start, end_date: end })}`);
}
