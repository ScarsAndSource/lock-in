import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useApp } from '../context/AppContext';
import { logHabit } from '../api/habits';
import { completeTask } from '../api/tasks';
import { fromServer, postCompanionEvent } from '../api/companion';
import type { CompanionNow } from '../api/companion';
import { pickNextAction } from '../lib/nextAction';
import { errorMessage } from '../lib/format';
import type { TaskFocus } from '../types';

interface NextCardProps {
  companion: CompanionNow | null;
  focus: TaskFocus | null;
  skipped: ReadonlySet<string>;
  onSkip: (key: string) => void;
  reloadAll: () => Promise<void>;
}

/**
 * The one thing to do now. The companion (server) chooses it from the person's own rhythm; if it can't be reached the
 * same card is chosen on-device, so the screen never goes blank. "Not now" hides it for this session.
 */
export const NextCard: React.FC<NextCardProps> = ({ companion, focus, skipped, onSkip, reloadAll }) => {
  const {
    checkinView, checkinLoading, refreshCheckinView, activeDate, bumpData, showToast, setCheckinModalOpen,
    setUrgeQuickModalOpen,
  } = useApp();
  const [busy, setBusy] = useState(false);
  const [whyOpen, setWhyOpen] = useState(false);
  const shown = useRef<Set<string>>(new Set());

  const action = useMemo(() => {
    if (companion) return fromServer(companion.next_action);
    return checkinView ? pickNextAction({ checkin: checkinView, focus, now: new Date(), skipped }) : null;
  }, [companion, checkinView, focus, skipped]);

  const key = action?.key ?? null;
  const kind = action?.kind ?? null;
  useEffect(() => {
    setWhyOpen(false);
    if (!key || kind === 'clear' || shown.current.has(key)) return;
    shown.current.add(key);
    postCompanionEvent('nba_shown', key);
  }, [key, kind]);

  const confirmed = companion?.confirmed ?? checkinView?.already_confirmed ?? false;

  if (!action) {
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
    if (t.type === 'urge') {
      setUrgeQuickModalOpen(true);
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
        await reloadAll();
        showToast('Done.');
      }
      postCompanionEvent('nba_acted', action.key);
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not save that'));
    } finally {
      setBusy(false);
    }
  };

  const skip = () => {
    postCompanionEvent('nba_skipped', action.key);
    onSkip(action.key);
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
        {confirmed && (
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
      {action.voice && (
        <p className="font-small text-small text-ground-chalk mt-3 pl-3 border-l-2 border-domain-screen-fill">
          {action.voice}
        </p>
      )}
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
            onClick={skip}
            className="h-12 px-4 rounded-xl text-surface-dim font-caption text-caption font-semibold hover:text-ground-chalk disabled:opacity-60"
          >
            Not now
          </button>
        </div>
      )}
      {action.why && (
        <div className="mt-3">
          <button
            type="button"
            aria-expanded={whyOpen}
            onClick={() => setWhyOpen((v) => !v)}
            className="font-caption text-caption text-surface-dim underline underline-offset-2 hover:text-ground-chalk"
          >
            Why this?
          </button>
          {whyOpen && <p className="font-caption text-caption text-surface-dim mt-1.5 animate-fadeIn">{action.why}</p>}
        </div>
      )}
    </section>
  );
};
