/**
 * Supabase Auth (GoTrue) over plain fetch: email + password, email-confirmation / magic-link return,
 * and silent refresh. No SDK, so no extra dependency. The access token lives where api/client.ts already
 * reads it ('lockin_auth_token'); the refresh token lives in 'lockin_session'.
 */
import { getAuthToken, registerAuthHooks, setAuthToken, setDemoMode } from './client';

const SUPABASE_URL = ((import.meta.env.VITE_SUPABASE_URL as string | undefined) || '').replace(/\/+$/, '');
const ANON_KEY = (import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined) || '';
const SESSION_KEY = 'lockin_session';

export const authConfigured: boolean = Boolean(SUPABASE_URL && ANON_KEY);

interface Session {
  access_token: string;
  refresh_token: string;
  expires_at: number; // epoch seconds
}

interface AuthResponse {
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
  expires_at?: number;
  error?: string;
  error_description?: string;
  msg?: string;
  message?: string;
}

function readSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Partial<Session>;
    if (typeof s.access_token === 'string' && typeof s.refresh_token === 'string') {
      return { access_token: s.access_token, refresh_token: s.refresh_token, expires_at: Number(s.expires_at) || 0 };
    }
  } catch {
    /* corrupt entry: treat as signed out */
  }
  return null;
}

function writeSession(s: Session | null): void {
  if (s) {
    localStorage.setItem(SESSION_KEY, JSON.stringify(s));
    setAuthToken(s.access_token);
  } else {
    localStorage.removeItem(SESSION_KEY);
    setAuthToken(null);
  }
}

function sessionFrom(r: AuthResponse): Session | null {
  if (!r.access_token || !r.refresh_token) return null;
  const expiresAt = r.expires_at ?? Math.floor(Date.now() / 1000) + (r.expires_in ?? 3600);
  return { access_token: r.access_token, refresh_token: r.refresh_token, expires_at: expiresAt };
}

async function gotrue(
  path: string,
  body: unknown,
  token?: string
): Promise<{ ok: boolean; status: number; data: AuthResponse }> {
  const res = await fetch(`${SUPABASE_URL}/auth/v1${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      apikey: ANON_KEY,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  const data = (await res.json().catch(() => ({}))) as AuthResponse;
  return { ok: res.ok, status: res.status, data };
}

function errText(data: AuthResponse, fallback: string): string {
  return data.error_description || data.msg || data.message || data.error || fallback;
}

function redirectQuery(): string {
  return `redirect_to=${encodeURIComponent(window.location.origin)}`;
}

function requireConfigured(): void {
  if (!authConfigured) {
    throw new Error('Sign-in is not configured for this build (missing VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY).');
  }
}

export async function signIn(email: string, password: string): Promise<void> {
  requireConfigured();
  const r = await gotrue('/token?grant_type=password', { email, password });
  if (!r.ok) throw new Error(errText(r.data, 'Sign-in failed. Check your email and password.'));
  const session = sessionFrom(r.data);
  if (!session) throw new Error('Sign-in failed: the auth service returned no session.');
  writeSession(session);
  setDemoMode(false);
}

/** 'signed-in' when the project auto-confirms accounts, otherwise 'confirm-email'. */
export async function signUp(email: string, password: string): Promise<'signed-in' | 'confirm-email'> {
  requireConfigured();
  const r = await gotrue(`/signup?${redirectQuery()}`, { email, password });
  if (!r.ok) throw new Error(errText(r.data, 'Could not create the account.'));
  const session = sessionFrom(r.data);
  if (session) {
    writeSession(session);
    setDemoMode(false);
    return 'signed-in';
  }
  return 'confirm-email';
}

/** One-tap sign-in link by email; doubles as "forgot password". */
export async function sendMagicLink(email: string): Promise<void> {
  requireConfigured();
  const r = await gotrue(`/otp?${redirectQuery()}`, { email, create_user: false });
  if (!r.ok) throw new Error(errText(r.data, 'Could not send the sign-in link.'));
}

/** Dev escape hatch: use a bearer token you already have (no refresh possible). */
export function adoptBearerToken(token: string): void {
  localStorage.removeItem(SESSION_KEY);
  setAuthToken(token.trim() || null);
  setDemoMode(false);
}

export async function signOut(): Promise<void> {
  const token = getAuthToken();
  if (authConfigured && token) {
    try {
      await gotrue('/logout', {}, token);
    } catch {
      /* best effort: the local session is cleared regardless */
    }
  }
  writeSession(null);
  localStorage.removeItem('lockin_demo_mode');
  window.location.reload();
}

let refreshing: Promise<string | null> | null = null;

/** New access token | null (session definitively dead) | throws (network / auth service down). Deduplicated. */
async function refreshSession(): Promise<string | null> {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    const current = readSession();
    if (!current || !authConfigured) return null; // a pasted token cannot be refreshed
    const r = await gotrue('/token?grant_type=refresh_token', { refresh_token: current.refresh_token });
    if (!r.ok) {
      if (r.status >= 500) throw new Error('Auth service unavailable.');
      return null;
    }
    const fresh = sessionFrom(r.data);
    if (!fresh) return null;
    writeSession(fresh);
    return fresh.access_token;
  })().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

/** Email-confirmation and magic links come back as #access_token=...&refresh_token=...; adopt them and clean the URL. */
function captureSessionFromUrl(): void {
  const hash = window.location.hash;
  if (!hash || hash.length < 2) return;
  const params = new URLSearchParams(hash.slice(1));
  const access = params.get('access_token');
  const refresh = params.get('refresh_token');
  if (!access || !refresh) return;
  const expiresAt = Number(params.get('expires_at')) || Math.floor(Date.now() / 1000) + (Number(params.get('expires_in')) || 3600);
  writeSession({ access_token: access, refresh_token: refresh, expires_at: expiresAt });
  setDemoMode(false);
  window.history.replaceState(null, '', window.location.pathname + window.location.search);
}

/** Call once, before the first render. */
export function startAuth(): void {
  captureSessionFromUrl();
  registerAuthHooks({
    refresh: refreshSession,
    onLost: () => {
      writeSession(null);
      window.location.reload();
    },
  });
}
