import React, { useEffect, useState } from 'react';
import { useApp } from '../context/AppContext';
import { confirmCheckin, getJournal } from '../api/checkins';
import { fetchSupport } from '../api/support';
import { Sheet } from './Sheet';
import { Disclosure } from './Disclosure';
import { SupportCard } from './SupportCard';
import { BounceCard } from './BounceCard';
import { MoodPicker } from './MoodPicker';
import type { HabitStatus, CheckinOverride, SupportPayload } from '../types';
import { toTimeInput } from '../lib/dates';
import { errorMessage, formatMinutes, habitStatusLabel, habitTierOptions, tierHint } from '../lib/format';

interface CheckinModalProps {
  isOpen: boolean;
  onClose: () => void;
}

// A quick heads-up while typing. The backend's check on save is the real one (it is broader, and also covers
// Roman-script Hindi and spelling tricks), and its response is what finally decides what the user is shown.
const CRISIS_FLAGS = [
  'suicid',
  'kill myself',
  'killing myself',
  'self-harm',
  'self harm',
  'selfharm',
  'hurt myself',
  'end my life',
  'take my life',
  'want to die',
  'wanna die',
  'dont want to live',
  'do not want to live',
  'better off dead',
  'no reason to live',
  'khudkushi',
  'marna chahta',
  'marna chahti',
  'jeene ka mann nahi',
];

const normalizeForCrisis = (text: string): string => text.toLowerCase().replace(/[\u2019'`]/g, '');

/** Minutes asleep from two "HH:MM" clock values, wrapping past midnight. Null when either is missing. */
function sleepMinutes(bed: string, wake: string): number | null {
  const [bh, bm] = bed.split(':').map(Number);
  const [wh, wm] = wake.split(':').map(Number);
  if (![bh, bm, wh, wm].every(Number.isFinite)) return null;
  const diff = (wh * 60 + wm - (bh * 60 + bm) + 1440) % 1440;
  return diff;
}

export const CheckinModal: React.FC<CheckinModalProps> = ({ isOpen, onClose }) => {
  const { checkinView, activeDate, refreshCheckinView, bumpData, showToast, profile } = useApp();

  const [habitOverrides, setHabitOverrides] = useState<Record<string, HabitStatus>>({});
  const [bedtime, setBedtime] = useState('23:30');
  const [wakeTime, setWakeTime] = useState('06:45');
  const [sleepQuality, setSleepQuality] = useState(4);
  const [screenMinutes, setScreenMinutes] = useState(120);
  const [journalText, setJournalText] = useState('');
  const [sleepDirty, setSleepDirty] = useState(false);
  const [screenDirty, setScreenDirty] = useState(false);
  const [mood, setMood] = useState<{ valence: number | null; energy: number | null }>({ valence: null, energy: null });
  const [moodDirty, setMoodDirty] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [crisisDetected, setCrisisDetected] = useState(false);
  const [bannerSupport, setBannerSupport] = useState<SupportPayload | null>(null);
  const [savedSupport, setSavedSupport] = useState<SupportPayload | null>(null);

  useEffect(() => {
    if (!isOpen || !checkinView) return;
    const sleep = checkinView.sleep.logged || checkinView.sleep.proposal;
    const screen = checkinView.screen_time.logged || checkinView.screen_time.proposal;
    setHabitOverrides({});
    setSleepDirty(false);
    setScreenDirty(false);
    setMood({ valence: checkinView.mood?.valence ?? null, energy: checkinView.mood?.energy ?? null });
    setMoodDirty(false);
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
    const lower = normalizeForCrisis(journalText);
    setCrisisDetected(CRISIS_FLAGS.some((kw) => lower.includes(normalizeForCrisis(kw))));
  }, [journalText]);

  // Region-aware resources from the backend (India gets Tele-MANAS / KIRAN / 112), never hard-coded numbers.
  useEffect(() => {
    if (!crisisDetected || bannerSupport) return;
    let cancelled = false;
    fetchSupport(profile?.timezone)
      .then((payload) => {
        if (!cancelled) setBannerSupport(payload);
      })
      .catch(() => {
        if (!cancelled) {
          setBannerSupport({
            region: 'GLOBAL',
            message: 'If you might act on these thoughts soon, call your local emergency number right now.',
            resources: [
              { name: 'Find a helpline', contact: 'findahelpline.com', detail: 'Helplines listed by country.' },
            ],
            verified_on: '',
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [crisisDetected, bannerSupport, profile?.timezone]);

  // A fresh open starts clean; closing drops the saved-with-support view.
  useEffect(() => {
    if (!isOpen) setSavedSupport(null);
  }, [isOpen]);

  if (!isOpen) return null;

  const confirmed = checkinView?.already_confirmed ?? false;
  const entries = checkinView?.entries || [];
  const scheduledCount = entries.filter((e) => e.is_scheduled !== false).length;
  const editedHabits = Object.keys(habitOverrides).length;
  const anyEdit = sleepDirty || screenDirty || editedHabits > 0;

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
        // Only sent once both rows are tapped; null leaves any saved mood untouched.
        mood: moodDirty && mood.valence !== null && mood.energy !== null ? { valence: mood.valence, energy: mood.energy } : null,
        accept_sleep_default: !sleepDirty,
        accept_screen_time_default: !screenDirty,
      });

      showToast(confirmed ? 'Check-in updated' : 'Locked in');
      bumpData();
      await refreshCheckinView();
      if (result.support) {
        // Keep the sheet open on the resources: closing here would hide exactly what the user needs to see.
        setSavedSupport(result.support);
      } else {
        onClose();
      }
    } catch (err) {
      showToast(errorMessage(err, 'Could not save check-in'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const sleepLogged = checkinView?.sleep.logged ?? null;
  const sleepMin = sleepDirty ? sleepMinutes(bedtime, wakeTime) : sleepLogged?.duration_minutes ?? sleepMinutes(bedtime, wakeTime);
  const sleepSummary = `${formatMinutes(sleepMin)}${!sleepDirty && (sleepLogged?.is_default ?? true) ? ' · usual' : ''}`;
  const screenLogged = checkinView?.screen_time.logged ?? null;
  const screenSummary = `${formatMinutes(screenMinutes)}${!screenDirty && (screenLogged?.is_default ?? true) ? ' · usual' : ''}`;
  const habitSummary = editedHabits > 0 ? `${editedHabits} changed` : `${scheduledCount} as usual`;
  const moodSummary = mood.valence !== null && mood.energy !== null ? `Felt ${mood.valence}/5 · energy ${mood.energy}/5` : 'Optional';

  const field = 'w-full bg-surface-container-low border border-line rounded-lg px-2.5 py-1.5 font-small text-ink';

  if (savedSupport) {
    return (
      <Sheet
        open={isOpen}
        onClose={onClose}
        title="Saved"
        footer={
          <button
            type="button"
            onClick={onClose}
            className="w-full h-12 bg-ink text-ground-chalk rounded-xl font-body-strong text-body-strong active:bg-secondary transition-colors"
          >
            Done
          </button>
        }
      >
        <div className="space-y-4">
          <div className="p-3 bg-surface-container rounded-lg flex items-center gap-2.5">
            <span className="material-symbols-outlined text-ink text-[20px]">check_circle</span>
            <p className="font-small text-small text-ink">Your check-in is saved.</p>
          </div>
          <SupportCard support={savedSupport} />
        </div>
      </Sheet>
    );
  }

  return (
    <Sheet
      open={isOpen}
      onClose={onClose}
      title={confirmed ? 'Today’s check-in' : 'Close today'}
      eyebrow="Defaults cover the usual"
      footer={
        <div className="space-y-2">
          <button
            type="button"
            disabled={isSubmitting || !checkinView}
            onClick={() => void handleConfirm()}
            className="w-full h-12 bg-ink text-ground-chalk rounded-xl font-body-strong text-body-strong flex items-center justify-center gap-2 active:bg-secondary transition-colors disabled:opacity-50"
          >
            <span>
              {isSubmitting ? 'Saving…' : confirmed ? 'Update check-in' : anyEdit ? 'Lock it in with my changes' : 'Lock it in'}
            </span>
            <span className="material-symbols-outlined text-[18px]">check</span>
          </button>
          <button
            type="button"
            onClick={onClose}
            className="w-full py-1.5 text-center font-caption text-caption text-muted-text hover:text-ink transition-colors"
          >
            Cancel
          </button>
        </div>
      }
    >
      {!checkinView ? (
        <p className="font-small text-muted-text">Loading today…</p>
      ) : (
        <div className="space-y-3">
          <BounceCard bounce={checkinView.bounce} />
          <p className="font-small text-small text-muted-text">Change only what was different today.</p>

          <Disclosure title="Habits" summary={habitSummary}>
            <div className="space-y-2 pt-2">
              {entries.length === 0 && <p className="font-small text-muted-text">No habits scheduled today.</p>}
              {entries.map((entry) => {
                const currentStatus = habitOverrides[entry.habit_id] ?? entry.status;
                const hint = tierHint(entry.floor_text, entry.stretch_text);
                return (
                  <div key={entry.habit_id} className="p-3 bg-surface-container-low rounded-xl space-y-2">
                    <div className="min-w-0">
                      <span className="font-small-medium text-ink block truncate">{entry.habit_name}</span>
                      {hint && <span className="font-caption text-caption text-muted-text block">{hint}</span>}
                    </div>
                    {entry.is_scheduled === false && currentStatus === null ? (
                      <span className="font-caption text-caption text-muted-text">Rest day</span>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {habitTierOptions(currentStatus).map((status) => (
                          <button
                            key={status}
                            type="button"
                            onClick={() => setHabitOverrides((prev) => ({ ...prev, [entry.habit_id]: status }))}
                            className={`px-3 h-8 rounded-lg font-caption text-caption transition-colors ${
                              currentStatus === status
                                ? 'bg-ink text-ground-chalk font-semibold'
                                : 'bg-surface text-ink border border-line'
                            }`}
                          >
                            {habitStatusLabel(status)}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </Disclosure>

          <Disclosure title="Sleep" summary={sleepSummary}>
            <div className="space-y-3 pt-2">
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
                    className={field}
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
                    className={field}
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
          </Disclosure>

          <Disclosure title="Screen time" summary={screenSummary}>
            <div className="space-y-2 pt-2">
              <div className="flex items-center justify-between">
                <span className="font-small text-ink">Total today</span>
                <span className="font-small-medium text-ink font-semibold">{formatMinutes(screenMinutes)}</span>
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
          </Disclosure>

          <Disclosure title="Mood and a note" summary={journalText.trim() ? 'Note written' : moodSummary}>
            <div className="space-y-3 pt-2">
              <MoodPicker
                valence={mood.valence}
                energy={mood.energy}
                onChange={(next) => {
                  setMood(next);
                  setMoodDirty(true);
                }}
              />
              <div className="space-y-1.5">
                <span className="font-caption text-caption text-muted-text uppercase tracking-wider block">
                  Note (encrypted)
                </span>
                <textarea
                  rows={3}
                  value={journalText}
                  onChange={(e) => setJournalText(e.target.value)}
                  placeholder="What got in the way today? Any wins?"
                  className="w-full bg-surface border border-line rounded-xl p-3 font-small text-ink focus:outline-none focus:ring-1 focus:ring-ink"
                />
              </div>
            </div>
          </Disclosure>

          {crisisDetected && bannerSupport && <SupportCard support={bannerSupport} />}
        </div>
      )}
    </Sheet>
  );
};
