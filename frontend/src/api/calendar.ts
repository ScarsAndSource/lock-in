import { request, isDemoMode } from './client';

export type CalendarKind = 'exam' | 'class' | 'other';

export interface CalendarImportResult {
  source: string;
  added: number;
  exams: number;
  skipped: number;
  warnings: string[];
}

export interface ExamDto {
  id: string;
  title: string;
  starts_at: string; // ISO instant
  all_day: boolean;
  day: string; // local YYYY-MM-DD
  days_until: number;
}

export interface CalendarSourceDto {
  source: string;
  events: number;
  exams: number;
  last_imported_at: string;
}

export const MAX_ICS_BYTES = 1_000_000;

/** Replaces the future events of the calendar named `source` with the file's contents. */
export async function importIcs(ics: string, source?: string): Promise<CalendarImportResult> {
  if (isDemoMode()) throw new Error('Calendar import needs the live backend (demo mode is on).');
  return request<CalendarImportResult>('/calendar/import', {
    method: 'POST',
    body: JSON.stringify(source ? { ics, source } : { ics }),
  });
}

export async function getExams(): Promise<ExamDto[]> {
  if (isDemoMode()) return [];
  return request<ExamDto[]>('/calendar/exams');
}

export async function getCalendarSources(): Promise<CalendarSourceDto[]> {
  if (isDemoMode()) return [];
  return request<CalendarSourceDto[]>('/calendar/sources');
}

/** "That isn't an exam." The correction survives re-importing the calendar. */
export async function setEventKind(id: string, kind: CalendarKind): Promise<void> {
  await request<unknown>(`/calendar/events/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify({ kind }),
  });
}

export async function deleteCalendarSource(source: string): Promise<void> {
  await request<void>(`/calendar/sources/${encodeURIComponent(source)}`, { method: 'DELETE' });
}
