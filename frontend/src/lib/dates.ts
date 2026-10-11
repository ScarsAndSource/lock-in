/** Calendar dates as YYYY-MM-DD. Never use `new Date('YYYY-MM-DD')` — that is UTC midnight and shifts in IST. */

export function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

export function localTodayISO(timeZone?: string): string {
  if (timeZone) {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(new Date());
    const y = parts.find((p) => p.type === 'year')?.value;
    const m = parts.find((p) => p.type === 'month')?.value;
    const d = parts.find((p) => p.type === 'day')?.value;
    if (y && m && d) return `${y}-${m}-${d}`;
  }
  const now = new Date();
  return `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())}`;
}

export function parseISODate(iso: string): { y: number; m: number; d: number } {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return { y, m, d };
}

export function addDaysISO(iso: string, days: number): string {
  const { y, m, d } = parseISODate(iso);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + days);
  return `${dt.getFullYear()}-${pad2(dt.getMonth() + 1)}-${pad2(dt.getDate())}`;
}

export function weekdayIndexMon0(iso: string): number {
  const { y, m, d } = parseISODate(iso);
  const js = new Date(y, m - 1, d).getDay(); // 0=Sun
  return (js + 6) % 7; // 0=Mon
}

export function formatDayHeading(iso: string): string {
  const { y, m, d } = parseISODate(iso);
  const dt = new Date(y, m - 1, d);
  return dt.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
}

export function formatDayShort(iso: string): string {
  const { m, d } = parseISODate(iso);
  const dt = new Date(2000, m - 1, d);
  return `${d} ${dt.toLocaleDateString(undefined, { month: 'short' })}`;
}

export function weekdayLetter(iso: string): string {
  const { y, m, d } = parseISODate(iso);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: 'narrow' });
}

export function clockLabel(now = new Date()): string {
  const time = now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  const hour = now.getHours();
  const band = hour < 5 ? 'Late night' : hour < 12 ? 'Morning' : hour < 17 ? 'Afternoon' : hour < 21 ? 'Evening' : 'Late evening';
  return `${time} · ${band}`;
}

export function toTimeInput(value: string | null | undefined, fallback: string): string {
  if (!value) return fallback;
  return value.slice(0, 5);
}

export function rangeDays(endISO: string, windowDays: number): { start: string; end: string } {
  return { start: addDaysISO(endISO, -(windowDays - 1)), end: endISO };
}

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}
