import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { logHabit } from '../api/habits';
import { BounceCard } from './BounceCard';
import type { CheckinEntry, HabitStatus } from '../types';
import { errorMessage, habitStatusLabel, habitTierOptions, tierHint } from '../lib/format';

/** A proposal ("usual") is a guess until the check-in is confirmed or the person logs it themselves. */
function isLogged(e: CheckinEntry, confirmed: boolean): boolean {
  return e.status !== null && (!e.is_default || confirmed);
}

const Circle: React.FC<{ entry: CheckinEntry; confirmed: boolean }> = ({ entry, confirmed }) => {
  const base = 'w-6 h-6 rounded-full flex items-center justify-center border-2 transition-colors';
  if (!isLogged(entry, confirmed)) {
    return entry.status !== null ? (
      <span className={`${base} border-dashed border-outline`}>
        <span className="material-symbols-outlined text-[16px] text-outline">check</span>
      </span>
    ) : (
      <span className={`${base} border-ink`} />
    );
  }
  if (entry.status === 'skipped') {
    return (
      <span className={`${base} border-outline bg-surface-container`}>
        <span className="material-symbols-outlined text-[14px] text-muted-text">close</span>
      </span>
    );
  }
  if (entry.status === 'floor' || entry.status === 'partial') {
    return (
      <span className={`${base} border-ink bg-surface-container`}>
        <span className="material-symbols-outlined text-[14px] text-ink">check</span>
      </span>
    );
  }
  return (
    <span className={`${base} border-ink bg-ink`}>
      <span className="material-symbols-outlined text-[16px] text-ground-chalk">
        {entry.status === 'stretch' ? 'bolt' : 'check'}
      </span>
    </span>
  );
};

/** Habit rows for today. Tap the circle = done. The ⋯ opens the four tiers (stretch / done / floor / miss). */
export const HabitChecklist: React.FC = () => {
  const { checkinView, activeDate, bumpData, showToast, openDomain } = useApp();
  const [openId, setOpenId] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);

  if (!checkinView) return null;
  const confirmed = checkinView.already_confirmed;
  const entries = checkinView.entries.filter((e) => e.is_scheduled !== false);

  const setStatus = async (entry: CheckinEntry, status: HabitStatus) => {
    setPending(entry.habit_id);
    try {
      await logHabit(entry.habit_id, activeDate, status);
      setOpenId(null);
      bumpData();
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not update habit'));
    } finally {
      setPending(null);
    }
  };

  if (entries.length === 0) {
    return (
      <div className="flex items-center justify-between gap-3">
        <p className="font-small text-muted-text">No habits scheduled today.</p>
        <button
          type="button"
          onClick={() => openDomain('habits')}
          className="px-3 h-9 rounded-lg bg-surface-container text-ink font-caption text-caption font-semibold"
        >
          Add habit
        </button>
      </div>
    );
  }

  const doneCount = entries.filter((e) => isLogged(e, confirmed) && e.status !== 'skipped').length;

  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <span className="font-caption text-caption text-muted-text uppercase tracking-wider">Habits</span>
        <span className="font-caption text-caption text-muted-text">
          {doneCount}/{entries.length}
        </span>
      </div>
      <BounceCard bounce={checkinView.bounce} className="mb-2" />
      <div className="divide-y divide-line">
        {entries.map((entry) => {
          const logged = isLogged(entry, confirmed);
          const solidDone = logged && (entry.status === 'done' || entry.status === 'stretch');
          const open = openId === entry.habit_id;
          const hint = tierHint(entry.floor_text, entry.stretch_text);
          let sub: string | null = null;
          if (logged && entry.status && entry.status !== 'done') sub = habitStatusLabel(entry.status);
          else if (!logged && entry.status !== null) sub = 'Usual. Tap to confirm.';
          else if (!logged) sub = hint;
          return (
            <div key={entry.habit_id} className="py-2">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  disabled={pending === entry.habit_id}
                  aria-label={solidDone ? `Change ${entry.habit_name}` : `Mark ${entry.habit_name} done`}
                  onClick={() => (solidDone ? setOpenId(open ? null : entry.habit_id) : void setStatus(entry, 'done'))}
                  className="shrink-0 min-w-[44px] min-h-[44px] -m-2.5 p-2.5 flex items-center justify-center"
                >
                  <Circle entry={entry} confirmed={confirmed} />
                </button>
                <div className="flex-1 min-w-0 ml-1">
                  <p className="font-small-medium text-small-medium text-ink truncate">{entry.habit_name}</p>
                  {sub && <p className="font-caption text-caption text-muted-text truncate">{sub}</p>}
                </div>
                <button
                  type="button"
                  aria-label={`More options for ${entry.habit_name}`}
                  aria-expanded={open}
                  onClick={() => setOpenId(open ? null : entry.habit_id)}
                  className="w-9 h-9 rounded-lg flex items-center justify-center text-muted-text hover:bg-surface-container"
                >
                  <span className="material-symbols-outlined text-[20px]">more_horiz</span>
                </button>
              </div>
              {open && (
                <div className="pl-9 pt-2 space-y-1.5">
                  <div className="flex flex-wrap gap-1.5">
                    {habitTierOptions(entry.status).map((s) => (
                      <button
                        key={s}
                        type="button"
                        disabled={pending === entry.habit_id}
                        onClick={() => void setStatus(entry, s)}
                        className={`px-3 h-8 rounded-lg font-caption text-caption transition-colors ${
                          logged && entry.status === s
                            ? 'bg-ink text-ground-chalk font-semibold'
                            : 'bg-surface-container text-ink hover:bg-secondary-fixed'
                        }`}
                      >
                        {habitStatusLabel(s)}
                      </button>
                    ))}
                  </div>
                  {hint && <p className="font-caption text-caption text-muted-text">{hint}</p>}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
