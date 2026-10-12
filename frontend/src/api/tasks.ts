import { request, isDemoMode } from './client';
import type { Task, TaskCaptureResult, TaskFocus } from '../types';

// ---------------------------------------------------------------- demo mode (no backend, no AI)
// Demo capture can't call a model, so it behaves like the backend's honest fallback: your words, one task per
// line, no dates. Nothing here pretends to be AI.
let demoTasks: Task[] = [];

function demoTask(title: string): Task {
  return {
    id: `demo-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    title,
    notes: null,
    importance: 2,
    status: 'open',
    state: 'due',
    due: null,
    due_has_time: false,
    remind: null,
    repeat_days: null,
    snoozed_until: null,
    nudge_count: 0,
    last_done_at: null,
    done_count: 0,
    ai_parsed: false,
    created_at: new Date().toISOString(),
  };
}

function demoFocus(): TaskFocus {
  const open = demoTasks.filter((t) => t.status === 'open' && t.state !== 'snoozed');
  return {
    now: open.filter((t) => t.importance >= 2),
    small: open.filter((t) => t.importance === 1),
    later_today: [],
    stale: [],
    hidden_now: 0,
    backlog_count: 0,
  };
}

// ---------------------------------------------------------------- api
export async function captureTasks(text: string): Promise<TaskCaptureResult> {
  if (isDemoMode()) {
    const titles = text
      .split(/[\n;]+/)
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 12);
    const created = titles.map(demoTask);
    demoTasks = [...created, ...demoTasks];
    return { mode: 'fallback', tasks: created, skipped_duplicates: 0, support: null };
  }
  return request<TaskCaptureResult>('/tasks/capture', { method: 'POST', body: JSON.stringify({ text }) });
}

export async function getTaskFocus(): Promise<TaskFocus> {
  if (isDemoMode()) return demoFocus();
  return request<TaskFocus>('/tasks/focus');
}

export async function listTasks(status: 'open' | 'done' | 'dropped' = 'open'): Promise<Task[]> {
  if (isDemoMode()) return demoTasks.filter((t) => t.status === status);
  return request<Task[]>(`/tasks?status=${status}`);
}

export interface TaskPatch {
  title?: string;
  notes?: string | null;
  importance?: 1 | 2 | 3;
  due?: string | null; // local "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM"; null clears
  remind?: string | null;
  repeat_days?: number | null;
  status?: 'open' | 'dropped';
}

export async function patchTask(id: string, patch: TaskPatch): Promise<Task> {
  if (isDemoMode()) {
    demoTasks = demoTasks.map((t) => (t.id === id ? { ...t, ...patch, status: patch.status ?? t.status } : t));
    return demoTasks.find((t) => t.id === id) as Task;
  }
  return request<Task>(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(patch) });
}

export async function completeTask(id: string): Promise<Task> {
  if (isDemoMode()) {
    demoTasks = demoTasks.map((t) => (t.id === id ? { ...t, status: 'done', state: 'done' } : t));
    return demoTasks.find((t) => t.id === id) as Task;
  }
  return request<Task>(`/tasks/${id}/done`, { method: 'POST' });
}

export async function snoozeTask(id: string, minutes: number): Promise<Task> {
  if (isDemoMode()) {
    demoTasks = demoTasks.map((t) => (t.id === id ? { ...t, state: 'snoozed' } : t));
    return demoTasks.find((t) => t.id === id) as Task;
  }
  return request<Task>(`/tasks/${id}/snooze`, { method: 'POST', body: JSON.stringify({ minutes }) });
}

export async function deleteTask(id: string): Promise<void> {
  if (isDemoMode()) {
    demoTasks = demoTasks.filter((t) => t.id !== id);
    return;
  }
  await request<void>(`/tasks/${id}`, { method: 'DELETE' });
}
