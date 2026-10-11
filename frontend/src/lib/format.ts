import type { ChainDomainStatus } from '../types';

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

export function formatComeback(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return '—';
  return `${Math.round(rate * 100)}%`;
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
