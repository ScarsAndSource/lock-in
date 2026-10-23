import { request, isDemoMode } from './client';
import type { SupportPayload } from '../types';

export const STICKERS = ['🌱', '☕', '🌙', '✨', '🍀', '🧸', '🌧️', '🔥'] as const;
export type AutopsyReason = 'too_big' | 'wrong_time' | 'wrong_trigger' | 'dont_care';

export interface GrowthAutopsy {
  id: string;
  habit_id: string;
  habit_name: string;
  consistency_pct: number;
  window_days: number;
  floor_text: string | null;
  current_label: string;
  lighter_label: string | null;
  identity_sentence: string | null;
  identity_confidence: number | null;
}

export interface GrowthPrompt {
  autopsy: GrowthAutopsy | null;
  identity_due: boolean;
}

export interface GrowthIdentity {
  sentence: string;
  matters: string;
  why_now: string;
  importance: number;
  confidence: number;
  votes: number;
  updated_at: string;
}

export interface IdentityInput {
  matters: string;
  why_now: string;
  importance: number;
  confidence: number;
  sentence: string;
}

export interface JournalEntry {
  entry_date: string;
  text: string;
  sticker: string | null;
}

export interface FutureNote {
  id: string;
  text: string | null;
  has_audio: boolean;
  duration_s: number | null;
  send_at: string | null;
  active: boolean;
  audio_b64: string | null;
  audio_mime: string | null;
}

export interface FutureInput {
  text: string | null;
  audio_b64: string | null;
  audio_mime: string | null;
  duration_s: number | null;
  send_at: string | null;
}

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });

// ---- prompt slot
export async function getGrowthPrompt(): Promise<GrowthPrompt> {
  if (isDemoMode()) return { autopsy: null, identity_due: false };
  return request<GrowthPrompt>('/growth/prompt');
}

// ---- identity
export async function getIdentity(weekStart?: string): Promise<GrowthIdentity | null> {
  if (isDemoMode()) return null;
  const q = weekStart ? `?week_start=${encodeURIComponent(weekStart)}` : '';
  return request<GrowthIdentity | null>(`/growth/identity${q}`);
}
export const putIdentity = (input: IdentityInput) =>
  request<GrowthIdentity>('/growth/identity', { method: 'PUT', ...json(input) });
export const deleteIdentity = () => request<void>('/growth/identity', { method: 'DELETE' });

// ---- journal
export const getJournal = (days = 14) => request<JournalEntry[]>(`/growth/journal?days=${days}`);
export const putJournal = (day: string, body: { text: string; sticker: string | null }) =>
  request<{ entry: JournalEntry; support: SupportPayload | null }>(`/growth/journal/${day}`, {
    method: 'PUT',
    ...json(body),
  });

// ---- habit check-up
export const applyAutopsy = (
  id: string,
  body: { reason: AutopsyReason; floor_text?: string; cue?: string; choice?: 'archive' | 'keep' },
) => request<{ message: string }>(`/growth/autopsy/${id}/apply`, { method: 'POST', ...json(body) });
export const deferAutopsy = (id: string, skip: boolean) =>
  request<void>(`/growth/autopsy/${id}/${skip ? 'skip' : 'later'}`, { method: 'POST' });

// ---- notes to future self
export const listFutureNotes = () => request<FutureNote[]>('/growth/future');
export const createFutureNote = (input: FutureInput) =>
  request<FutureNote>('/growth/future', { method: 'POST', ...json(input) });
export const getFutureNote = (id: string) => request<FutureNote>(`/growth/future/${id}`);
export const markFutureNotePlayed = (id: string) => request<void>(`/growth/future/${id}/played`, { method: 'POST' });
export const setFutureNoteActive = (id: string, active: boolean) =>
  request<void>(`/growth/future/${id}`, { method: 'PATCH', ...json({ active }) });
export const deleteFutureNote = (id: string) => request<void>(`/growth/future/${id}`, { method: 'DELETE' });

export function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const s = String(reader.result);
      resolve(s.slice(s.indexOf(',') + 1));
    };
    reader.onerror = () => reject(new Error('Could not read the recording.'));
    reader.readAsDataURL(blob);
  });
}

// ---- device-local switches (prompts on/off, identity snooze). The check-up snooze lives on the server.
const PROMPTS_KEY = 'lockin_growth_prompts';
const IDENTITY_SNOOZE_KEY = 'lockin_growth_identity_snooze';
export const MIRROR_SECTION_KEY = 'lockin_mirror_section';

export function promptsEnabled(): boolean {
  try {
    return localStorage.getItem(PROMPTS_KEY) !== 'off';
  } catch {
    return true;
  }
}
export function setPromptsEnabled(on: boolean): void {
  try {
    localStorage.setItem(PROMPTS_KEY, on ? 'on' : 'off');
  } catch {
    /* storage unavailable: the switch just won't stick */
  }
}
export function identitySnoozed(): boolean {
  try {
    return Date.now() < Number(localStorage.getItem(IDENTITY_SNOOZE_KEY) || 0);
  } catch {
    return false;
  }
}
export function snoozeIdentity(days: number): void {
  try {
    localStorage.setItem(IDENTITY_SNOOZE_KEY, String(Date.now() + days * 86_400_000));
  } catch {
    /* ignore */
  }
}
