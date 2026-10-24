import type { ShareKey } from '../../api/crew';

export const input = 'w-full bg-surface-container-low border border-line rounded-lg px-3 py-2 font-small text-ink';
export const btn = 'h-9 px-3 rounded-lg bg-ink text-ground-chalk font-caption text-caption font-semibold disabled:opacity-40 shrink-0';
export const ghost = 'h-9 px-3 rounded-lg bg-surface-container text-ink font-caption text-caption disabled:opacity-40 shrink-0';
export const head = 'font-caption text-[11px] text-muted-text uppercase tracking-wider';
export const box = 'bg-surface rounded-xl border border-line p-3 space-y-2.5';
export const hint = 'font-caption text-[11px] text-muted-text leading-relaxed';

export const NO_SHARE: Record<ShareKey, boolean> = { days: false, hours: false, proud: false, focus: false, habits: false };

// Mirrors the backend rules (crew_service.py) so mistakes are caught before a round trip.
export const USERNAME_RE = /^[a-z][a-z0-9_]{2,19}$/;
export const CODE_RE = /^[0-9a-f]{24}$/;
export const USERNAME_HINT = 'Usernames are 3-20 characters: lowercase letters, numbers or _, starting with a letter.';
export const CODE_HINT = 'Invite codes are 24 letters and numbers (0-9, a-f).';

export const cleanHandle = (v: string): string => v.trim().replace(/^@+/, '').toLowerCase();
export const cleanCode = (v: string): string => v.replace(/\s+/g, '').toLowerCase();
export const validateHandle = (v: string): string | null => (USERNAME_RE.test(v) ? null : USERNAME_HINT);
export const validateCode = (v: string): string | null => (CODE_RE.test(v) ? null : CODE_HINT);

/** "Oct 20" from a calendar date like 2026-10-20. */
export function dayLabel(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** "Oct 31" from a timestamp. */
export function stampLabel(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
