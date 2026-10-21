import { request, isDemoMode } from './client';

export interface SleepInferenceDto {
  day: string; // wake date, YYYY-MM-DD
  kind: 'sleep';
  time_to_bed: string; // HH:MM local
  time_woke: string; // HH:MM local
  duration_minutes: number;
  confidence: 'low' | 'medium' | 'high';
  basis: string[];
  prompt: string; // e.g. "~6.5h, right?"
}

/** One yes/no question about last night, or null when there is nothing worth asking. Never throws: a chip is optional. */
export async function getSleepInference(day: string): Promise<SleepInferenceDto | null> {
  if (isDemoMode()) return null;
  try {
    return (await request<SleepInferenceDto | null>(`/companion/inference?day=${encodeURIComponent(day)}`)) ?? null;
  } catch {
    return null;
  }
}
