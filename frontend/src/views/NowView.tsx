import React, { useCallback, useState } from 'react';
import { useApp } from '../context/AppContext';
import { useTaskFocus } from '../hooks/useTaskFocus';
import { useCompanion } from '../hooks/useCompanion';
import { DEMO_RHYTHM } from '../api/companion';
import { DayOrbit } from '../components/DayOrbit';
import { NextCard } from '../components/NextCard';
import { GentlePrompt } from '../components/growth/GentlePrompt';
import { HabitChecklist } from '../components/HabitChecklist';
import { TaskList } from '../components/TaskList';
import { QuickAdd } from '../components/QuickAdd';
import { StatusChips } from '../components/StatusChips';
import { InferenceChip } from '../components/InferenceChip';
import { SevenDayWeave } from '../components/SevenDayWeave';
import { formatDayHeading } from '../lib/dates';

const NONE: ReadonlySet<string> = new Set<string>();

function deviceMinute(): number {
  const d = new Date();
  return d.getHours() * 60 + d.getMinutes();
}

export const NowView: React.FC = () => {
  const { activeDate, checkinView, demoMode } = useApp();
  const { focus, reload } = useTaskFocus();
  const [skipped, setSkipped] = useState<ReadonlySet<string>>(NONE);
  const { data: companion, refresh } = useCompanion(skipped);

  const reloadAll = useCallback(async () => {
    await reload();
    await refresh();
  }, [reload, refresh]);
  const onSkip = useCallback((key: string) => setSkipped((prev) => new Set(prev).add(key)), []);

  const entries = (checkinView?.entries ?? []).filter((e) => e.is_scheduled !== false);
  const confirmed = checkinView?.already_confirmed ?? false;
  const localTotal = entries.length;
  const localDone = entries.filter((e) => e.status !== null && e.status !== 'skipped' && (!e.is_default || confirmed)).length;

  const hasHabits = localTotal > 0;
  const hasTasks = focus ? focus.now.length + focus.small.length + focus.later_today.length + focus.stale.length > 0 : false;

  return (
    <div className="flex flex-col w-full pb-24 max-w-md mx-auto space-y-4 animate-fadeIn">
      <DayOrbit
        rhythm={companion?.rhythm ?? (demoMode ? DEMO_RHYTHM : null)}
        localMinute={companion?.local_minute ?? deviceMinute()}
        heading={formatDayHeading(activeDate)}
        done={companion?.habits_done ?? localDone}
        total={companion?.habits_total ?? localTotal}
        isDemo={demoMode}
      />

      <NextCard companion={companion} focus={focus} skipped={skipped} onSkip={onSkip} reloadAll={reloadAll} />

      <GentlePrompt />

      {(hasHabits || hasTasks || checkinView) && (
        <section className="w-full bg-surface rounded-xl px-4 py-3 border border-line [&>*+*]:border-t [&>*+*]:border-line [&>*+*]:mt-3 [&>*+*]:pt-3">
          <HabitChecklist />
          <TaskList focus={focus} reload={reloadAll} />
        </section>
      )}

      <QuickAdd onAdded={reloadAll} />
      <InferenceChip />
      <StatusChips />
      <SevenDayWeave />
    </div>
  );
};
