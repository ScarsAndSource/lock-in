import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { captureUrge } from '../api/tracking';
import { logHabit } from '../api/habits';
import { HabitStatus } from '../types';

interface TodayEntriesProps {
  onOpenCheckin?: () => void;
  onOpenUrgeCapture?: () => void;
}

export const TodayEntries: React.FC<TodayEntriesProps> = ({
  onOpenCheckin,
  onOpenUrgeCapture,
}) => {
  const { showToast, activeDate } = useApp();
  const [habitStatus, setHabitStatus] = useState<HabitStatus>('done');
  const [urgeStatus, setUrgeStatus] = useState<'resisted' | 'relapsed' | null>(null);

  const handleHabitToggle = async (status: HabitStatus) => {
    setHabitStatus(status);
    showToast(`Gym status updated to ${status}`);
    try {
      await logHabit('habit-1', activeDate, status);
    } catch {
      // offline/demo fallback already handles
    }
  };

  const handleUrgeAction = async (outcome: 'resisted' | 'relapsed') => {
    setUrgeStatus(outcome);
    showToast(`Urge recorded as ${outcome}`);
    try {
      await captureUrge({
        outcome,
        occurred_at: new Date().toISOString(),
        trigger_context: 'Evening craving - tired after work',
      });
    } catch {
      // fallback handles
    }
  };

  return (
    <section className="w-full flex flex-col mb-4">
      <div className="flex items-baseline justify-between mb-2 px-1">
        <h3 className="font-section text-section text-ink">Today's entries</h3>
        <span className="font-caption text-caption text-muted-text">4 of 5 active</span>
      </div>

      {/* Tabular list on Surface */}
      <div className="w-full bg-surface rounded-xl overflow-hidden border border-line shadow-sm">
        {/* Row 1: Habits */}
        <div className="min-h-[58px] p-3.5 flex items-center justify-between gap-3 bg-surface hover:bg-surface-container-low transition-colors">
          <div className="flex items-center gap-3 min-w-0">
            <svg className="shrink-0" height="14" viewBox="0 0 14 14" width="14">
              <circle cx="7" cy="7" fill="#C84A21" r="6" />
            </svg>
            <div className="flex flex-col min-w-0">
              <span className="font-small-medium text-small-medium text-ink truncate">
                Gym: same as usual.
              </span>
              <span className="font-caption text-caption text-muted-text">
                Upper body push · 45 min
              </span>
            </div>
          </div>

          {/* Habit Status Segmented Control */}
          <div className="flex items-center bg-surface-container p-0.5 rounded-lg shrink-0">
            <button
              type="button"
              onClick={() => handleHabitToggle('done')}
              className={`px-2.5 py-1 rounded font-caption text-caption transition-colors ${
                habitStatus === 'done'
                  ? 'bg-ink text-ground-chalk font-semibold'
                  : 'text-ink hover:bg-surface-variant'
              }`}
            >
              Done
            </button>
            <button
              type="button"
              onClick={() => handleHabitToggle('partial')}
              className={`px-2.5 py-1 rounded font-caption text-caption transition-colors ${
                habitStatus === 'partial'
                  ? 'bg-ink text-ground-chalk font-semibold'
                  : 'text-ink hover:bg-surface-variant'
              }`}
            >
              Part
            </button>
            <button
              type="button"
              onClick={() => handleHabitToggle('skipped')}
              className={`px-2.5 py-1 rounded font-caption text-caption transition-colors ${
                habitStatus === 'skipped'
                  ? 'bg-ink text-ground-chalk font-semibold'
                  : 'text-ink hover:bg-surface-variant'
              }`}
            >
              Miss
            </button>
          </div>
        </div>

        {/* Divider */}
        <div className="w-full h-[1px] bg-surface-container" />

        {/* Row 2: Sleep */}
        <div
          onClick={onOpenCheckin}
          className="min-h-[58px] p-3.5 flex items-center justify-between gap-3 bg-surface hover:bg-surface-container-low transition-colors cursor-pointer"
        >
          <div className="flex items-center gap-3 min-w-0">
            <svg className="shrink-0" height="14" viewBox="0 0 14 14" width="14">
              <path d="M 7 1 A 6 6 0 0 1 7 13 Z" fill="#1D5F73" />
            </svg>
            <div className="flex flex-col min-w-0">
              <span className="font-small-medium text-small-medium text-ink truncate">
                7 hr 15 min
              </span>
              <span className="font-caption text-caption text-muted-text">
                11:30 pm to 6:45 am
              </span>
            </div>
          </div>
          <div className="px-2.5 py-1 rounded bg-domain-sleep-tint text-domain-sleep-fill font-caption text-caption shrink-0 font-medium">
            Logged
          </div>
        </div>

        {/* Divider */}
        <div className="w-full h-[1px] bg-surface-container" />

        {/* Row 3: Screen */}
        <div
          onClick={onOpenCheckin}
          className="min-h-[58px] p-3.5 flex items-center justify-between gap-3 bg-surface hover:bg-surface-container-low transition-colors cursor-pointer"
        >
          <div className="flex items-center gap-3 min-w-0">
            <svg className="shrink-0" height="14" viewBox="0 0 14 14" width="14">
              <rect fill="#E0A21B" height="12" rx="2.5" width="10" x="2" y="1" />
            </svg>
            <div className="flex flex-col min-w-0">
              <span className="font-small-medium text-small-medium text-ink truncate">
                3 hr 10 min
              </span>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="w-8 h-1.5 rounded-sm bg-domain-screen-fill" />
                <span className="font-caption text-caption text-muted-text">Within limit</span>
              </div>
            </div>
          </div>
          <div className="px-2.5 py-1 rounded bg-surface-container-low text-ink font-caption text-caption shrink-0 flex items-center gap-1 border border-surface-container">
            <span className="w-1.5 h-1.5 rounded-full bg-domain-screen-fill" />
            <span>Guess</span>
          </div>
        </div>

        {/* Divider */}
        <div className="w-full h-[1px] bg-surface-container" />

        {/* Row 4: Urges */}
        <div className="min-h-[58px] p-3.5 flex items-center justify-between gap-3 bg-surface hover:bg-surface-container-low transition-colors">
          <div
            onClick={onOpenUrgeCapture}
            className="flex items-center gap-3 min-w-0 cursor-pointer flex-1"
          >
            <svg className="shrink-0" height="14" viewBox="0 0 14 14" width="14">
              <path d="M 1 7 Q 4 3 7 7 T 13 7" fill="none" stroke="#92405F" strokeLinecap="round" strokeWidth="2" />
            </svg>
            <div className="flex flex-col min-w-0">
              <span className="font-small-medium text-small-medium text-ink truncate">
                Evening craving
              </span>
              <span className="font-caption text-caption text-muted-text">
                Trigger: tired after work
              </span>
            </div>
          </div>

          {/* Dual Outline Buttons (ink styled) */}
          <div className="flex items-center gap-1.5 shrink-0" id="urge-actions">
            <button
              type="button"
              onClick={() => handleUrgeAction('resisted')}
              className={`h-8 px-3 rounded font-caption text-caption transition-colors ${
                urgeStatus === 'resisted'
                  ? 'bg-ink text-ground-chalk font-semibold'
                  : 'bg-surface-container text-ink hover:bg-secondary-fixed'
              }`}
            >
              Resisted
            </button>
            <button
              type="button"
              onClick={() => handleUrgeAction('relapsed')}
              className={`h-8 px-3 rounded font-caption text-caption transition-colors ${
                urgeStatus === 'relapsed'
                  ? 'bg-ink text-ground-chalk font-semibold'
                  : 'bg-surface-container text-ink hover:bg-secondary-fixed'
              }`}
            >
              Relapsed
            </button>
          </div>
        </div>

        {/* Divider */}
        <div className="w-full h-[1px] bg-surface-container" />

        {/* Row 5: Study */}
        <div
          onClick={onOpenCheckin}
          className="min-h-[58px] p-3.5 flex items-center justify-between gap-3 bg-surface hover:bg-surface-container-low transition-colors cursor-pointer"
        >
          <div className="flex items-center gap-3 min-w-0">
            <svg className="shrink-0" height="14" viewBox="0 0 14 14" width="14">
              <polygon fill="#4F7A2E" points="7,1 13,12 1,12" />
            </svg>
            <div className="flex flex-col min-w-0">
              <span className="font-small-medium text-small-medium text-ink truncate">
                Algorithms & Systems
              </span>
              <span className="font-caption text-caption text-muted-text">
                85 min · Follow-through 94%
              </span>
            </div>
          </div>
          <div className="px-2.5 py-1 rounded bg-domain-study-tint text-domain-study-fill font-caption text-caption shrink-0 font-medium">
            Logged
          </div>
        </div>
      </div>
    </section>
  );
};
