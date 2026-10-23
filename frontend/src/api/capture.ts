import { request, isDemoMode, ApiError, API_BASE } from './client';
import type { HabitStatus, SupportPayload } from '../types';

/* ------------------------------------------------------------------ check-in capture (typed, voice, screenshot) */

export interface ParsedHabit {
  habit_id: string;
  status: HabitStatus;
}

/** A PROPOSAL. Nothing is saved until the person locks the check-in in. */
export interface CheckinProposal {
  transcript: string | null;
  habits: ParsedHabit[];
  sleep: { time_to_bed: string | null; time_woke: string | null; self_rated_quality: number | null } | null;
  screen_time_minutes: number | null;
  mood: { valence: number; energy: number } | null;
  journal: string | null;
  empty: boolean;
  support: SupportPayload | null;
}

export interface ScreenshotProposal {
  total_minutes: number;
  category_breakdown: Record<string, number>;
  confidence: 'high' | 'medium' | 'low';
  source: 'screenshot';
}

const demoBlocked = (what: string): never => {
  throw new ApiError(`${what} needs the live backend. Switch off demo data to use it.`, 0);
};

/** Typed (or keyboard-dictated) check-in -> proposal. */
export async function parseTypedCheckin(text: string): Promise<CheckinProposal> {
  if (isDemoMode()) return demoBlocked('Reading your check-in');
  return request<CheckinProposal>('/checkins/parse', { method: 'POST', body: JSON.stringify({ text }) });
}

function audioForm(blob: Blob): FormData {
  const base = (blob.type || '').split(';')[0].toLowerCase();
  const ext = base.includes('mp4') || base.includes('aac') || base.includes('m4a') ? 'm4a' : base.includes('ogg') ? 'ogg' : 'webm';
  const form = new FormData();
  form.append('audio', blob, `checkin.${ext}`);
  return form;
}

/** A short recording -> transcript -> proposal. */
export async function parseVoiceCheckin(blob: Blob): Promise<CheckinProposal> {
  if (isDemoMode()) return demoBlocked('Voice check-in');
  return request<CheckinProposal>('/checkins/voice', { method: 'POST', body: audioForm(blob) });
}

/** A short recording -> just its words, to drop into a text box (Quick Add, Companion). */
export async function transcribeRecording(blob: Blob): Promise<string> {
  if (isDemoMode()) return demoBlocked('Voice input');
  const res = await request<{ transcript: string }>('/checkins/transcribe', { method: 'POST', body: audioForm(blob) });
  return res.transcript;
}

/** A Screen Time / Digital Wellbeing screenshot -> a proposed daily total. */
export async function parseScreenshot(file: Blob): Promise<ScreenshotProposal> {
  if (isDemoMode()) return demoBlocked('Screenshot reading');
  const form = new FormData();
  form.append('image', file, (file as File).name || 'screen-time.png');
  return request<ScreenshotProposal>('/screen-time/parse-screenshot', { method: 'POST', body: form });
}

/* ------------------------------------------------------------------ ingest tokens (phone automations) */

export interface IngestToken {
  id: string;
  label: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
  /** Set: a key that can only mark this one habit done. Unset: the sleep / screen-time key. */
  habit_id?: string | null;
}

/** `token` is returned ONCE, at creation. The server never stores or returns it again. */
export interface IngestTokenCreated extends IngestToken {
  token: string;
}

export const MAX_ACTIVE_INGEST_TOKENS = 8; // mirrors the backend cap

export async function listIngestTokens(): Promise<IngestToken[]> {
  if (isDemoMode()) return [];
  return request<IngestToken[]>('/ingest/tokens');
}

export async function createIngestToken(label: string, habitId?: string): Promise<IngestTokenCreated> {
  if (isDemoMode()) return demoBlocked('Automations');
  return request<IngestTokenCreated>('/ingest/tokens', {
    method: 'POST',
    body: JSON.stringify(habitId ? { label, habit_id: habitId } : { label }),
  });
}

/** One pasteable URL for an automation app: the key rides in the path, so no header and no JSON body are needed. */
export function ingestUrl(token: string, kind: 'sleep_start' | 'sleep_end' | 'screen_time' | 'habit_done'): string {
  const base = (API_BASE || window.location.origin).replace(/\/$/, '');
  return `${base}/ingest/u/${encodeURIComponent(token)}/${kind}`;
}

export async function revokeIngestToken(id: string): Promise<void> {
  if (isDemoMode()) return demoBlocked('Automations');
  await request<void>(`/ingest/tokens/${id}`, { method: 'DELETE' });
}
