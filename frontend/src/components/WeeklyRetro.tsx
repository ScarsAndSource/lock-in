import React, { useState, useEffect, useCallback } from 'react';
import { getLatestRetro, updateRetroTone, completeRetro, generateRetro } from '../api/retros';
import { RetroDetail, WeekMode } from '../types';
import { useApp } from '../context/AppContext';
import { addDaysISO } from '../lib/dates';
import { IdentityVote } from './growth/IdentityVote';
import { errorMessage, formatMinutes, formatPct } from '../lib/format';

interface Chip {
  label: string;
  value: string;
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const humanize = (key: string): string => key.replace(/_/g, ' ');

/**
 * The stored summary is nested (study, urges, mission, chains...). Turn the parts worth a glance into chips,
 * and show any other flat string/number value as-is. Objects and arrays are never printed raw.
 */
export function summaryChips(summary: Record<string, unknown> | null | undefined): Chip[] {
  if (!summary) return [];
  const chips: Chip[] = [];
  const handled = new Set<string>(['week_mode', 'week', 'days', 'domains', 'habit_changes', 'habit_overall_prev_pct']);

  if (isNum(summary.habit_overall_pct)) {
    chips.push({ label: 'Habit consistency', value: formatPct(summary.habit_overall_pct, 0) });
  }
  handled.add('habit_overall_pct');

  if (isNum(summary.clean_day_count)) {
    chips.push({ label: 'Clean days', value: `${summary.clean_day_count} / 7` });
  }
  handled.add('clean_day_count');
  handled.add('clean_days');

  if (Array.isArray(summary.chains)) {
    chips.push({ label: 'Slip chains', value: String(summary.chains.length) });
  }
  handled.add('chains');
  if (Array.isArray(summary.unexplained_slips) && summary.unexplained_slips.length > 0) {
    chips.push({ label: 'Unexplained slips', value: String(summary.unexplained_slips.length) });
  }
  handled.add('unexplained_slips');
  handled.add('pattern_echoes');

  const study = summary.study;
  if (isRecord(study)) {
    if (isNum(study.actual_minutes)) chips.push({ label: 'Study time', value: formatMinutes(study.actual_minutes) });
    if (isNum(study.follow_through_pct)) {
      chips.push({ label: 'Study follow-through', value: formatPct(study.follow_through_pct, 0) });
    }
  }
  handled.add('study');

  const urges = summary.urges;
  if (isRecord(urges) && isNum(urges.total) && urges.total > 0) {
    chips.push({ label: 'Urges resisted', value: `${isNum(urges.resisted) ? urges.resisted : 0} of ${urges.total}` });
  }
  handled.add('urges');

  const mission = summary.mission;
  if (isRecord(mission) && typeof mission.title === 'string') {
    chips.push({
      label: 'Mission',
      value: isNum(mission.day_number) && isNum(mission.days_total) ? `Day ${mission.day_number} of ${mission.days_total}` : mission.title,
    });
  }
  handled.add('mission');

  for (const [key, val] of Object.entries(summary)) {
    if (handled.has(key)) continue;
    if (typeof val === 'string' || isNum(val)) chips.push({ label: humanize(key), value: String(val) });
  }
  return chips;
}

export const WeeklyRetro: React.FC = () => {
  const { showToast, dataEpoch, demoMode, profile } = useApp();
  const [retro, setRetro] = useState<RetroDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setRetro(await getLatestRetro());
    } catch (err: unknown) {
      setLoadError(errorMessage(err, 'Could not load your weekly retro'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, dataEpoch, demoMode]);

  const handleGenerate = async () => {
    setIsSubmitting(true);
    try {
      setRetro(await generateRetro('auto'));
      showToast('Weekly retro ready');
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not generate the retro'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleToneChange = async (mode: WeekMode) => {
    if (!retro) return;
    setIsSubmitting(true);
    try {
      const updated = await updateRetroTone(retro.week_start, mode);
      setRetro(updated);
      showToast(`Retro tone set to ${mode.toUpperCase()} mode`);
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not change the tone'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleComplete = async () => {
    if (!retro) return;
    setIsSubmitting(true);
    try {
      await completeRetro(retro.week_start);
      setRetro((prev) => (prev ? { ...prev, status: 'completed', completed_at: new Date().toISOString() } : null));
      showToast('Weekly retrospective closed and feedback archived!');
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not close the week'));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading && !retro) {
    return (
      <div className="bg-surface rounded-xl p-5 border border-line shadow-sm font-small text-muted-text">
        Loading your weekly retro…
      </div>
    );
  }

  if (loadError && !retro) {
    return (
      <div className="bg-surface rounded-xl p-5 border border-line shadow-sm space-y-3">
        <p role="alert" className="font-small text-ink">{loadError}</p>
        <button
          type="button"
          onClick={() => void load()}
          className="h-10 px-4 bg-surface-container text-ink border border-line rounded-lg font-caption text-caption font-semibold"
        >
          Try again
        </button>
      </div>
    );
  }

  if (!retro) {
    return (
      <div className="bg-surface rounded-xl p-5 border border-line shadow-sm space-y-3">
        <div>
          <span className="font-caption text-caption text-muted-text uppercase tracking-wider block">
            Weekly review
          </span>
          <h3 className="font-title text-title text-ink text-xl">No review yet</h3>
        </div>
        <p className="font-small text-muted-text">
          Your retro reads last week&rsquo;s logs and names the chain behind any slip. Generate it once the week is done.
        </p>
        <button
          type="button"
          disabled={isSubmitting}
          onClick={() => void handleGenerate()}
          className="w-full h-11 bg-ink text-ground-chalk rounded-xl font-body-strong disabled:opacity-60 hover:bg-secondary transition-colors"
        >
          {isSubmitting ? 'Reading your week…' : 'Generate last week’s retro'}
        </button>
      </div>
    );
  }

  const currentMode = retro.week_mode?.mode || 'normal';
  const chips = summaryChips(retro.summary);
  const newerMayExist = Boolean(profile?.today) && retro.week_end <= addDaysISO(profile!.today, -8);

  return (
    <div className="bg-surface rounded-xl p-5 border border-line shadow-sm space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <span className="font-caption text-caption text-muted-text uppercase tracking-wider block">
            Weekly review
          </span>
          <h3 className="font-title text-title text-ink text-xl">
            Week of {retro.week_start}
          </h3>
        </div>
        <div className="flex items-center gap-1 bg-surface-container p-0.5 rounded-lg">
          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => handleToneChange('normal')}
            className={`px-2 py-1 rounded text-[11px] font-semibold transition-colors ${
              currentMode === 'normal' ? 'bg-ink text-ground-chalk' : 'text-ink'
            }`}
          >
            Normal
          </button>
          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => handleToneChange('rough')}
            className={`px-2 py-1 rounded text-[11px] font-semibold transition-colors ${
              currentMode === 'rough' ? 'bg-ink text-ground-chalk' : 'text-ink'
            }`}
          >
            Rough Week
          </button>
        </div>
      </div>

      <p className="font-small-medium text-ink leading-relaxed">{retro.narrative}</p>

      <IdentityVote weekStart={retro.week_start} />

      {/* Concrete next step */}
      <div className="p-3 bg-surface-container-low rounded-lg border border-surface-container">
        <span className="font-caption text-caption text-muted-text uppercase tracking-wider block mb-0.5">
          Focus for next week
        </span>
        <p className="font-small text-small text-ink font-semibold">{retro.next_step}</p>
      </div>

      {/* Metric chips */}
      {chips.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
          {chips.map((chip) => (
            <div key={chip.label} className="p-2.5 bg-surface-container-low rounded-lg text-center">
              <span className="font-caption text-caption text-muted-text block capitalize">{chip.label}</span>
              <strong className="font-small-medium text-ink text-base">{chip.value}</strong>
            </div>
          ))}
        </div>
      )}

      {/* Complete Button */}
      {retro.status !== 'completed' ? (
        <button
          type="button"
          disabled={isSubmitting}
          onClick={handleComplete}
          className="w-full h-11 bg-ink text-ground-chalk rounded-xl font-body-strong text-body-strong flex items-center justify-center gap-2 hover:bg-secondary transition-colors"
        >
          <span>Close & Archive Week</span>
          <span className="material-symbols-outlined text-[18px]">done_all</span>
        </button>
      ) : (
        <div className="text-center py-1 font-caption text-caption text-muted-text">
          ✓ Completed on {new Date(retro.completed_at || '').toLocaleDateString()}
        </div>
      )}

      {newerMayExist && (
        <button
          type="button"
          disabled={isSubmitting}
          onClick={() => void handleGenerate()}
          className="w-full h-10 bg-surface-container text-ink border border-line rounded-lg font-caption text-caption font-semibold disabled:opacity-60"
        >
          {isSubmitting ? 'Reading your week…' : 'Generate last week’s retro'}
        </button>
      )}
    </div>
  );
};
