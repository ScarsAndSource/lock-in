import { request, isDemoMode } from './client';
import { ConsistencyOut, ChainOut } from '../types';
import { INITIAL_CONSISTENCY, INITIAL_CHAIN, INITIAL_PATTERNS } from '../store/mockData';
import { addDaysISO, localTodayISO, qs } from '../lib/dates';

export async function getConsistency(window_days: number = 30, endDate?: string): Promise<ConsistencyOut> {
  if (isDemoMode()) {
    // The live API reports comeback_rate as 0-100; the mock stores a 0-1 fraction.
    const habits = INITIAL_CONSISTENCY.habits.map((h) => ({
      ...h,
      comeback_rate: h.comeback_rate === null ? null : Math.round(h.comeback_rate * 1000) / 10,
    }));
    return { ...INITIAL_CONSISTENCY, habits, end_date: endDate || localTodayISO(), window_days };
  }
  return request<ConsistencyOut>(`/stats/consistency${qs({ window_days, end_date: endDate })}`);
}

export async function getChain(days: number = 14, endDate?: string): Promise<ChainOut> {
  if (isDemoMode()) {
    const end = endDate || localTodayISO();
    const templates = INITIAL_CHAIN.days;
    const mapped = Array.from({ length: days }, (_, i) => {
      const day = addDaysISO(end, i - days + 1);
      const t = templates[i % templates.length];
      return { ...t, day };
    });
    return { end_date: end, days: mapped };
  }
  return request<ChainOut>(`/stats/chain${qs({ days, end_date: endDate })}`);
}

export async function getPatterns(days: number = 30, endDate?: string) {
  if (isDemoMode()) {
    return { ...INITIAL_PATTERNS, end_date: endDate || localTodayISO(), days };
  }
  return request<typeof INITIAL_PATTERNS>(`/stats/patterns${qs({ days, end_date: endDate })}`);
}
