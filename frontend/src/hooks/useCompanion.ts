import { useCallback, useEffect, useRef, useState } from 'react';
import { useApp } from '../context/AppContext';
import { getCompanionNow, postCompanionEvent } from '../api/companion';
import type { CompanionNow } from '../api/companion';

const REFRESH_MS = 60_000;
const REOPEN_AFTER_MS = 30 * 60_000; // coming back after half an hour counts as opening the app again

// Module-level on purpose: one "app opened" signal per real open, however often the Now screen remounts.
let lastOpenSignal = 0;

function signalOpen(): void {
  const now = Date.now();
  if (now - lastOpenSignal < REOPEN_AFTER_MS) return;
  lastOpenSignal = now;
  postCompanionEvent('app_open');
}

/**
 * The companion's answer for right now: the one thing to do, the shape of the day, the tone. Re-asks when the person
 * logs something, says "not now", comes back to the tab, and once a minute while visible. Null in demo mode or when
 * the server can't be reached, so the screen falls back to the on-device ranking instead of going blank.
 */
export function useCompanion(skipped: ReadonlySet<string>): { data: CompanionNow | null; refresh: () => Promise<void> } {
  const { demoMode, dataEpoch } = useApp();
  const [data, setData] = useState<CompanionNow | null>(null);
  const skippedRef = useRef(skipped);
  skippedRef.current = skipped;
  const seq = useRef(0);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const next = await getCompanionNow(Array.from(skippedRef.current));
      if (alive.current && mine === seq.current) setData(next);
    } catch {
      if (alive.current && mine === seq.current) setData(null);
    }
  }, []);

  const skipSignature = Array.from(skipped).sort().join('|');

  useEffect(() => {
    void refresh();
  }, [refresh, demoMode, dataEpoch, skipSignature]);

  useEffect(() => {
    alive.current = true;
    signalOpen();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh();
    }, REFRESH_MS);
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      signalOpen();
      void refresh();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [refresh]);

  return { data, refresh };
}
