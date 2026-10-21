import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { completeTask, deleteTask, patchTask, snoozeTask } from '../api/tasks';
import type { Task, TaskFocus } from '../types';
import { addDaysISO, localTodayISO } from '../lib/dates';
import { errorMessage } from '../lib/format';
import { taskMeta } from '../lib/taskLabels';

interface TaskListProps {
  focus: TaskFocus | null;
  reload: () => Promise<void>;
}

/** The person's tasks for now. Everything else (small things, later today, stale) sits behind one "more" row. */
export const TaskList: React.FC<TaskListProps> = ({ focus, reload }) => {
  const { showToast } = useApp();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [showMore, setShowMore] = useState(false);

  if (!focus) return null;
  const moreCount = focus.small.length + focus.later_today.length + focus.stale.length;
  if (focus.now.length + moreCount === 0) return null;

  const act = async (t: Task, fn: () => Promise<unknown>, okMsg?: string) => {
    setBusyId(t.id);
    try {
      await fn();
      if (okMsg) showToast(okMsg);
      setOpenId(null);
      await reload();
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Something went wrong'));
    } finally {
      setBusyId(null);
    }
  };

  const done = (t: Task) =>
    act(
      t,
      () => completeTask(t.id),
      t.repeat_days ? `Done. Next one in ${t.repeat_days} day${t.repeat_days === 1 ? '' : 's'}.` : undefined
    );
  const snooze = (t: Task) => act(t, () => snoozeTask(t.id, 60), 'Snoozed for an hour.');
  const tomorrow = (t: Task) =>
    act(t, () => patchTask(t.id, { due: addDaysISO(localTodayISO(), 1) }), 'Moved to tomorrow.');
  const drop = (t: Task) => act(t, () => deleteTask(t.id));

  const chip = 'px-3 h-8 rounded-lg bg-surface-container text-ink font-caption text-caption hover:bg-secondary-fixed disabled:opacity-50';

  const renderRow = (t: Task, stale = false) => {
    const meta = taskMeta(t);
    const open = stale || openId === t.id;
    const busy = busyId === t.id;
    return (
      <div key={t.id} className="py-2">
        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={busy}
            aria-label={`Mark ${t.title} done`}
            onClick={() => void done(t)}
            className="shrink-0 min-w-[44px] min-h-[44px] -m-2.5 p-2.5 flex items-center justify-center group"
          >
            <span className="w-6 h-6 rounded-full border-2 border-ink flex items-center justify-center group-active:bg-ink transition-colors">
              <span className="material-symbols-outlined text-[16px] text-transparent group-hover:text-ink group-active:text-ground-chalk">
                check
              </span>
            </span>
          </button>
          <div className="flex-1 min-w-0 ml-1">
            <p className="font-small-medium text-small-medium text-ink truncate">{t.title}</p>
            {meta && <p className="font-caption text-caption text-muted-text truncate">{meta}</p>}
          </div>
          {!stale && (
            <button
              type="button"
              aria-label={`More options for ${t.title}`}
              aria-expanded={open}
              onClick={() => setOpenId(open ? null : t.id)}
              className="w-9 h-9 rounded-lg flex items-center justify-center text-muted-text hover:bg-surface-container"
            >
              <span className="material-symbols-outlined text-[20px]">more_horiz</span>
            </button>
          )}
        </div>
        {open && (
          <div className="pl-9 pt-2 flex flex-wrap gap-1.5">
            {!stale && (
              <button type="button" disabled={busy} className={chip} onClick={() => void snooze(t)}>
                Snooze 1h
              </button>
            )}
            <button type="button" disabled={busy} className={chip} onClick={() => void tomorrow(t)}>
              Tomorrow
            </button>
            <button type="button" disabled={busy} className={chip} onClick={() => void drop(t)}>
              Drop
            </button>
          </div>
        )}
      </div>
    );
  };

  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <span className="font-caption text-caption text-muted-text uppercase tracking-wider">Tasks</span>
        {focus.hidden_now > 0 && (
          <span className="font-caption text-caption text-muted-text">+{focus.hidden_now} more after these</span>
        )}
      </div>
      <div className="divide-y divide-line">{focus.now.map((t) => renderRow(t))}</div>

      {moreCount > 0 && (
        <button
          type="button"
          aria-expanded={showMore}
          onClick={() => setShowMore((v) => !v)}
          className="mt-1 h-9 flex items-center gap-1 font-caption text-caption text-muted-text hover:text-ink"
        >
          <span>{showMore ? 'Show less' : `${moreCount} more`}</span>
          <span className={`material-symbols-outlined text-[16px] transition-transform ${showMore ? 'rotate-180' : ''}`}>
            expand_more
          </span>
        </button>
      )}

      {showMore && (
        <div className="space-y-2">
          {focus.small.length > 0 && (
            <div>
              <span className="font-caption text-caption text-muted-text uppercase tracking-wider">Small things</span>
              <div className="divide-y divide-line">{focus.small.map((t) => renderRow(t))}</div>
            </div>
          )}
          {focus.later_today.length > 0 && (
            <div>
              <span className="font-caption text-caption text-muted-text uppercase tracking-wider">Later today</span>
              <div className="divide-y divide-line">{focus.later_today.map((t) => renderRow(t))}</div>
            </div>
          )}
          {focus.stale.length > 0 && (
            <div>
              <span className="font-caption text-caption text-muted-text uppercase tracking-wider">
                Stopped nudging. Still want these?
              </span>
              <div className="divide-y divide-line">{focus.stale.map((t) => renderRow(t, true))}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
