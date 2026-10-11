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

let localSubjects = [...INITIAL_SUBJECTS];
let localSessions = [...INITIAL_STUDY_SESSIONS];
let localUrges = [...INITIAL_URGES];
let localUrgeSummary = { ...INITIAL_URGE_SUMMARY };

// ---------------- Sleep
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
      duration_minutes: 450,
      is_default: false,
    };
  }
  return request<SleepLog>('/sleep/logs', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// ---------------- Screen Time
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
      category_breakdown: payload.category_breakdown,
    }),
  });
}

// ---------------- Study
export async function getSubjects(): Promise<Subject[]> {
  if (isDemoMode()) {
    return localSubjects.filter((s) => !s.archived_at);
  }
  try {
    return await request<Subject[]>('/study/subjects');
  } catch {
    return localSubjects.filter((s) => !s.archived_at);
  }
}

export async function createSubject(name: string): Promise<Subject> {
  if (isDemoMode()) {
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
    const created: Subject[] = names.map((name) => ({
      id: `subj-${Date.now()}-${Math.random().toString(36).substring(2, 5)}`,
      name,
      archived_at: null,
    }));
    localSubjects.push(...created);
    return created;
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
    const subjectName = payload.subject_name || localSubjects.find((s) => s.id === payload.subject_id)?.name || 'Study';
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
  return request<StudySession>('/study/sessions', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getStudySessions(): Promise<StudySession[]> {
  if (isDemoMode()) return localSessions;
  try {
    return await request<StudySession[]>('/study/sessions');
  } catch {
    return localSessions;
  }
}

export async function getStudySummary(): Promise<StudySummary> {
  if (isDemoMode()) {
    const bySubj = localSubjects.map((s) => {
      const minutes = localSessions
        .filter((sess) => sess.subject_id === s.id || sess.subject_name === s.name)
        .reduce((sum, curr) => sum + curr.actual_minutes, 0);
      return { subject_id: s.id, name: s.name, minutes };
    });
    const totalActual = bySubj.reduce((sum, s) => sum + s.minutes, 0);
    return {
      start_date: '2026-12-01',
      end_date: '2026-12-31',
      total_actual: totalActual,
      total_planned: totalActual + 30,
      follow_through_pct: 92.5,
      days_studied: 18,
      by_subject: bySubj,
    };
  }
  return request<StudySummary>('/study/summary');
}

// ---------------- Urges
export async function captureUrge(payload: {
  outcome: UrgeOutcome;
  occurred_at?: string;
  intensity?: number | null;
  trigger_context?: string | null;
  coping_strategy?: string | null;
  note?: string | null;
}): Promise<UrgeLog> {
  if (isDemoMode()) {
    const newUrge: UrgeLog = {
      id: `urge-${Date.now()}`,
      occurred_at: payload.occurred_at || new Date().toISOString(),
      log_date: new Date().toISOString().split('T')[0],
      outcome: payload.outcome,
      intensity: payload.intensity || null,
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
    localUrgeSummary.resist_rate_pct = Math.round((localUrgeSummary.resisted / localUrgeSummary.total) * 100);
    return newUrge;
  }
  return request<UrgeLog>('/urges', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getUrges(): Promise<UrgeLog[]> {
  if (isDemoMode()) return localUrges;
  try {
    return await request<UrgeLog[]>('/urges');
  } catch {
    return localUrges;
  }
}

export async function getUrgeSummary(): Promise<UrgeSummary> {
  if (isDemoMode()) return localUrgeSummary;
  try {
    return await request<UrgeSummary>('/urges/summary');
  } catch {
    return localUrgeSummary;
  }
}
