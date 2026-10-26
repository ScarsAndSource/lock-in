/**
 * Offline write queue for the two things people do on bad signal: the urge quick-capture and the daily check-in.
 *
 *   sendOrQueue()  tries the request with a short timeout (a dead-but-"connected" phone would otherwise hang for
 *                  minutes); if the network or a cold backend is the problem it stores the write in IndexedDB instead.
 *   replay()       sends queued writes oldest-first when we're back online. Safe to run twice:
 *                    - urge captures carry a client_id, the server returns the stored log for a repeated id
 *                    - check-in confirm is an upsert per (user, date)
 *
 * Queued items belong to the user who made them (the JWT `sub`), so another account on the same phone never sends them.
 * A replay can hand back crisis resources (the server screens the text when it finally arrives); the caller shows them.
 */
import { ApiError, getAuthToken, request } from '../api/client';
import { idbAll, idbDelete, idbGet, idbPut } from './idb';
import type { CheckinView, SupportPayload } from '../types';

export type QueueKind = 'urge' | 'checkin';

export interface QueueItem {
  id: string;
  kind: QueueKind;
  owner: string;
  createdAt: number;
  attempts: number;
  path: string;
  body: Record<string, unknown>;
  date?: string; // check-in date, used to keep one day's check-ins in order
}

export interface DroppedItem {
  kind: QueueKind;
  status: number;
  message: string;
}

export interface ReplayResult {
  synced: number;
  dropped: DroppedItem[];
  support: SupportPayload | null;
  remaining: number;
}

const MAX_ITEMS = 200;
const MAX_AGE_MS = 14 * 24 * 60 * 60 * 1000;
export const LIVE_TIMEOUT_MS = { urge: 8000, checkin: 10000 } as const;
const REPLAY_TIMEOUT_MS = 20000;

// ------------------------------------------------------------------ identity
export function newId(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  const b = new Uint8Array(16);
  c.getRandomValues(b);
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

/** Who owns a queued write: the `sub` claim of the current access token (decoded, not verified; it is only a bucket key). */
export function ownerKey(): string {
  const token = getAuthToken();
  if (!token) return 'anonymous';
  try {
    const part = token.split('.')[1];
    const json = atob(part.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(part.length / 4) * 4, '='));
    const sub = (JSON.parse(json) as { sub?: unknown }).sub;
    return typeof sub === 'string' && sub ? sub : 'unknown';
  } catch {
    return 'unknown';
  }
}

// ------------------------------------------------------------------ classification
/** Worth retrying later: no network / timeout, an expired session that may recover, a cold or overloaded backend. */
export function isTransient(status: number): boolean {
  return status === 0 || status === 401 || status === 408 || status === 429 || status === 502 || status === 503 || status === 504;
}

// ------------------------------------------------------------------ change notifications (this tab + other tabs)
type Listener = () => void;
const listeners = new Set<Listener>();
const channel: BroadcastChannel | null = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('lockin-queue') : null;

function emit(): void {
  listeners.forEach((fn) => fn());
  channel?.postMessage('changed');
}
if (channel) channel.onmessage = () => listeners.forEach((fn) => fn());

export function subscribe(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

// ------------------------------------------------------------------ storage
async function mine(): Promise<QueueItem[]> {
  const owner = ownerKey();
  return (await idbAll<QueueItem>('queue')).filter((i) => i.owner === owner).sort((a, b) => a.createdAt - b.createdAt);
}

export async function pendingCount(): Promise<number> {
  try {
    return (await mine()).length;
  } catch {
    return 0;
  }
}

export async function hasPending(kind: QueueKind, date?: string): Promise<boolean> {
  try {
    return (await mine()).some((i) => i.kind === kind && (date === undefined || i.date === date));
  } catch {
    return false;
  }
}

async function enqueue(kind: QueueKind, path: string, body: Record<string, unknown>, date?: string): Promise<void> {
  if ((await idbAll<QueueItem>('queue')).length >= MAX_ITEMS) {
    throw new ApiError('Too many unsent entries on this phone. Connect once so they can sync.', 0);
  }
  await idbPut('queue', { id: newId(), kind, owner: ownerKey(), createdAt: Date.now(), attempts: 0, path, body, date });
  emit();
}

// ------------------------------------------------------------------ live attempt, queue on failure
export type SendOutcome<T> = { queued: false; data: T } | { queued: true };

async function postWithTimeout<T>(path: string, body: unknown, ms: number): Promise<T> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    return await request<T>(path, { method: 'POST', body: JSON.stringify(body), signal: ctl.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function sendOrQueue<T>(spec: {
  kind: QueueKind;
  path: string;
  body: Record<string, unknown>;
  /** Body to store if we have to queue (an urge adds the tap time here, so the log keeps its real moment). */
  queuedBody?: Record<string, unknown>;
  date?: string;
  /** Keep order: if this day already has an unsent entry, line up behind it instead of jumping the queue. */
  keepOrder?: boolean;
}): Promise<SendOutcome<T>> {
  const stored = spec.queuedBody ?? spec.body;
  const queueIt = async (): Promise<SendOutcome<T>> => {
    await enqueue(spec.kind, spec.path, stored, spec.date);
    return { queued: true };
  };
  if (!getAuthToken()) return { queued: false, data: await request<T>(spec.path, { method: 'POST', body: JSON.stringify(spec.body) }) };
  if (navigator.onLine === false) return queueIt();
  if (spec.keepOrder && (await hasPending(spec.kind, spec.date))) return queueIt();
  try {
    return { queued: false, data: await postWithTimeout<T>(spec.path, spec.body, LIVE_TIMEOUT_MS[spec.kind]) };
  } catch (err) {
    if (err instanceof ApiError && isTransient(err.status) && getAuthToken()) return queueIt();
    throw err;
  }
}

// ------------------------------------------------------------------ replay
async function sendQueued(item: QueueItem): Promise<{ support?: SupportPayload | null } | undefined> {
  try {
    return await postWithTimeout(item.path, item.body, REPLAY_TIMEOUT_MS);
  } catch (err) {
    // The tap time came from this phone's clock. If it's ahead of the server's by more than its tolerance, keep the log and let the server stamp it.
    if (item.kind === 'urge' && err instanceof ApiError && err.status === 422 && /future/i.test(err.message) && item.body.occurred_at) {
      const { occurred_at: _drop, ...rest } = item.body;
      void _drop;
      return postWithTimeout(item.path, rest, REPLAY_TIMEOUT_MS);
    }
    throw err;
  }
}

async function doReplay(): Promise<ReplayResult> {
  const result: ReplayResult = { synced: 0, dropped: [], support: null, remaining: 0 };
  const items = await mine();
  for (const item of items) {
    if (navigator.onLine === false) break;
    if (Date.now() - item.createdAt > MAX_AGE_MS) {
      await idbDelete('queue', item.id);
      result.dropped.push({ kind: item.kind, status: 0, message: 'older than 14 days' });
      continue;
    }
    try {
      const out = await sendQueued(item);
      await idbDelete('queue', item.id);
      result.synced += 1;
      if (out?.support && !result.support) result.support = out.support;
    } catch (err) {
      if (!(err instanceof ApiError)) break;
      if (item.kind === 'urge' && err.status === 409) {
        await idbDelete('queue', item.id); // that client_id is already stored: the first attempt did land
        result.synced += 1;
        continue;
      }
      if (isTransient(err.status)) {
        await idbPut('queue', { ...item, attempts: item.attempts + 1 });
        break; // later items would fail the same way, and order matters for check-ins
      }
      await idbDelete('queue', item.id); // the server will never accept this one; retrying forever helps nobody
      result.dropped.push({ kind: item.kind, status: err.status, message: err.message });
    }
  }
  result.remaining = await pendingCount();
  emit();
  return result;
}

let running: Promise<ReplayResult> | null = null;

/** One replay at a time, in this tab (promise) and across tabs (Web Locks where available). */
export function replay(): Promise<ReplayResult> {
  if (running) return running;
  const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined;
  const job = locks
    ? locks.request('lockin-queue-replay', { ifAvailable: true }, async (lock) =>
        lock ? doReplay() : { synced: 0, dropped: [], support: null, remaining: await pendingCount() }
      )
    : doReplay();
  running = Promise.resolve(job)
    .catch((): ReplayResult => ({ synced: 0, dropped: [], support: null, remaining: 0 }))
    .finally(() => {
      running = null;
    });
  return running;
}

// ------------------------------------------------------------------ check-in snapshot (so the check-in can open offline)
interface Snapshot {
  id: string; // `${owner}:${date}`
  view: CheckinView;
  savedAt: number;
}

export async function saveCheckinSnapshot(date: string, view: CheckinView): Promise<void> {
  try {
    const owner = ownerKey();
    const keep = (await idbAll<Snapshot>('snapshot')).filter((s) => s.id.startsWith(`${owner}:`) && s.id !== `${owner}:${date}`);
    // one snapshot per user is plenty: the day being filled in
    await Promise.all(keep.map((s) => idbDelete('snapshot', s.id)));
    await idbPut('snapshot', { id: `${owner}:${date}`, view, savedAt: Date.now() });
  } catch {
    /* best effort */
  }
}

export async function loadCheckinSnapshot(date: string): Promise<CheckinView | null> {
  try {
    return (await idbGet<Snapshot>('snapshot', `${ownerKey()}:${date}`))?.view ?? null;
  } catch {
    return null;
  }
}

/** Sign-out: remove what we cached for display (check-in view, pending share). Unsent writes stay for their owner (14-day limit). */
export async function purgeLocalPersonalData(): Promise<void> {
  try {
    const [snaps, shares] = await Promise.all([idbAll<{ id: string }>('snapshot'), idbAll<{ id: string }>('share')]);
    await Promise.all([
      ...snaps.map((s) => idbDelete('snapshot', s.id)),
      ...shares.map((s) => idbDelete('share', s.id)),
    ]);
  } catch {
    /* best effort */
  }
}
