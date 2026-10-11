const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

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

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
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

export function isDemoMode(): boolean {
  const pref = localStorage.getItem('lockin_demo_mode');
  return pref === null ? !getAuthToken() : pref === 'true';
}

export function setDemoMode(demo: boolean): void {
  localStorage.setItem('lockin_demo_mode', String(demo));
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getAuthToken();
  const headers = new Headers(options.headers || {});
  const method = (options.method || 'GET').toUpperCase();

  if (method !== 'GET' && method !== 'HEAD' && !headers.has('Content-Type')) {
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

  try {
    const res = await fetch(url, {
      ...options,
      headers,
    });

    if (res.status === 204) {
      return undefined as T;
    }

    const data = await res.json().catch(() => null);

    if (!res.ok) {
      throw new ApiError(formatApiDetail(data, res.status), res.status, data);
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
