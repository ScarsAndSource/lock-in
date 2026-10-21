import { useEffect } from 'react';

/** Where a notification tap lands: /?a=checkin, /?a=habit, /?a=tasks, /?a=plan, /?a=sleep, /?a=study */
export type DeepLink = 'checkin' | 'habit' | 'tasks' | 'plan' | 'sleep' | 'study';
const KNOWN: ReadonlySet<string> = new Set(['checkin', 'habit', 'tasks', 'plan', 'sleep', 'study']);

/** Reads ?a=..., removes it from the address bar (a refresh must not re-trigger it) and returns it. */
export function consumeDeepLink(): DeepLink | null {
  const url = new URL(window.location.href);
  const a = url.searchParams.get('a');
  if (!a) return null;
  url.searchParams.delete('a');
  window.history.replaceState(null, '', url.pathname + (url.search || '') + url.hash);
  return KNOWN.has(a) ? (a as DeepLink) : null;
}

/**
 * Call once near the top of the signed-in app. `handle` decides what each link opens, for example:
 *   checkin -> show the "Lock it / Rough day" sheet (runInAppAction('checkin', 'lock'))
 *   plan    -> open the person's own if-then plan
 * It also fires when the service worker focuses an already-open window, because that navigates to the deep link.
 */
export function useDeepLink(handle: (link: DeepLink) => void): void {
  useEffect(() => {
    const run = () => {
      const link = consumeDeepLink();
      if (link) handle(link);
    };
    run();
    window.addEventListener('focus', run);
    return () => window.removeEventListener('focus', run);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
