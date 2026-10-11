import React, { useState, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import { confirmCheckin, getJournal } from '../api/checkins';
import { HabitStatus, CheckinOverride } from '../types';
import { toTimeInput } from '../lib/dates';
import { errorMessage } from '../lib/format';

interface CheckinModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const CRISIS_FLAGS = ['suicide', 'kill myself', 'self-harm', 'end my life', 'want to die'];

export const CheckinModal: React.FC<CheckinModalProps> = ({ isOpen, onClose }) => {
  const { checkinView, activeDate, refreshCheckinView, bumpData, showToast } = useApp();

  const [habitOverrides, setHabitOverrides] = useState<Record<string, HabitStatus>>({});
  const [bedtime, setBedtime] = useState('23:30');
  const [wakeTime, setWakeTime] = useState('06:45');
  const [sleepQuality, setSleepQuality] = useState(4);
  const [screenMinutes, setScreenMinutes] = useState(120);
  const [journalText, setJournalText] = useState('');
  const [sleepDirty, setSleepDirty] = useState(false);
  const [screenDirty, setScreenDirty] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [crisisDetected, setCrisisDetected] = useState(false);

  useEffect(() => {
    if (!isOpen || !checkinView) return;
    const sleep = checkinView.sleep.logged || checkinView.sleep.proposal;
    const screen = checkinView.screen_time.logged || checkinView.screen_time.proposal;
    setHabitOverrides({});
    setSleepDirty(false);
    setScreenDirty(false);
    setBedtime(toTimeInput(sleep?.time_to_bed, '23:30'));
    setWakeTime(toTimeInput(sleep?.time_woke, '06:45'));
    setSleepQuality(sleep?.self_rated_quality ?? 4);
    setScreenMinutes(screen?.total_minutes ?? 120);
    setJournalText('');
    if (checkinView.already_confirmed) {
      getJournal(activeDate)
        .then((j) => setJournalText(j.journal_text || ''))
        .catch(() => {});
    }
  }, [isOpen, checkinView, activeDate]);

  useEffect(() => {
    const lower = journalText.toLowerCase();
    setCrisisDetected(CRISIS_FLAGS.some((kw) => lower.includes(kw)));
  }, [journalText]);

  if (!isOpen) return null;

  const handleConfirm = async () => {
    setIsSubmitting(true);
    try {
      const overrides: CheckinOverride[] = Object.entries(habitOverrides).map(([habit_id, status]) => ({
        habit_id,
        status,
      }));

      const result = await confirmCheckin(activeDate, {
        overrides,
        journal_text: journalText.trim() ? journalText.trim() : checkinView?.already_confirmed ? journalText : null,
        sleep: sleepDirty
          ? {
              time_to_bed: bedtime || null,
              time_woke: wakeTime || null,
              self_rated_quality: sleepQuality,
            }
          : null,
        screen_time: screenDirty ? { total_minutes: screenMinutes, source: 'manual' } : null,
        accept_sleep_default: !sleepDirty,
        accept_screen_time_default: !screenDirty,
      });

      if (result.support) {
        showToast('Check-in saved. Support resources are on screen.');
      } else {
        showToast(checkinView?.already_confirmed ? 'Check-in updated' : 'Daily check-in locked in');
      }
      bumpData();
      await refreshCheckinView();
      onClose();
    } catch (err) {
      showToast(errorMessage(err, 'Could not save check-in'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-xs p-0 sm:p-4">
      <div className="w-full max-w-md bg-ground-chalk rounded-t-2xl sm:rounded-2xl max-h-[92vh] flex flex-col overflow-hidden shadow-2xl border border-line animate-slideUp">
        <div className="p-4 bg-surface border-b border-surface-container flex items-center justify-between shrink-0">
          <div>
            <span className="font-caption text-caption text-muted-text uppercase tracking-wider block">
              Opt-Out Daily Check-in
            </span>
            <h2 className="font-title text-title text-ink text-xl">Today's Protocol</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center text-ink hover:bg-secondary-fixed transition-colors"
          >
            <span className="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>

        <div className="p-4 overflow-y-auto space-y-5 flex-1">
          <div className="p-3 bg-surface-container rounded-lg flex items-center gap-2.5">
            <span className="material-symbols-outlined text-ink text-[20px]">verified</span>
            <p className="font-small text-small text-ink">
              Defaults seeded from your declared rhythm. Touch only what was different today.
            </p>
          </div>

          <div className="space-y-2">
            <h3 className="font-small-medium text-small-medium text-ink uppercase tracking-wider">Habits Scheduled</h3>
            <div className="space-y-2">
              {(checkinView?.entries || []).map((entry) => {
                const currentStatus = habitOverrides[entry.habit_id] ?? entry.status;
                return (
                  <div
                    key={entry.habit_id}
                    className="p-3 bg-surface rounded-xl border border-line flex items-center justify-between gap-2"
                  >
                    <div className="min-w-0 flex-1">
                      <span className="font-small-medium text-ink block truncate">{entry.habit_name}</span>
                      <span className="font-caption text-muted-text text-[11px] block">{entry.reason}</span>
                    </div>
                    {entry.is_scheduled === false && currentStatus === null ? (
                      <span className="font-caption text-caption text-muted-text">Rest day</span>
                    ) : (
                      <div className="flex items-center bg-surface-container p-0.5 rounded-lg shrink-0">
                        {(['done', 'partial', 'skipped'] as HabitStatus[]).map((status) => (
                          <button
                            key={status}
                            type="button"
                            onClick={() => setHabitOverrides((prev) => ({ ...prev, [entry.habit_id]: status }))}
                            className={`px-2 py-1 rounded text-[11px] font-semibold transition-colors ${
                              currentStatus === status ? 'bg-ink text-ground-chalk' : 'text-ink'
                            }`}
                          >
                            {status === 'done' ? 'Done' : status === 'partial' ? 'Part' : 'Miss'}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="space-y-2">
            <h3 className="font-small-medium text-small-medium text-ink uppercase tracking-wider">Sleep Rhythm</h3>
            <div className="p-3 bg-surface rounded-xl border border-line space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-caption text-caption text-muted-text block mb-1">To bed</label>
                  <input
                    type="time"
                    value={bedtime}
                    onChange={(e) => {
                      setBedtime(e.target.value);
                      setSleepDirty(true);
                    }}
                    className="w-full bg-surface-container-low border border-line rounded-lg px-2.5 py-1.5 font-small text-ink"
                  />
                </div>
                <div>
                  <label className="font-caption text-caption text-muted-text block mb-1">Woke up</label>
                  <input
                    type="time"
                    value={wakeTime}
                    onChange={(e) => {
                      setWakeTime(e.target.value);
                      setSleepDirty(true);
                    }}
                    className="w-full bg-surface-container-low border border-line rounded-lg px-2.5 py-1.5 font-small text-ink"
                  />
                </div>
              </div>
              <div>
                <label className="font-caption text-caption text-muted-text block mb-1">
                  Quality (1 = groggy, 5 = refreshed): <strong className="text-ink">{sleepQuality}/5</strong>
                </label>
                <input
                  type="range"
                  min="1"
                  max="5"
                  value={sleepQuality}
                  onChange={(e) => {
                    setSleepQuality(parseInt(e.target.value, 10));
                    setSleepDirty(true);
                  }}
                  className="w-full accent-ink"
                />
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <h3 className="font-small-medium text-small-medium text-ink uppercase tracking-wider">Screen Time</h3>
            <div className="p-3 bg-surface rounded-xl border border-line space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-small text-ink">Total minutes</span>
                <span className="font-small-medium text-ink font-semibold">
                  {Math.floor(screenMinutes / 60)}h {screenMinutes % 60}m ({screenMinutes} min)
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="600"
                step="15"
                value={screenMinutes}
                onChange={(e) => {
                  setScreenMinutes(parseInt(e.target.value, 10));
                  setScreenDirty(true);
                }}
                className="w-full accent-ink"
              />
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="font-small-medium text-small-medium text-ink uppercase tracking-wider">
                Journal Note (Encrypted)
              </h3>
            </div>
            <textarea
              rows={3}
              value={journalText}
              onChange={(e) => setJournalText(e.target.value)}
              placeholder="What triggered friction today? Any wins or bottlenecks..."
              className="w-full bg-surface border border-line rounded-xl p-3 font-small text-ink focus:outline-none focus:ring-1 focus:ring-ink"
            />
          </div>

          {crisisDetected && (
            <div className="p-4 bg-error-container text-on-error-container rounded-xl border border-error space-y-2">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[20px]">warning</span>
                <span className="font-body-strong font-bold">Immediate Support Resources</span>
              </div>
              <p className="font-small text-small">
                If you are going through a crisis, please reach out to real support right now:
              </p>
              <div className="space-y-1 font-small-medium">
                <div>
                  • National Crisis Lifeline: <strong>Call or Text 988</strong> (24/7)
                </div>
                <div>
                  • Crisis Text Line: <strong>Text HOME to 741741</strong>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="p-4 bg-surface border-t border-surface-container shrink-0 space-y-2">
          <button
            type="button"
            disabled={isSubmitting}
            onClick={handleConfirm}
            className="w-full h-12 bg-ink text-ground-chalk rounded-xl font-body-strong text-body-strong flex items-center justify-center gap-2 active:bg-secondary transition-colors disabled:opacity-50"
          >
            <span>
              {isSubmitting
                ? 'Locking in...'
                : sleepDirty || screenDirty || Object.keys(habitOverrides).length
                  ? 'Confirm today (edits applied)'
                  : 'Confirm today (defaults accepted)'}
            </span>
            <span className="material-symbols-outlined text-[18px]">check</span>
          </button>
          <button
            type="button"
            onClick={onClose}
            className="w-full py-2 text-center font-caption text-caption text-muted-text hover:text-ink transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};
