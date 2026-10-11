import React, { useEffect, useState } from 'react';
import { useApp } from '../context/AppContext';
import { captureUrge, getStudySessions, getUrges } from '../api/tracking';
import { logHabit } from '../api/habits';
import { HabitStatus, StudySession, UrgeLog } from '../types';
import { formatMinutes, errorMessage } from '../lib/format';
import { toTimeInput } from '../lib/dates';

interface TodayEntriesProps {
  onOpenCheckin?: () => void;
  onOpenUrgeCapture?: () => void;
}

export const TodayEntries: React.FC<TodayEntriesProps> = ({ onOpenCheckin, onOpenUrgeCapture }) => {
  const { showToast, activeDate, checkinView, bumpData, dataEpoch, demoMode } = useApp();
  const [todayUrges, setTodayUrges] = useState<UrgeLog[]>([]);
  const [todayStudy, setTodayStudy] = useState<StudySession[]>([]);
  const [pendingHabit, setPendingHabit] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getUrges(activeDate, 2, true), getStudySessions(activeDate, 2)])
      .then(([urges, sessions]) => {
        if (cancelled) return;
        setTodayUrges(urges.filter((u) => u.log_date === activeDate));
        setTodayStudy(sessions.filter((s) => s.log_date === activeDate));
      })
      .catch(() => {
        if (!cancelled) {
          setTodayUrges([]);
          setTodayStudy([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeDate, dataEpoch, demoMode]);

  const entries = checkinView?.entries.filter((e) => e.is_scheduled !== false) ?? [];
  const sleep = checkinView?.sleep.logged;
  const screen = checkinView?.screen_time.logged;
  const latestUrge = todayUrges[0] ?? null;

  const handleHabitToggle = async (habitId: string, status: HabitStatus) => {
    setPendingHabit(habitId);
    try {
      await logHabit(habitId, activeDate, status);
      bumpData();
      showToast(`Habit updated to ${status}`);
    } catch (err) {
      showToast(errorMessage(err, 'Could not update habit'));
    } finally {
      setPendingHabit(null);
    }
  };

  const handleUrgeAction = async (outcome: 'resisted' | 'relapsed') => {
    try {
      await captureUrge({ outcome });
      bumpData();
      showToast(`Urge recorded as ${outcome}`);
    } catch (err) {
      showToast(errorMessage(err, 'Could not log urge'));
    }
  };

  const studyMinutes = todayStudy.reduce((sum, s) => sum + s.actual_minutes, 0);
  const studyLabel = todayStudy[0]?.subject_name || 'Study';

  return (
    <section className="w-full flex flex-col mb-4">
      <div className="flex items-baseline justify-between mb-2 px-1">
        <h3 className="font-section text-section text-ink">Today's entries</h3>
        <span className="font-caption text-caption text-muted-text">
          {entries.length} habit{entries.length === 1 ? '' : 's'} scheduled
        </span>
      </div>

      <div className="w-full bg-surface rounded-xl overflow-hidden border border-line shadow-sm">
        {entries.length === 0 && (
          <div className="p-3.5 font-caption text-caption text-muted-text">
            No habits scheduled for this date. Add one on Track.
          </div>
        )}

        {entries.map((entry, idx) => (
          <div key={entry.habit_id}>
            {idx > 0 && <div className="w-full h-[1px] bg-surface-container" />}
            <div className="min-h-[58px] p-3.5 flex items-center justify-between gap-3 bg-surface">
              <div className="flex items-center gap-3 min-w-0">
                <svg className="shrink-0" height="14" viewBox="0 0 14 14" width="14">
                  <circle cx="7" cy="7" fill="#C84A21" r="6" />
                </svg>
                <div className="flex flex-col min-w-0">
                  <span className="font-small-medium text-small-medium text-ink truncate">{entry.habit_name}</span>
                  <span className="font-caption text-caption text-muted-text truncate">{entry.reason}</span>
                </div>
              </div>
              <div className="flex items-center bg-surface-container p-0.5 rounded-lg shrink-0">
                {(['done', 'partial', 'skipped'] as HabitStatus[]).map((status) => (
                  <button
                    key={status}
                    type="button"
                    disabled={pendingHabit === entry.habit_id}
                    onClick={() => handleHabitToggle(entry.habit_id, status)}
                    className={`px-2.5 py-1 rounded font-caption text-caption transition-colors ${
                      entry.status === status
                        ? 'bg-ink text-ground-chalk font-semibold'
                        : 'text-ink hover:bg-surface-variant'
                    }`}
                  >
                    {status === 'done' ? 'Done' : status === 'partial' ? 'Part' : 'Miss'}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ))}

        <div className="w-full h-[1px] bg-surface-container" />
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
                {formatMinutes(sleep?.duration_minutes)}
              </span>
              <span className="font-caption text-caption text-muted-text">
                {sleep
                  ? `${toTimeInput(sleep.time_to_bed, '—')} to ${toTimeInput(sleep.time_woke, '—')}`
                  : 'Not logged — tap to check in'}
              </span>
            </div>
          </div>
          <div
            className={`px-2.5 py-1 rounded font-caption text-caption shrink-0 font-medium ${
              sleep ? 'bg-domain-sleep-tint text-domain-sleep-fill' : 'bg-surface-container text-muted-text'
            }`}
          >
            {sleep ? (sleep.is_default ? 'Default' : 'Logged') : 'Open'}
          </div>
        </div>

        <div className="w-full h-[1px] bg-surface-container" />
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
                {formatMinutes(screen?.total_minutes)}
              </span>
              <span className="font-caption text-caption text-muted-text">
                {screen?.is_default ? 'Guess from your usual' : screen ? 'Manual log' : 'Not logged'}
              </span>
            </div>
          </div>
          <div className="px-2.5 py-1 rounded bg-surface-container-low text-ink font-caption text-caption shrink-0 border border-surface-container">
            {screen ? (screen.is_default ? 'Guess' : 'Logged') : 'Open'}
          </div>
        </div>

        <div className="w-full h-[1px] bg-surface-container" />
        <div className="min-h-[58px] p-3.5 flex items-center justify-between gap-3 bg-surface">
          <div onClick={onOpenUrgeCapture} className="flex items-center gap-3 min-w-0 cursor-pointer flex-1">
            <svg className="shrink-0" height="14" viewBox="0 0 14 14" width="14">
              <path d="M 1 7 Q 4 3 7 7 T 13 7" fill="none" stroke="#92405F" strokeLinecap="round" strokeWidth="2" />
            </svg>
            <div className="flex flex-col min-w-0">
              <span className="font-small-medium text-small-medium text-ink truncate">
                {latestUrge ? `Urge ${latestUrge.outcome}` : 'Urge quick-capture'}
              </span>
              <span className="font-caption text-caption text-muted-text truncate">
                {latestUrge?.trigger_context || (todayUrges.length ? `${todayUrges.length} today` : '2-tap log — no form required')}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              type="button"
              onClick={() => handleUrgeAction('resisted')}
              className="h-8 px-3 rounded font-caption text-caption bg-surface-container text-ink hover:bg-secondary-fixed"
            >
              Resisted
            </button>
            <button
              type="button"
              onClick={() => handleUrgeAction('relapsed')}
              className="h-8 px-3 rounded font-caption text-caption bg-surface-container text-ink hover:bg-secondary-fixed"
            >
              Relapsed
            </button>
          </div>
        </div>

        <div className="w-full h-[1px] bg-surface-container" />
        <div
          onClick={onOpenCheckin}
          className="min-h-[58px] p-3.5 flex items-center justify-between gap-3 bg-surface hover:bg-surface-container-low transition-colors cursor-pointer"
        >
          <div className="flex items-center gap-3 min-w-0">
            <svg className="shrink-0" height="14" viewBox="0 0 14 14" width="14">
              <polygon fill="#4F7A2E" points="7,1 13,12 1,12" />
            </svg>
            <div className="flex flex-col min-w-0">
              <span className="font-small-medium text-small-medium text-ink truncate">{studyLabel}</span>
              <span className="font-caption text-caption text-muted-text">
                {todayStudy.length ? `${formatMinutes(studyMinutes)} · log more on Track` : 'No session today — log on Track'}
              </span>
            </div>
          </div>
          <div
            className={`px-2.5 py-1 rounded font-caption text-caption shrink-0 font-medium ${
              todayStudy.length ? 'bg-domain-study-tint text-domain-study-fill' : 'bg-surface-container text-muted-text'
            }`}
          >
            {todayStudy.length ? 'Logged' : 'Empty'}
          </div>
        </div>
      </div>
    </section>
  );
};
