export const API_BASE: string =
  import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? 'http://localhost:8000' : '');

export function isNotFound(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404;
}

function formatApiDetail(data: unknown, status: number): string {
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (typeof item === 'string') return item;
          if (item && typeof item === 'object' && 'msg' in item) {
            const loc = Array.isArray((item as { loc?: unknown }).loc)
              ? (item as { loc: unknown[] }).loc.filter((p) => p !== 'body').join('.')
              : '';
            return loc ? `${loc}: ${(item as { msg: string }).msg}` : (item as { msg: string }).msg;
          }
          return JSON.stringify(item);
        })
        .join('; ');
    }
  }
  return `API request failed with status ${status}`;
}

export class ApiError extends Error {
  status: number;
  data: unknown;
  /** Seconds the server asked us to wait (Retry-After on a 429 / 503), when it said. */
  retryAfter?: number;

  constructor(message: string, status: number, data?: unknown, retryAfter?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
    this.retryAfter = retryAfter;
  }
}

/** Retry-After as whole seconds (a number of seconds, as this API sends it). Missing or not a number -> undefined. */
function retryAfterSeconds(res: Response): number | undefined {
  const raw = res.headers.get('Retry-After');
  if (!raw) return undefined;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? Math.ceil(n) : undefined;
}

export function getAuthToken(): string | null {
  return localStorage.getItem('lockin_auth_token') || null;
}

export function setAuthToken(token: string | null): void {
  if (token) {
    localStorage.setItem('lockin_auth_token', token);
  } else {
    localStorage.removeItem('lockin_auth_token');
  }
}

/** Demo (local mock data) is opt-in. A visitor with no session sees the login screen, never fake data. */
export function isDemoMode(): boolean {
  return localStorage.getItem('lockin_demo_mode') === 'true';
}

export function setDemoMode(demo: boolean): void {
  localStorage.setItem('lockin_demo_mode', String(demo));
}

/**
 * Hooks registered by api/auth.ts (kept out of this file to avoid a circular import).
 *   refresh -> a new access token, null when the session is definitively dead, or it throws on a network error.
 *   onLost  -> the session is gone: clear it and return to the login screen.
 */
interface AuthHooks {
  refresh: () => Promise<string | null>;
  onLost: () => void;
}

let authHooks: AuthHooks | null = null;

export function registerAuthHooks(hooks: AuthHooks): void {
  authHooks = hooks;
}

async function send(path: string, options: RequestInit, token: string | null): Promise<Response> {
  const headers = new Headers(options.headers || {});
  const method = (options.method || 'GET').toUpperCase();

  // A FormData body (voice / screenshot upload) must NOT get a JSON Content-Type: the browser has to set the
  // multipart boundary itself.
  const isForm = typeof FormData !== 'undefined' && options.body instanceof FormData;
  if (method !== 'GET' && method !== 'HEAD' && !isForm && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  headers.set(
    'X-Request-ID',
    `web-${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 7)}`
  );

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
  return fetch(url, { ...options, headers });
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  try {
    const token = getAuthToken();
    let res = await send(path, options, token);

    // An expired access token: refresh once and replay the request. A dead session sends the user to login.
    if (res.status === 401 && token && authHooks) {
      let fresh: string | null | undefined;
      try {
        fresh = await authHooks.refresh();
      } catch {
        fresh = undefined; // offline / auth service down: keep the session, surface the 401
      }
      if (fresh) {
        res = await send(path, options, fresh);
      } else if (fresh === null) {
        authHooks.onLost();
      }
    }

    if (res.status === 204) {
      return undefined as T;
    }

    const data = await res.json().catch(() => null);

    if (!res.ok) {
      throw new ApiError(formatApiDetail(data, res.status), res.status, data, retryAfterSeconds(res));
    }

    return data as T;
  } catch (err: unknown) {
    if (err instanceof ApiError) {
      throw err;
    }
    const message = err instanceof Error ? err.message : 'Network error or backend unreachable';
    throw new ApiError(message, 0);
  }
}
