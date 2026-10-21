import React from 'react';
import { useApp } from '../context/AppContext';
import { useTaskFocus } from '../hooks/useTaskFocus';
import { NextCard } from '../components/NextCard';
import { HabitChecklist } from '../components/HabitChecklist';
import { TaskList } from '../components/TaskList';
import { QuickAdd } from '../components/QuickAdd';
import { StatusChips } from '../components/StatusChips';
import { SevenDayWeave } from '../components/SevenDayWeave';
import { clockLabel, formatDayHeading } from '../lib/dates';

export const NowView: React.FC = () => {
  const { activeDate, checkinView } = useApp();
  const { focus, reload } = useTaskFocus();

  const hasHabits = (checkinView?.entries ?? []).some((e) => e.is_scheduled !== false);
  const hasTasks = focus ? focus.now.length + focus.small.length + focus.later_today.length + focus.stale.length > 0 : false;

  return (
    <div className="flex flex-col w-full pb-24 max-w-md mx-auto space-y-4 animate-fadeIn">
      <div className="flex items-baseline justify-between pt-2">
        <span className="font-title text-title text-ink tracking-tight">{formatDayHeading(activeDate)}</span>
        <span className="font-small text-small text-muted-text">{clockLabel()}</span>
      </div>

      <NextCard focus={focus} reloadFocus={reload} />

      {(hasHabits || hasTasks || checkinView) && (
        <section className="w-full bg-surface rounded-xl px-4 py-3 border border-line [&>*+*]:border-t [&>*+*]:border-line [&>*+*]:mt-3 [&>*+*]:pt-3">
          <HabitChecklist />
          <TaskList focus={focus} reload={reload} />
        </section>
      )}

      <QuickAdd onAdded={reload} />
      <StatusChips />
      <SevenDayWeave />
    </div>
  );
};
