import { useCallback, useEffect, useMemo, useState } from 'react';
import { useApp } from '../context/AppContext';
import { getJourneyState, SHOW_ALL_KEY, STAGE_CACHE_KEY, TOP_STAGE } from '../api/journey';
import type { JourneyState } from '../api/journey';

const SHOW_ALL_EVENT = 'lockin:showall';
const NO_IDS: ReadonlySet<string> = new Set<string>();

function readShowAll(): boolean {
  try {
    return localStorage.getItem(SHOW_ALL_KEY) === '1';
  } catch {
    return false;
  }
}

function readCachedStage(): number | null {
  try {
    const raw = localStorage.getItem(STAGE_CACHE_KEY);
    const n = raw === null ? NaN : Number(raw);
    return Number.isInteger(n) && n >= 0 && n <= TOP_STAGE ? n : null;
  } catch {
    return null;
  }
}

// One request per data epoch, shared by every component that asks.
let shared: { epoch: number; promise: Promise<JourneyState> } | null = null;
function loadShared(epoch: number): Promise<JourneyState> {
  if (shared === null || shared.epoch !== epoch) shared = { epoch, promise: getJourneyState() };
  return shared.promise;
}

/**
 * Slow unlock + seasons for the UI. FAIL-OPEN: any error (or demo mode, or "show everything") means the top
 * stage and no benched habits, so a bug here can never hide a feature.
 */
export function useJourney() {
  const { demoMode, dataEpoch } = useApp();
  const [state, setState] = useState<JourneyState | null>(null);
  const [failed, setFailed] = useState(false);
  const [showAll, setShowAllState] = useState<boolean>(readShowAll);

  useEffect(() => {
    if (demoMode) return;
    let cancelled = false;
    loadShared(dataEpoch)
      .then((s) => {
        if (cancelled) return;
        setState(s);
        setFailed(false);
        try {
          localStorage.setItem(STAGE_CACHE_KEY, String(s.stage));
        } catch {
          /* the cache is only there to avoid a flash */
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [demoMode, dataEpoch]);

  useEffect(() => {
    const sync = () => setShowAllState(readShowAll());
    window.addEventListener(SHOW_ALL_EVENT, sync);
    return () => window.removeEventListener(SHOW_ALL_EVENT, sync);
  }, []);

  const setShowAll = useCallback((on: boolean) => {
    try {
      localStorage.setItem(SHOW_ALL_KEY, on ? '1' : '0');
    } catch {
      /* ignore */
    }
    setShowAllState(on);
    window.dispatchEvent(new Event(SHOW_ALL_EVENT));
  }, []);

  const open = demoMode || showAll || failed;
  const stage = open ? TOP_STAGE : state ? state.stage : readCachedStage() ?? 0;
  const benched = useMemo<ReadonlySet<string>>(
    () => (open || !state ? NO_IDS : new Set(state.benched_ids)),
    [open, state],
  );

  return { stage, benched, state, showAll, setShowAll };
}
