import { useEffect } from 'react';

/** Where a notification tap lands: /?a=checkin, /?a=habit, /?a=tasks, /?a=plan, /?a=sleep, /?a=study, /?a=focus, /?a=comeback, /?a=insight, /?a=future */
export type DeepLink = 'checkin' | 'habit' | 'tasks' | 'plan' | 'sleep' | 'study' | 'focus' | 'comeback' | 'insight' | 'future';
const KNOWN: ReadonlySet<string> = new Set([
  'checkin', 'habit', 'tasks', 'plan', 'sleep', 'study', 'focus', 'comeback', 'insight', 'future',
]);

export interface DeepLinkParams {
  link: DeepLink;
  k?: string;
  id?: string;
}

/** Reads ?a=... and associated params (?k=..., ?id=...), removes them from the address bar
 *  (a refresh must not re-trigger it) and returns them. */
export function consumeDeepLink(): DeepLinkParams | null {
  const url = new URL(window.location.href);
  const a = url.searchParams.get('a');
  if (!a || !KNOWN.has(a)) return null;
  const k = url.searchParams.get('k') || undefined;
  const id = url.searchParams.get('id') || undefined;
  url.searchParams.delete('a');
  url.searchParams.delete('k');
  url.searchParams.delete('id');
  window.history.replaceState(null, '', url.pathname + (url.search || '') + url.hash);
  return { link: a as DeepLink, k, id };
}

/**
 * Call once near the top of the signed-in app. `handle` decides what each link opens, for example:
 *   checkin -> show the "Lock it / Rough day" sheet (runInAppAction('checkin', 'lock'))
 *   plan    -> open the person's own if-then plan
 *   focus   -> open the focused item (?k=task|habit&id=...)
 *   comeback-> open the comeback habit (?id=...)
 * It also fires when the service worker focuses an already-open window, because that navigates to the deep link.
 */
export function useDeepLink(handle: (link: DeepLink, params?: { k?: string; id?: string }) => void): void {
  useEffect(() => {
    const run = () => {
      const res = consumeDeepLink();
      if (res) handle(res.link, { k: res.k, id: res.id });
    };
    run();
    window.addEventListener('focus', run);
    return () => window.removeEventListener('focus', run);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
