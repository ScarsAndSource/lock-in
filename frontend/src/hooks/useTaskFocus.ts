import { useCallback, useEffect, useRef, useState } from 'react';
import { useApp } from '../context/AppContext';
import { getTaskFocus } from '../api/tasks';
import type { TaskFocus } from '../types';

const REFRESH_MS = 60_000;

/** One shared task-focus load for the whole Now screen (the next-action card and the list read the same data). */
export function useTaskFocus(): { focus: TaskFocus | null; reload: () => Promise<void> } {
  const { demoMode, dataEpoch } = useApp();
  const [focus, setFocus] = useState<TaskFocus | null>(null);
  const alive = useRef(true);

  const reload = useCallback(async () => {
    try {
      const f = await getTaskFocus();
      if (alive.current) setFocus(f);
    } catch {
      /* keep what we have; the next refresh retries */
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void reload();
    // No polling while the app is in the background: the visibility handler catches up the moment it returns.
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void reload();
    }, REFRESH_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') void reload();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [reload, demoMode, dataEpoch]);

  return { focus, reload };
}
