import React, { useState, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import { confirmCheckin } from '../api/checkins';
import { HabitStatus, CheckinOverride } from '../types';

interface CheckinModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const CheckinModal: React.FC<CheckinModalProps> = ({ isOpen, onClose }) => {
  const { checkinView, activeDate, refreshCheckinView, showToast } = useApp();

  const [habitOverrides, setHabitOverrides] = useState<Record<string, HabitStatus>>({});
  const [bedtime, setBedtime] = useState('23:30');
  const [wakeTime, setWakeTime] = useState('06:45');
  const [sleepQuality, setSleepQuality] = useState<number>(4);
  const [screenMinutes, setScreenMinutes] = useState<number>(190);
  const [journalText, setJournalText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [crisisDetected, setCrisisDetected] = useState(false);

  useEffect(() => {
    if (checkinView) {
      if (checkinView.sleep.logged?.time_to_bed) {
        setBedtime(checkinView.sleep.logged.time_to_bed);
      }
      if (checkinView.sleep.logged?.time_woke) {
        setWakeTime(checkinView.sleep.logged.time_woke);
      }
      if (checkinView.sleep.logged?.self_rated_quality) {
        setSleepQuality(checkinView.sleep.logged.self_rated_quality);
      }
      if (checkinView.screen_time.logged?.total_minutes !== undefined) {
        setScreenMinutes(checkinView.screen_time.logged.total_minutes);
      }
    }
  }, [checkinView]);

  // Check crisis keywords in journal per Section 8 of SPEC
  useEffect(() => {
    const lower = journalText.toLowerCase();
    const flags = ['suicide', 'kill myself', 'self-harm', 'end my life', 'want to die'];
    setCrisisDetected(flags.some((kw) => lower.includes(kw)));
  }, [journalText]);

  if (!isOpen) return null;

  const handleHabitToggle = (habitId: string, status: HabitStatus) => {
    setHabitOverrides((prev) => ({
      ...prev,
      [habitId]: status,
    }));
  };

  const handleConfirm = async (acceptDefaults: boolean) => {
    setIsSubmitting(true);
    try {
      const overrides: CheckinOverride[] = Object.entries(habitOverrides).map(([habit_id, status]) => ({
        habit_id,
        status,
      }));

      await confirmCheckin(activeDate, {
        overrides,
        journal_text: journalText.trim() || null,
        sleep: {
          time_to_bed: bedtime,
          time_woke: wakeTime,
          self_rated_quality: sleepQuality,
        },
        screen_time: {
          total_minutes: screenMinutes,
        },
        accept_sleep_default: acceptDefaults,
        accept_screen_time_default: acceptDefaults,
      });

      showToast('Daily check-in locked in!');
      await refreshCheckinView();
      onClose();
    } catch (err: any) {
      showToast(err?.message || 'Check-in saved locally');
      onClose();
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-xs p-0 sm:p-4">
      <div className="w-full max-w-md bg-ground-chalk rounded-t-2xl sm:rounded-2xl max-h-[92vh] flex flex-col overflow-hidden shadow-2xl border border-line animate-slideUp">
        {/* Modal Header */}
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

        {/* Modal Scrollable Body */}
        <div className="p-4 overflow-y-auto space-y-5 flex-1">
          {/* Defaults info banner */}
          <div className="p-3 bg-surface-container rounded-lg flex items-center gap-2.5">
            <span className="material-symbols-outlined text-ink text-[20px]">verified</span>
            <p className="font-small text-small text-ink">
              Defaults seeded from your declared rhythm. Touch only what was different today.
            </p>
          </div>

          {/* Section: Habits */}
          <div className="space-y-2">
            <h3 className="font-small-medium text-small-medium text-ink uppercase tracking-wider">
              Habits Scheduled
            </h3>
            <div className="space-y-2">
              {checkinView?.entries.map((entry) => {
                const currentStatus = habitOverrides[entry.habit_id] || entry.status || 'done';
                return (
                  <div
                    key={entry.habit_id}
                    className="p-3 bg-surface rounded-xl border border-line flex items-center justify-between gap-2"
                  >
                    <div className="min-w-0 flex-1">
                      <span className="font-small-medium text-ink block truncate">{entry.habit_name}</span>
                      <span className="font-caption text-muted-text text-[11px] block">{entry.reason}</span>
                    </div>
                    <div className="flex items-center bg-surface-container p-0.5 rounded-lg shrink-0">
                      <button
                        type="button"
                        onClick={() => handleHabitToggle(entry.habit_id, 'done')}
                        className={`px-2 py-1 rounded text-[11px] font-semibold transition-colors ${
                          currentStatus === 'done' ? 'bg-ink text-ground-chalk' : 'text-ink'
                        }`}
                      >
                        Done
                      </button>
                      <button
                        type="button"
                        onClick={() => handleHabitToggle(entry.habit_id, 'partial')}
                        className={`px-2 py-1 rounded text-[11px] font-semibold transition-colors ${
                          currentStatus === 'partial' ? 'bg-ink text-ground-chalk' : 'text-ink'
                        }`}
                      >
                        Part
                      </button>
                      <button
                        type="button"
                        onClick={() => handleHabitToggle(entry.habit_id, 'skipped')}
                        className={`px-2 py-1 rounded text-[11px] font-semibold transition-colors ${
                          currentStatus === 'skipped' ? 'bg-ink text-ground-chalk' : 'text-ink'
                        }`}
                      >
                        Miss
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Section: Sleep */}
          <div className="space-y-2">
            <h3 className="font-small-medium text-small-medium text-ink uppercase tracking-wider">
              Sleep Rhythm
            </h3>
            <div className="p-3 bg-surface rounded-xl border border-line space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-caption text-caption text-muted-text block mb-1">To bed</label>
                  <input
                    type="time"
                    value={bedtime}
                    onChange={(e) => setBedtime(e.target.value)}
                    className="w-full bg-surface-container-low border border-line rounded-lg px-2.5 py-1.5 font-small text-ink"
                  />
                </div>
                <div>
                  <label className="font-caption text-caption text-muted-text block mb-1">Woke up</label>
                  <input
                    type="time"
                    value={wakeTime}
                    onChange={(e) => setWakeTime(e.target.value)}
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
                  onChange={(e) => setSleepQuality(parseInt(e.target.value, 10))}
                  className="w-full accent-ink"
                />
              </div>
            </div>
          </div>

          {/* Section: Screen Time */}
          <div className="space-y-2">
            <h3 className="font-small-medium text-small-medium text-ink uppercase tracking-wider">
              Screen Time
            </h3>
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
                onChange={(e) => setScreenMinutes(parseInt(e.target.value, 10))}
                className="w-full accent-ink"
              />
            </div>
          </div>

          {/* Section: Encrypted Journal Note */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="font-small-medium text-small-medium text-ink uppercase tracking-wider">
                Journal Note (Encrypted)
              </h3>
              <span className="font-caption text-caption text-muted-text">Zero-knowledge AES</span>
            </div>
            <textarea
              rows={3}
              value={journalText}
              onChange={(e) => setJournalText(e.target.value)}
              placeholder="What triggered friction today? Any wins or bottlenecks..."
              className="w-full bg-surface border border-line rounded-xl p-3 font-small text-ink focus:outline-none focus:ring-1 focus:ring-ink"
            />
          </div>

          {/* Crisis Banner if triggered */}
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
                <div>• National Crisis Lifeline: <strong>Call or Text 988</strong> (24/7)</div>
                <div>• Crisis Text Line: <strong>Text HOME to 741741</strong></div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Actions Footer */}
        <div className="p-4 bg-surface border-t border-surface-container shrink-0 space-y-2">
          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => handleConfirm(true)}
            className="w-full h-12 bg-ink text-ground-chalk rounded-xl font-body-strong text-body-strong flex items-center justify-center gap-2 active:bg-secondary transition-colors"
          >
            <span>{isSubmitting ? 'Locking in...' : 'Confirm Today (Defaults Accepted)'}</span>
            <span className="material-symbols-outlined text-[18px]">check</span>
          </button>
          <button
            type="button"
            onClick={onClose}
            className="w-full py-2 text-center font-caption text-caption text-muted-text hover:text-ink transition-colors"
          >
            Cancel / Edit Later
          </button>
        </div>
      </div>
    </div>
  );
};
