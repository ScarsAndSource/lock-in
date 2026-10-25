import React, { useState } from 'react';
import { authConfigured, sendMagicLink, signIn, signUp, adoptBearerToken } from '../api/auth';
import { setDemoMode } from '../api/client';

type Mode = 'signin' | 'signup';

const inputClass =
  'w-full bg-surface-container-low border border-line rounded-lg px-3 py-2.5 text-base text-ink font-body-default';
const primaryClass =
  'w-full h-11 bg-ink text-ground-chalk rounded-lg font-body-strong disabled:opacity-60 hover:bg-secondary transition-colors';
const secondaryClass =
  'w-full h-10 bg-surface-container text-ink border border-line rounded-lg font-small-medium disabled:opacity-60 hover:bg-secondary-fixed transition-colors';

export const LoginScreen: React.FC = () => {
  const [mode, setMode] = useState<Mode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [tokenInput, setTokenInput] = useState('');

  const reset = () => {
    setError(null);
    setNotice(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    reset();
    const cleanEmail = email.trim();
    if (!cleanEmail || !password) {
      setError('Enter your email and password.');
      return;
    }
    if (mode === 'signup' && password.length < 8) {
      setError('Use at least 8 characters for the password.');
      return;
    }
    setBusy(true);
    try {
      if (mode === 'signin') {
        await signIn(cleanEmail, password);
        window.location.reload();
      } else {
        const result = await signUp(cleanEmail, password);
        if (result === 'signed-in') {
          window.location.reload();
        } else {
          setNotice('Account created. Check your email for the confirmation link, then come back here.');
          setMode('signin');
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Try again.');
    } finally {
      setBusy(false);
    }
  };

  const handleMagicLink = async () => {
    reset();
    const cleanEmail = email.trim();
    if (!cleanEmail) {
      setError('Enter your email first.');
      return;
    }
    setBusy(true);
    try {
      await sendMagicLink(cleanEmail);
      setNotice('If that email has an account, a sign-in link is on its way.');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not send the link.');
    } finally {
      setBusy(false);
    }
  };

  const handleDemo = () => {
    setDemoMode(true);
    window.location.reload();
  };

  const handleToken = (e: React.FormEvent) => {
    e.preventDefault();
    if (!tokenInput.trim()) return;
    adoptBearerToken(tokenInput);
    window.location.reload();
  };

  return (
    <div className="min-h-screen text-ink flex flex-col items-center justify-center px-margin py-space-xl">
      <div className="w-full max-w-sm space-y-4">
        <div className="space-y-1 text-center">
          <h1 className="font-title text-title text-ink">Lock’in</h1>
          <p className="font-small text-small text-muted-text">
            {mode === 'signin' ? 'Sign in to pick up where you left off.' : 'Create your account.'}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="bg-surface rounded-xl p-5 border border-line shadow-sm space-y-3">
          {!authConfigured && (
            <p className="font-caption text-caption text-on-error-container bg-error-container rounded-lg px-3 py-2">
              Sign-in isn’t configured in this build (VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY). You can still try
              the demo below.
            </p>
          )}
          {error && (
            <p role="alert" className="font-caption text-caption text-on-error-container bg-error-container rounded-lg px-3 py-2">
              {error}
            </p>
          )}
          {notice && (
            <p role="status" className="font-caption text-caption text-ink bg-domain-study-tint rounded-lg px-3 py-2">
              {notice}
            </p>
          )}

          <label className="block space-y-1">
            <span className="font-caption text-caption text-muted-text">Email</span>
            <input
              type="email"
              inputMode="email"
              autoComplete="email"
              autoCapitalize="none"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputClass}
              placeholder="you@example.com"
            />
          </label>
          <label className="block space-y-1">
            <span className="font-caption text-caption text-muted-text">Password</span>
            <input
              type="password"
              autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
              placeholder={mode === 'signin' ? 'Your password' : 'At least 8 characters'}
            />
          </label>

          <button type="submit" disabled={busy || !authConfigured} className={primaryClass}>
            {busy ? 'One moment…' : mode === 'signin' ? 'Sign in' : 'Create account'}
          </button>
          <button
            type="button"
            disabled={busy || !authConfigured}
            onClick={handleMagicLink}
            className={secondaryClass}
          >
            Email me a sign-in link instead
          </button>
          <button
            type="button"
            onClick={() => {
              reset();
              setMode(mode === 'signin' ? 'signup' : 'signin');
            }}
            className="w-full font-caption text-caption text-muted-text underline underline-offset-2"
          >
            {mode === 'signin' ? 'New here? Create an account' : 'Already have an account? Sign in'}
          </button>
        </form>

        <button type="button" onClick={handleDemo} className={secondaryClass}>
          Try the demo (nothing is saved)
        </button>

        <details className="font-caption text-caption text-muted-text">
          <summary className="cursor-pointer text-center">Developer: use a bearer token</summary>
          <form onSubmit={handleToken} className="mt-2 space-y-2">
            <input
              type="password"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              className={inputClass}
              placeholder="eyJhbGciOiJIUzI1NiIs..."
            />
            <button type="submit" className={secondaryClass}>
              Use token
            </button>
          </form>
        </details>
      </div>
    </div>
  );
};
