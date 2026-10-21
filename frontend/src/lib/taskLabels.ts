import type { Task } from '../types';
import { addDaysISO, formatDayShort, localTodayISO } from './dates';

export function clock12(hhmm: string): string {
  const [h, m] = hhmm.split(':').map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`;
}

export function repeatLabel(days: number | null): string | null {
  if (!days) return null;
  if (days === 1) return 'daily';
  if (days === 7) return 'weekly';
  return `every ${days} days`;
}

/** "Today 5:00 PM", "Tomorrow", "Overdue · 9 Oct", ... built from the backend's local-time strings (no tz math here). */
export function taskMeta(t: Task): string {
  const today = localTodayISO();
  const parts: string[] = [];
  if (t.due) {
    const day = t.due.slice(0, 10);
    const time = t.due_has_time ? clock12(t.due.slice(11, 16)) : null;
    let label: string;
    if (day < today) label = `Overdue · ${formatDayShort(day)}`;
    else if (day === today) label = 'Today';
    else if (day === addDaysISO(today, 1)) label = 'Tomorrow';
    else label = formatDayShort(day);
    parts.push(time && day >= today ? `${label} ${time}` : label);
  } else if (t.remind) {
    parts.push(`Reminder ${clock12(t.remind.slice(11, 16))}`);
  }
  const rep = repeatLabel(t.repeat_days);
  if (rep) parts.push(rep);
  return parts.join(' · ');
}
