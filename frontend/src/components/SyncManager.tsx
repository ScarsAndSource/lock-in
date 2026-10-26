import React, { useEffect, useState } from 'react';
import { useApp } from '../context/AppContext';
import { pendingCount, replay, subscribe } from '../lib/offlineQueue';
import { reportEvent } from '../lib/monitoring';
import { Sheet } from './Sheet';
import { SupportCard } from './SupportCard';
import type { SupportPayload } from '../types';

const FIRST_RETRY_MS = 5_000;
const MAX_RETRY_MS = 5 * 60_000;

/**
 * Sends the offline queue whenever it can: on start, when the phone comes back online, when the app returns to the
 * foreground, and on a backing-off timer while entries are still waiting (the "online" event is unreliable on weak data).
 * Renders nothing, except the support sheet when a replayed entry's text tripped the server's crisis screen: that
 * reply arrives long after the person typed it, so it is shown here instead of being lost.
 */
export const SyncManager: React.FC = () => {
  const { token, demoMode, showToast, bumpData } = useApp();
  const [support, setSupport] = useState<SupportPayload | null>(null);

  useEffect(() => {
    if (demoMode || !token) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let scheduled = false;
    let failures = 0;

    const schedule = (ms: number) => {
      clearTimeout(timer);
      scheduled = true;
      timer = setTimeout(() => void run(), ms);
    };

    const run = async () => {
      clearTimeout(timer);
      scheduled = false;
      const res = await replay();
      if (!alive) return;
      if (res.synced > 0) {
        showToast(res.synced === 1 ? 'Synced 1 offline entry' : `Synced ${res.synced} offline entries`);
        bumpData();
      }
      if (res.dropped.length > 0) {
        res.dropped.forEach((d) => reportEvent('offline_entry_dropped', { kind: d.kind, status: d.status }));
        showToast(
          res.dropped.length === 1
            ? "1 offline entry couldn't be saved"
            : `${res.dropped.length} offline entries couldn't be saved`
        );
      }
      if (res.support) setSupport(res.support);
      if (res.remaining > 0) {
        failures += 1;
        schedule(Math.min(FIRST_RETRY_MS * 2 ** (failures - 1), MAX_RETRY_MS));
      } else {
        failures = 0;
      }
    };

    const onOnline = () => {
      failures = 0;
      void run();
    };
    const onVisible = () => {
      if (document.visibilityState === 'visible') void run();
    };

    // A write that just got queued (live attempt failed): try again soon, without waiting for an "online" event.
    const off = subscribe(() => {
      void pendingCount().then((n) => {
        if (alive && n > 0 && !scheduled) schedule(FIRST_RETRY_MS);
      });
    });
    window.addEventListener('online', onOnline);
    document.addEventListener('visibilitychange', onVisible);
    void run();

    return () => {
      alive = false;
      clearTimeout(timer);
      off();
      window.removeEventListener('online', onOnline);
      document.removeEventListener('visibilitychange', onVisible);
    };
    // showToast / bumpData are stable callbacks
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, demoMode]);

  return (
    <Sheet open={support !== null} onClose={() => setSupport(null)} title="About something you saved earlier" eyebrow="Support">
      {support && (
        <div className="space-y-3">
          <p className="font-small text-small text-muted-text">
            An entry you wrote while offline has just synced. If it is still true for you, these are here now.
          </p>
          <SupportCard support={support} />
        </div>
      )}
    </Sheet>
  );
};
