import { useEffect, useState } from 'react';
import { pendingCount, subscribe } from '../lib/offlineQueue';

/** How many offline entries (urges, check-ins) are waiting to be sent for the signed-in user. `who` re-reads it on account change. */
export function usePendingSync(who: string | null): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let alive = true;
    const refresh = () => {
      void pendingCount().then((n) => {
        if (alive) setCount(n);
      });
    };
    refresh();
    const off = subscribe(refresh);
    return () => {
      alive = false;
      off();
    };
  }, [who]);
  return count;
}
