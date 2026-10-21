import React, { useEffect, useState } from 'react';
import { useApp } from '../context/AppContext';
import { getSleepInference, SleepInferenceDto } from '../api/inference';
import { logSleep } from '../api/tracking';

const dismissKey = (day: string) => `lockin.inference.dismissed.${day}`;

const wasDismissed = (day: string): boolean => {
  try {
    return window.localStorage.getItem(dismissKey(day)) === '1';
  } catch {
    return false;
  }
};

const BASIS_TEXT: Record<string, string> = {
  logged_bed: 'your bedtime',
  logged_wake: 'your wake time',
  last_open: 'when you last used the app',
  first_open: 'when you first opened it',
  rhythm_bed: 'your usual bedtime',
  rhythm_wake: 'your usual wake time',
};

/**
 * "Slept ~6.5h, right?" One tap logs the guess as real; "Edit" opens the sleep sheet; the X hides it for today.
 * Renders nothing when there is nothing worth asking, so it costs no space on a normal day.
 */
export const InferenceChip: React.FC = () => {
  const { activeDate, dataEpoch, demoMode, bumpData, openDomain, showToast } = useApp();
  const [item, setItem] = useState<SleepInferenceDto | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (demoMode || wasDismissed(activeDate)) {
      setItem(null);
      return;
    }
    getSleepInference(activeDate).then((r) => {
      if (!cancelled) setItem(r);
    });
    return () => {
      cancelled = true;
    };
  }, [activeDate, dataEpoch, demoMode]);

  if (!item) return null;

  const confirm = async () => {
    setBusy(true);
    try {
      await logSleep({ log_date: item.day, time_to_bed: item.time_to_bed, time_woke: item.time_woke });
      setItem(null);
      bumpData();
      showToast('Sleep logged');
    } catch {
      showToast('Could not save that. Try again?');
    } finally {
      setBusy(false);
    }
  };

  const dismiss = () => {
    try {
      window.localStorage.setItem(dismissKey(item.day), '1');
    } catch {
      /* private mode: it just comes back next load */
    }
    setItem(null);
  };

  const why = item.basis.map((b) => BASIS_TEXT[b]).filter(Boolean).join(' and ');

  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-surface border border-line rounded-xl" role="group" aria-label="Sleep guess">
      <span className="w-2 h-2 rounded-full bg-domain-sleep-fill shrink-0" />
      <span className="flex-1 min-w-0">
        <span className="font-small-medium text-small-medium text-ink block truncate">Slept {item.prompt}</span>
        {why && <span className="font-caption text-caption text-muted-text block truncate">From {why}</span>}
      </span>
      <button
        type="button"
        disabled={busy}
        onClick={confirm}
        className="min-h-[44px] px-3 rounded-lg bg-ink text-ground-chalk font-small-medium text-small-medium disabled:opacity-50"
      >
        Yes
      </button>
      <button
        type="button"
        onClick={() => openDomain('sleep')}
        className="min-h-[44px] px-3 rounded-lg border border-line text-ink font-small-medium text-small-medium"
      >
        Edit
      </button>
      <button type="button" onClick={dismiss} aria-label="Hide for today" className="min-h-[44px] min-w-[44px] text-muted-text">
        ×
      </button>
    </div>
  );
};
