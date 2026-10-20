import type { ChainDomainStatus, HabitStatus } from '../types';

/** The tiers a user can tap, best to worst. Legacy 'partial' is only offered when a day already holds it. */
const HABIT_TIERS: HabitStatus[] = ['stretch', 'done', 'floor', 'skipped'];

export function habitTierOptions(current?: HabitStatus | null): HabitStatus[] {
  return current === 'partial' ? ['stretch', 'done', 'partial', 'floor', 'skipped'] : HABIT_TIERS;
}

const HABIT_STATUS_LABEL: Record<HabitStatus, string> = {
  stretch: 'Stretch',
  done: 'Done',
  floor: 'Floor',
  partial: 'Part',
  skipped: 'Miss',
};

export function habitStatusLabel(status: HabitStatus): string {
  return HABIT_STATUS_LABEL[status];
}

/** "Floor: 10 min walk · Stretch: full hour", or null when the habit has no tier text. */
export function tierHint(floor?: string | null, stretch?: string | null): string | null {
  const parts = [floor ? `Floor: ${floor}` : null, stretch ? `Stretch: ${stretch}` : null].filter(Boolean);
  return parts.length ? parts.join(' · ') : null;
}

export function formatPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${Number(value).toFixed(digits)}%`;
}

export function formatMinutes(total: number | null | undefined): string {
  if (total === null || total === undefined) return '—';
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h <= 0) return `${m} min`;
  if (m === 0) return `${h} hr`;
  return `${h} hr ${m} min`;
}

/** The backend already sends the comeback rate as a percentage (0-100). */
export function formatComeback(rate: number | null | undefined): string {
  if (rate === null || rate === undefined || Number.isNaN(rate)) return '—';
  return `${Math.round(rate)}%`;
}

/** "HH:MM" or "HH:MM:SS" -> minutes after midnight, or null. */
export function clockToMinutes(value: string | null | undefined): number | null {
  if (!value) return null;
  const [h, m] = value.split(':').map(Number);
  if (!Number.isFinite(h) || !Number.isFinite(m)) return null;
  return h * 60 + m;
}

/**
 * Median clock time of a list of "HH:MM" values. With `overnight`, early-morning times (before noon) are treated as
 * after midnight so a bedtime of 23:30 and 00:30 average to ~00:00, not midday.
 */
export function medianClockMinutes(values: (string | null | undefined)[], overnight = false): number | null {
  const mins = values
    .map(clockToMinutes)
    .filter((v): v is number => v !== null)
    .map((v) => (overnight && v < 12 * 60 ? v + 24 * 60 : v))
    .sort((a, b) => a - b);
  if (mins.length === 0) return null;
  const mid = Math.floor(mins.length / 2);
  const med = mins.length % 2 ? mins[mid] : (mins[mid - 1] + mins[mid]) / 2;
  return Math.round(med) % (24 * 60);
}

export function formatClock12(totalMinutes: number | null | undefined): string {
  if (totalMinutes === null || totalMinutes === undefined) return '—';
  const h24 = Math.floor(totalMinutes / 60) % 24;
  const m = totalMinutes % 60;
  const suffix = h24 >= 12 ? 'pm' : 'am';
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
  return `${h12}:${String(m).padStart(2, '0')} ${suffix}`;
}

export function mean(values: number[]): number | null {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

/** Backend chain uses good/ok/bad/none; the weave UI uses good/partial/missed/none. */
export function toWeaveStatus(raw: string | null | undefined): ChainDomainStatus {
  switch (raw) {
    case 'good':
      return 'good';
    case 'ok':
    case 'partial':
      return 'partial';
    case 'bad':
    case 'missed':
      return 'missed';
    default:
      return 'none';
  }
}

export function errorMessage(err: unknown, fallback = 'Something went wrong'): string {
  if (err && typeof err === 'object' && 'message' in err && typeof (err as Error).message === 'string') {
    return (err as Error).message;
  }
  return fallback;
}
