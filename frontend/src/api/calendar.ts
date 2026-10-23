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

/** One thing read off a photo of a timetable, date sheet or notice. A PROPOSAL: nothing is saved yet. */
export interface ProposedItem {
  type: 'event' | 'task';
  title: string;
  date: string | null; // local YYYY-MM-DD (events always have one)
  start: string | null; // HH:MM
  end: string | null;
  kind: CalendarKind | null; // events only
}

export interface ScheduleProposal {
  items: ProposedItem[];
  /** Entries with no calendar date (a weekly timetable) or unreadable ones: not proposed. */
  skipped: number;
}

export interface PhotoEvent {
  title: string;
  date: string;
  start?: string | null;
  end?: string | null;
  kind: CalendarKind;
}

/** A photo or screenshot -> proposed events and tasks. Saves nothing. */
export async function parseScheduleImage(file: Blob): Promise<ScheduleProposal> {
  if (isDemoMode()) throw new Error('Reading a photo needs the live backend (demo mode is on).');
  const form = new FormData();
  form.append('image', file, (file as File).name || 'schedule.jpg');
  return request<ScheduleProposal>('/calendar/parse-image', { method: 'POST', body: form });
}

/** The events the person ticked. Adding the same picture twice adds nothing the second time. */
export async function addPhotoEvents(events: PhotoEvent[]): Promise<{ added: number; duplicates: number }> {
  if (isDemoMode()) throw new Error('Adding events needs the live backend (demo mode is on).');
  return request<{ added: number; duplicates: number }>('/calendar/photo-events', {
    method: 'POST',
    body: JSON.stringify({ events }),
  });
}

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
