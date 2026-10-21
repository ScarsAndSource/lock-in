import React, { useMemo, useState } from 'react';
import { useApp } from '../context/AppContext';
import { logHabit } from '../api/habits';
import { completeTask } from '../api/tasks';
import { pickNextAction } from '../lib/nextAction';
import { errorMessage } from '../lib/format';
import type { TaskFocus } from '../types';

interface NextCardProps {
  focus: TaskFocus | null;
  reloadFocus: () => Promise<void>;
}

const EMPTY: ReadonlySet<string> = new Set<string>();

/** The one thing to do now. One button. "Not now" hides it for this session and shows the next candidate. */
export const NextCard: React.FC<NextCardProps> = ({ focus, reloadFocus }) => {
  const { checkinView, checkinLoading, refreshCheckinView, activeDate, bumpData, showToast, setCheckinModalOpen } =
    useApp();
  const [skipped, setSkipped] = useState<ReadonlySet<string>>(EMPTY);
  const [busy, setBusy] = useState(false);

  const action = useMemo(
    () => (checkinView ? pickNextAction({ checkin: checkinView, focus, now: new Date(), skipped }) : null),
    [checkinView, focus, skipped]
  );

  if (!checkinView || !action) {
    return (
      <section className="w-full bg-surface rounded-xl p-5 border border-line">
        {checkinLoading ? (
          <p className="font-small text-muted-text">Loading today…</p>
        ) : (
          <div className="flex items-center justify-between gap-3">
            <p className="font-small text-ink">Couldn’t load today.</p>
            <button
              type="button"
              onClick={() => void refreshCheckinView()}
              className="px-3 h-9 rounded-lg bg-surface-container text-ink font-caption text-caption font-semibold"
            >
              Retry
            </button>
          </div>
        )}
      </section>
    );
  }

  const run = async () => {
    const t = action.target;
    if (t.type === 'checkin') {
      setCheckinModalOpen(true);
      return;
    }
    if (t.type === 'none') return;
    setBusy(true);
    try {
      if (t.type === 'habit') {
        await logHabit(t.habitId, activeDate, t.status);
        bumpData();
        showToast(t.status === 'floor' ? 'Floor logged. That counts.' : 'Logged.');
      } else {
        await completeTask(t.taskId);
        await reloadFocus();
        showToast('Done.');
      }
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not save that'));
    } finally {
      setBusy(false);
    }
  };

  if (action.kind === 'clear') {
    return (
      <section className="w-full bg-surface rounded-xl p-5 border border-line flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="material-symbols-outlined text-[24px] text-domain-study-fill">check_circle</span>
          <div className="min-w-0">
            <h2 className="font-section text-section text-ink">{action.title}</h2>
            <p className="font-small text-small text-muted-text">{action.detail}</p>
          </div>
        </div>
        {checkinView.already_confirmed && (
          <button
            type="button"
            onClick={() => setCheckinModalOpen(true)}
            className="px-3 h-9 shrink-0 rounded-lg bg-surface-container text-ink font-caption text-caption font-semibold"
          >
            Review
          </button>
        )}
      </section>
    );
  }

  return (
    <section className="w-full bg-ink rounded-xl p-5 text-ground-chalk shadow-sm">
      <span className="font-caption text-caption text-surface-dim uppercase tracking-wider">{action.eyebrow}</span>
      <h2 className="font-title text-title text-ground-chalk leading-tight mt-1.5 break-words">{action.title}</h2>
      {action.detail && <p className="font-small text-small text-surface-dim mt-1.5">{action.detail}</p>}
      {action.cta && (
        <div className="mt-5 flex items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => void run()}
            className="flex-1 h-12 bg-ground-chalk text-ink rounded-xl font-body-strong text-body-strong active:bg-surface-dim transition-colors disabled:opacity-60"
          >
            {action.cta}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => setSkipped((prev) => new Set(prev).add(action.key))}
            className="h-12 px-4 rounded-xl text-surface-dim font-caption text-caption font-semibold hover:text-ground-chalk disabled:opacity-60"
          >
            Not now
          </button>
        </div>
      )}
    </section>
  );
};
