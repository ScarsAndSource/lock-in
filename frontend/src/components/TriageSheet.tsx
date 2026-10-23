import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useApp } from '../context/AppContext';
import { completeTask, deleteTask, getTaskFocus, patchTask } from '../api/tasks';
import type { Task } from '../types';
import { addDaysISO, localTodayISO } from '../lib/dates';
import { errorMessage } from '../lib/format';
import { taskMeta } from '../lib/taskLabels';
import { Sheet } from './Sheet';

interface TriageSheetProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Opened by the "a few small things" notification (and any task nudge): one task per screen, so a pile of small
 * chores gets cleared in a few taps without scrolling the whole Now tab. Done, Tomorrow, Skip, or Drop (two taps).
 * It reads the same focus the Now tab does: due now, small things, and the ones that stopped nudging.
 */
export const TriageSheet: React.FC<TriageSheetProps> = ({ open, onClose }) => {
  const { showToast, bumpData } = useApp();
  const [queue, setQueue] = useState<Task[] | null>(null);
  const [stale, setStale] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [confirmDrop, setConfirmDrop] = useState(false);
  const alive = useRef(true);

  const load = useCallback(async () => {
    try {
      const f = await getTaskFocus();
      if (!alive.current) return;
      const seen = new Set<string>();
      const all = [...f.now, ...f.small, ...f.stale].filter((t) => (seen.has(t.id) ? false : (seen.add(t.id), true)));
      setStale(new Set(f.stale.map((t) => t.id)));
      setQueue(all);
    } catch (err: unknown) {
      if (!alive.current) return;
      showToast(errorMessage(err, 'Could not load your tasks'));
      setQueue([]);
    }
  }, [showToast]);

  useEffect(() => {
    alive.current = true;
    if (open) {
      setQueue(null);
      setConfirmDrop(false);
      void load();
    }
    return () => {
      alive.current = false;
    };
  }, [open, load]);

  const current = queue && queue.length > 0 ? queue[0] : null;

  const finish = (id: string) => {
    setQueue((q) => (q ? q.filter((t) => t.id !== id) : q));
    setConfirmDrop(false);
    bumpData(); // the Now tab reloads its own list
  };

  const run = async (t: Task, fn: () => Promise<unknown>, okMsg?: string) => {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
      if (okMsg) showToast(okMsg);
      finish(t.id);
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Something went wrong'));
    } finally {
      setBusy(false);
    }
  };

  const skip = () => {
    setConfirmDrop(false);
    setQueue((q) => (q && q.length > 1 ? [...q.slice(1), q[0]] : q));
  };

  const chip =
    'flex-1 h-10 rounded-xl bg-surface-container text-ink font-caption text-caption font-semibold hover:bg-secondary-fixed disabled:opacity-50';

  return (
    <Sheet
      open={open}
      onClose={onClose}
      eyebrow={queue && queue.length > 0 ? `${queue.length} left` : 'Small things'}
      title="Clear a few"
    >
      {queue === null && <p className="py-6 text-center font-small text-muted-text">Loading…</p>}

      {queue !== null && !current && (
        <div className="py-6 text-center space-y-3">
          <p className="font-body-strong text-ink">All clear.</p>
          <button type="button" onClick={onClose} className="px-5 h-10 rounded-xl bg-ink text-ground-chalk font-caption text-caption font-semibold">
            Close
          </button>
        </div>
      )}

      {current && (
        <div className="space-y-4">
          <div className="space-y-1 py-2">
            <p className="font-section text-section text-ink break-words">{current.title}</p>
            {taskMeta(current) && <p className="font-caption text-caption text-muted-text">{taskMeta(current)}</p>}
            {stale.has(current.id) && (
              <p className="font-caption text-caption text-muted-text">I stopped reminding you about this one. Keep it or drop it?</p>
            )}
          </div>

          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run(
                current,
                () => completeTask(current.id),
                current.repeat_days ? `Done. Next one in ${current.repeat_days} day${current.repeat_days === 1 ? '' : 's'}.` : undefined
              )
            }
            className="w-full h-12 rounded-xl bg-ink text-ground-chalk font-body-strong disabled:opacity-50"
          >
            Done
          </button>

          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy}
              className={chip}
              onClick={() => void run(current, () => patchTask(current.id, { due: addDaysISO(localTodayISO(), 1) }), 'Moved to tomorrow.')}
            >
              Tomorrow
            </button>
            <button type="button" disabled={busy || (queue?.length ?? 0) < 2} className={chip} onClick={skip}>
              Skip
            </button>
            <button
              type="button"
              disabled={busy}
              className={chip}
              onClick={() => (confirmDrop ? void run(current, () => deleteTask(current.id)) : setConfirmDrop(true))}
            >
              {confirmDrop ? 'Tap to drop' : 'Drop'}
            </button>
          </div>
        </div>
      )}
    </Sheet>
  );
};
