const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(message: string, status: number, data?: any) {
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
  // Default to demo mode if no token is configured, so frontend works smoothly out-of-the-box
  return pref === null ? !getAuthToken() : pref === 'true';
}

export function setDemoMode(demo: boolean): void {
  localStorage.setItem('lockin_demo_mode', String(demo));
}

export async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getAuthToken();
  const headers = new Headers(options.headers || {});

  headers.set('Content-Type', 'application/json');
  headers.set('X-Request-ID', `web-${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 7)}`);

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
      return {} as T;
    }

    const data = await res.json().catch(() => null);

    if (!res.ok) {
      const errorMsg = data?.detail || `API request failed with status ${res.status}`;
      throw new ApiError(errorMsg, res.status, data);
    }

    return data as T;
  } catch (err: any) {
    if (err instanceof ApiError) {
      throw err;
    }
    throw new ApiError(err?.message || 'Network error or backend unreachable', 0);
  }
}
