import { request, isDemoMode } from './client';
import {
  SleepLog,
  ScreenTimeLog,
  Subject,
  StudySession,
  StudySummary,
  UrgeLog,
  UrgeSummary,
  UrgeOutcome,
} from '../types';
import {
  INITIAL_SUBJECTS,
  INITIAL_STUDY_SESSIONS,
  INITIAL_URGES,
  INITIAL_URGE_SUMMARY,
} from '../store/mockData';
import { localTodayISO, qs, rangeDays } from '../lib/dates';

let localSubjects = [...INITIAL_SUBJECTS];
let localSessions = [...INITIAL_STUDY_SESSIONS];
let localUrges = [...INITIAL_URGES];
let localUrgeSummary = { ...INITIAL_URGE_SUMMARY };

export async function logSleep(payload: {
  log_date: string;
  time_to_bed?: string | null;
  time_woke?: string | null;
  self_rated_quality?: number | null;
}): Promise<SleepLog> {
  if (isDemoMode()) {
    return {
      log_date: payload.log_date,
      time_to_bed: payload.time_to_bed || null,
      time_woke: payload.time_woke || null,
      self_rated_quality: payload.self_rated_quality || null,
      duration_minutes: null,
      is_default: false,
    };
  }
  return request<SleepLog>('/sleep/logs', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function logScreenTime(payload: {
  log_date: string;
  total_minutes: number;
  source?: 'manual' | 'extension';
  category_breakdown?: Record<string, number> | null;
}): Promise<ScreenTimeLog> {
  if (isDemoMode()) {
    return {
      log_date: payload.log_date,
      total_minutes: payload.total_minutes,
      source: payload.source || 'manual',
      category_breakdown: payload.category_breakdown || null,
      is_default: false,
    };
  }
  return request<ScreenTimeLog>('/screen-time/logs', {
    method: 'POST',
    body: JSON.stringify({
      log_date: payload.log_date,
      total_minutes: payload.total_minutes,
      source: payload.source || 'manual',
      category_breakdown: payload.category_breakdown ?? null,
    }),
  });
}

export async function getSubjects(): Promise<Subject[]> {
  if (isDemoMode()) {
    return localSubjects.filter((s) => !s.archived_at);
  }
  return request<Subject[]>('/study/subjects');
}

export async function createSubject(name: string): Promise<Subject> {
  if (isDemoMode()) {
    const existing = localSubjects.find((s) => s.name.toLowerCase() === name.toLowerCase() && !s.archived_at);
    if (existing) return existing;
    const s: Subject = { id: `subj-${Date.now()}`, name, archived_at: null };
    localSubjects.push(s);
    return s;
  }
  return request<Subject>('/study/subjects', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export async function bulkCreateSubjects(text: string): Promise<Subject[]> {
  if (isDemoMode()) {
    const names = text.split(',').map((s) => s.trim()).filter(Boolean);
    return Promise.all(names.map((name) => createSubject(name)));
  }
  return request<Subject[]>('/study/subjects/bulk', {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
}

export async function logStudySession(payload: {
  log_date: string;
  subject_id?: string;
  subject_name?: string;
  planned_minutes?: number | null;
  actual_minutes: number;
}): Promise<StudySession> {
  if (isDemoMode()) {
    const subjectName =
      payload.subject_name || localSubjects.find((s) => s.id === payload.subject_id)?.name || 'Study';
    const s: StudySession = {
      id: `sess-${Date.now()}`,
      log_date: payload.log_date,
      subject_id: payload.subject_id || `subj-${Date.now()}`,
      subject_name: subjectName,
      planned_minutes: payload.planned_minutes || null,
      actual_minutes: payload.actual_minutes,
    };
    localSessions.unshift(s);
    return s;
  }
  const body: Record<string, unknown> = {
    log_date: payload.log_date,
    actual_minutes: payload.actual_minutes,
    planned_minutes: payload.planned_minutes ?? null,
  };
  if (payload.subject_id) body.subject_id = payload.subject_id;
  else if (payload.subject_name) body.subject_name = payload.subject_name;
  return request<StudySession>('/study/sessions', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function getStudySessions(endDate: string, windowDays = 30): Promise<StudySession[]> {
  const { start, end } = rangeDays(endDate, windowDays);
  if (isDemoMode()) {
    return localSessions.filter((s) => s.log_date >= start && s.log_date <= end);
  }
  return request<StudySession[]>(`/study/sessions${qs({ start_date: start, end_date: end })}`);
}

export async function getStudySummary(endDate: string, windowDays = 30): Promise<StudySummary> {
  const { start, end } = rangeDays(endDate, windowDays);
  if (isDemoMode()) {
    const sessions = localSessions.filter((s) => s.log_date >= start && s.log_date <= end);
    const bySubj = localSubjects.map((subj) => {
      const minutes = sessions
        .filter((sess) => sess.subject_id === subj.id)
        .reduce((sum, curr) => sum + curr.actual_minutes, 0);
      return { subject_id: subj.id, name: subj.name, minutes };
    });
    const totalActual = sessions.reduce((sum, s) => sum + s.actual_minutes, 0);
    const totalPlanned = sessions.reduce((sum, s) => sum + (s.planned_minutes || 0), 0);
    const daysStudied = new Set(sessions.map((s) => s.log_date)).size;
    return {
      start_date: start,
      end_date: end,
      total_actual: totalActual,
      total_planned: totalPlanned,
      follow_through_pct: totalPlanned > 0 ? Math.round((totalActual / totalPlanned) * 1000) / 10 : null,
      days_studied: daysStudied,
      by_subject: bySubj,
    };
  }
  return request<StudySummary>(`/study/summary${qs({ start_date: start, end_date: end })}`);
}

export async function captureUrge(payload: {
  outcome: UrgeOutcome;
  occurred_at?: string;
  intensity?: number | null;
  trigger_context?: string | null;
  coping_strategy?: string | null;
  note?: string | null;
}): Promise<UrgeLog> {
  if (isDemoMode()) {
    const today = localTodayISO();
    const newUrge: UrgeLog = {
      id: `urge-${Date.now()}`,
      occurred_at: payload.occurred_at || new Date().toISOString(),
      log_date: today,
      outcome: payload.outcome,
      intensity: payload.intensity ?? null,
      has_detail: Boolean(payload.trigger_context || payload.coping_strategy || payload.note),
      trigger_context: payload.trigger_context || null,
      coping_strategy: payload.coping_strategy || null,
      note: payload.note || null,
    };
    localUrges.unshift(newUrge);
    if (payload.outcome === 'resisted') {
      localUrgeSummary.resisted += 1;
    } else {
      localUrgeSummary.relapsed += 1;
    }
    localUrgeSummary.total += 1;
    localUrgeSummary.resist_rate_pct =
      localUrgeSummary.total > 0
        ? Math.round((localUrgeSummary.resisted / localUrgeSummary.total) * 1000) / 10
        : null;
    return newUrge;
  }
  return request<UrgeLog>('/urges', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getUrges(endDate: string, windowDays = 14, details = true): Promise<UrgeLog[]> {
  const { start, end } = rangeDays(endDate, windowDays);
  if (isDemoMode()) {
    return localUrges.filter((u) => u.log_date >= start && u.log_date <= end);
  }
  return request<UrgeLog[]>(`/urges${qs({ start_date: start, end_date: end, details })}`);
}

export async function getUrgeSummary(windowDays = 14): Promise<UrgeSummary> {
  if (isDemoMode()) return { ...localUrgeSummary, window_days: windowDays };
  return request<UrgeSummary>(`/urges/summary${qs({ days: windowDays })}`);
}
