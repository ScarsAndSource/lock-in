import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, ReactNode } from 'react';
import { useApp } from './AppContext';
import { errorMessage } from '../lib/format';
import {
  getBuddies, getCrewInbox, getCrewOverview, getDuels, markCrewInboxSeen,
  type BuddyOverview, type CrewInbox, type CrewOverview, type Duel, type ShareKey,
} from '../api/crew';

/** The four slices of crew data. Every action reloads only the slices it can have changed. */
export type CrewPart = 'overview' | 'inbox' | 'buddies' | 'duels';
export const ALL_PARTS: readonly CrewPart[] = ['overview', 'inbox', 'buddies', 'duels'];

const STALE_MS = 30_000;
const ANSWERED_KEY = 'lockin_crew_answered';

/** How many things are waiting on the person. Drives the dot on the Crew tab. Never counts a missed day or a rank. */
export function crewAttention(
  overview: CrewOverview | null,
  inbox: CrewInbox | null,
  buddies: BuddyOverview | null,
  duels: readonly Duel[],
): number {
  let n = overview?.invites.length ?? 0;
  n += inbox?.cheers.filter((c) => !c.seen).length ?? 0;
  n += inbox?.boosts.filter((b) => !b.seen).length ?? 0;
  n += buddies?.messages.filter((m) => !m.seen).length ?? 0;
  n += buddies?.deals.filter((d) => (d.role === 'owner' && d.due) || (d.role === 'buddy' && d.status === 'pending')).length ?? 0;
  n += duels.filter((d) => d.role === 'opponent' && d.status === 'pending').length;
  return n;
}

function readAnswered(): string[] {
  try {
    const raw = localStorage.getItem(ANSWERED_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string') : [];
  } catch {
    return [];
  }
}

interface ActOptions {
  ok?: string;
  reload?: readonly CrewPart[];
}

interface CrewContextType {
  /** Signed in with a real account. Crew does not exist in demo mode. */
  live: boolean;
  overview: CrewOverview | null;
  inbox: CrewInbox | null;
  buddies: BuddyOverview | null;
  duels: Duel[];
  loading: boolean;
  error: string | null;
  busy: boolean;
  attention: number;
  /** Boost ids the person already answered with a hello. */
  answered: ReadonlySet<string>;
  reload: (parts?: readonly CrewPart[]) => Promise<void>;
  /** Reload everything unless it was loaded in the last 30 seconds. */
  refresh: () => Promise<void>;
  /** Run one request, toast its outcome, reload the slices it touched. Resolves true when the request succeeded. */
  act: (fn: () => Promise<unknown>, opts?: ActOptions) => Promise<boolean>;
  /** Optimistic share-menu update, so a checkbox flips instantly. */
  patchShare: (share: Partial<Record<ShareKey, boolean>>) => void;
  markSeen: () => Promise<void>;
  markAnswered: (id: string) => void;
}

const CrewContext = createContext<CrewContextType | undefined>(undefined);

export const CrewProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { demoMode, token, showToast, dataEpoch } = useApp();
  const live = !demoMode && !!token;

  const [overview, setOverview] = useState<CrewOverview | null>(null);
  const [inbox, setInbox] = useState<CrewInbox | null>(null);
  const [buddies, setBuddies] = useState<BuddyOverview | null>(null);
  const [duels, setDuels] = useState<Duel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyCount, setBusyCount] = useState(0);
  const [answered, setAnswered] = useState<ReadonlySet<string>>(() => new Set(readAnswered()));

  const seqs = useRef<Record<CrewPart, number>>({ overview: 0, inbox: 0, buddies: 0, duels: 0 });
  const lastLoad = useRef(0);
  const engaged = useRef(false); // in at least one crew: only then are inbox, deals and duels worth fetching

  const clearAll = useCallback(() => {
    (Object.keys(seqs.current) as CrewPart[]).forEach((k) => { seqs.current[k] += 1; }); // drop anything in flight
    engaged.current = false;
    setOverview(null);
    setInbox(null);
    setBuddies(null);
    setDuels([]);
    setError(null);
  }, []);

  const reload = useCallback(
    async (parts: readonly CrewPart[] = ALL_PARTS) => {
      if (!live) return;
      lastLoad.current = Date.now();

      // Each slice has its own sequence number, so a slow older response never overwrites a newer one.
      const fetchPart = async (part: CrewPart): Promise<void> => {
        const s = ++seqs.current[part];
        const fresh = () => s === seqs.current[part];
        if (part === 'overview') {
          const v = await getCrewOverview();
          if (!fresh()) return;
          engaged.current = !!v.username && v.crews.length > 0;
          setOverview(v);
        } else if (part === 'inbox') {
          const v = await getCrewInbox();
          if (fresh()) setInbox(v);
        } else if (part === 'buddies') {
          const v = await getBuddies();
          if (fresh()) setBuddies(v);
        } else {
          const v = await getDuels();
          if (fresh()) setDuels(v.duels);
        }
      };

      try {
        const wanted = new Set(parts);
        if (wanted.has('overview')) await fetchPart('overview'); // first: it says whether the rest is worth asking for
        const rest = (['inbox', 'buddies', 'duels'] as const).filter((p) => wanted.has(p));
        if (engaged.current) {
          await Promise.all(rest.map(fetchPart));
        } else if (wanted.has('overview')) {
          setInbox(null);
          setBuddies(null);
          setDuels([]);
        }
        setError(null);
      } catch (e) {
        setError(errorMessage(e));
      } finally {
        setLoading(false);
      }
    },
    [live],
  );

  const refresh = useCallback(async () => {
    if (Date.now() - lastLoad.current < STALE_MS) return;
    await reload();
  }, [reload]);

  // Load on sign-in, reset on sign-out or account switch. This is also what feeds the tab badge before the tab is opened.
  useEffect(() => {
    clearAll();
    if (!live) {
      setLoading(false);
      return;
    }
    setLoading(true);
    void reload();
  }, [live, token, clearAll, reload]);

  // Coming back to the app is when a cheer or an invite is most likely to be waiting.
  useEffect(() => {
    if (!live) return;
    const onBack = () => {
      if (document.visibilityState === 'visible') void refresh();
    };
    window.addEventListener('focus', onBack);
    document.addEventListener('visibilitychange', onBack);
    return () => {
      window.removeEventListener('focus', onBack);
      document.removeEventListener('visibilitychange', onBack);
    };
  }, [live, refresh]);

  // A check-in can make a buddy deal come due, so re-ask only that slice, and only for people who have deals to ask about.
  const epoch = useRef(dataEpoch);
  useEffect(() => {
    if (epoch.current === dataEpoch) return;
    epoch.current = dataEpoch;
    if (live && engaged.current) void reload(['buddies']);
  }, [dataEpoch, live, reload]);

  useEffect(() => {
    try {
      localStorage.setItem(ANSWERED_KEY, JSON.stringify([...answered].slice(-50)));
    } catch {
      /* private mode: the list simply won't survive a reload */
    }
  }, [answered]);

  const act = useCallback(
    async (fn: () => Promise<unknown>, opts?: ActOptions): Promise<boolean> => {
      setBusyCount((n) => n + 1);
      let ok = false;
      try {
        await fn();
        ok = true;
        if (opts?.ok) showToast(opts.ok);
      } catch (e) {
        showToast(errorMessage(e));
      }
      // Reload even after a failure: "that invite is gone" means the list on screen is stale.
      if (opts?.reload?.length) await reload(opts.reload);
      setBusyCount((n) => n - 1);
      return ok;
    },
    [reload, showToast],
  );

  const patchShare = useCallback((share: Partial<Record<ShareKey, boolean>>) => {
    setOverview((o) => (o ? { ...o, share } : o));
  }, []);

  const markSeen = useCallback(async () => {
    if (!live) return;
    try {
      await markCrewInboxSeen();
      setInbox((i) => (i ? { cheers: i.cheers.map((c) => ({ ...c, seen: true })), boosts: i.boosts.map((b) => ({ ...b, seen: true })) } : i));
      setBuddies((b) => (b ? { ...b, messages: b.messages.map((m) => ({ ...m, seen: true })) } : b));
    } catch {
      /* the list still shows what was new; the dot clears on the next successful open */
    }
  }, [live]);

  const markAnswered = useCallback((id: string) => {
    setAnswered((prev) => (prev.has(id) ? prev : new Set(prev).add(id)));
  }, []);

  const attention = useMemo(() => crewAttention(overview, inbox, buddies, duels), [overview, inbox, buddies, duels]);

  const value = useMemo<CrewContextType>(
    () => ({
      live, overview, inbox, buddies, duels, loading, error, busy: busyCount > 0, attention, answered,
      reload, refresh, act, patchShare, markSeen, markAnswered,
    }),
    [live, overview, inbox, buddies, duels, loading, error, busyCount, attention, answered, reload, refresh, act, patchShare, markSeen, markAnswered],
  );

  return <CrewContext.Provider value={value}>{children}</CrewContext.Provider>;
};

export function useCrew(): CrewContextType {
  const ctx = useContext(CrewContext);
  if (!ctx) throw new Error('useCrew must be used within a CrewProvider');
  return ctx;
}
