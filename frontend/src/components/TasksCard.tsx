import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useApp } from '../context/AppContext';
import { captureTasks, completeTask, deleteTask, getTaskFocus, patchTask, snoozeTask } from '../api/tasks';
import type { SupportPayload, Task, TaskFocus } from '../types';
import { addDaysISO, formatDayShort, localTodayISO } from '../lib/dates';
import { errorMessage } from '../lib/format';

const REFRESH_MS = 60_000;

function clock12(hhmm: string): string {
  const [h, m] = hhmm.split(':').map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`;
}

function repeatLabel(days: number | null): string | null {
  if (!days) return null;
  if (days === 1) return 'daily';
  if (days === 7) return 'weekly';
  return `every ${days} days`;
}

/** "Today 5:00 PM", "Tomorrow", "Overdue · 9 Oct", ... built from the backend's local-time strings (no tz math here). */
function metaLabel(t: Task): string {
  const today = localTodayISO();
  const parts: string[] = [];
  if (t.due) {
    const day = t.due.slice(0, 10);
    const time = t.due_has_time ? clock12(t.due.slice(11, 16)) : null;
    let label: string;
    if (day < today) label = `Overdue · ${formatDayShort(day)}`;
    else if (day === today) label = 'Today';
    else if (day === addDaysISO(today, 1)) label = 'Tomorrow';
    else label = formatDayShort(day);
    parts.push(time && day >= today ? `${label} ${time}` : label);
  } else if (t.remind) {
    parts.push(`Reminder ${clock12(t.remind.slice(11, 16))}`);
  }
  const rep = repeatLabel(t.repeat_days);
  if (rep) parts.push(rep);
  return parts.join(' · ');
}

interface RowProps {
  task: Task;
  busy: boolean;
  stale?: boolean;
  onDone: (t: Task) => void;
  onSnooze: (t: Task) => void;
  onTomorrow: (t: Task) => void;
  onDrop: (t: Task) => void;
}

const TaskRow: React.FC<RowProps> = ({ task, busy, stale, onDone, onSnooze, onTomorrow, onDrop }) => {
  const meta = metaLabel(task);
  return (
    <div className="flex items-center gap-3 py-2">
      <button
        type="button"
        disabled={busy}
        aria-label={`Mark ${task.title} done`}
        onClick={() => onDone(task)}
        className="w-6 h-6 shrink-0 rounded-full border-2 border-ink flex items-center justify-center active:bg-ink transition-colors group"
      >
        <span className="material-symbols-outlined text-[16px] text-transparent group-hover:text-ink group-active:text-ground-chalk">
          check
        </span>
      </button>
      <div className="flex-1 min-w-0">
        <p className="font-small-medium text-ink truncate">{task.title}</p>
        {meta && <p className="font-caption text-caption text-muted-text truncate">{meta}</p>}
      </div>
      {stale ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => onTomorrow(task)}
          className="px-2 h-8 rounded-lg bg-surface-container font-caption text-caption text-ink"
        >
          Tomorrow
        </button>
      ) : (
        <button
          type="button"
          disabled={busy}
          aria-label={`Snooze ${task.title} for an hour`}
          onClick={() => onSnooze(task)}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-text hover:bg-surface-container"
        >
          <span className="material-symbols-outlined text-[18px]">snooze</span>
        </button>
      )}
      <button
        type="button"
        disabled={busy}
        aria-label={`Drop ${task.title}`}
        onClick={() => onDrop(task)}
        className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-text hover:bg-surface-container"
      >
        <span className="material-symbols-outlined text-[18px]">close</span>
      </button>
    </div>
  );
};

export const TasksCard: React.FC = () => {
  const { showToast, demoMode, dataEpoch } = useApp();
  const [focus, setFocus] = useState<TaskFocus | null>(null);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [support, setSupport] = useState<SupportPayload | null>(null);
  const alive = useRef(true);

  const load = useCallback(async () => {
    try {
      const f = await getTaskFocus();
      if (alive.current) setFocus(f);
    } catch {
      /* keep what we have; the next refresh retries */
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    load();
    const timer = window.setInterval(load, REFRESH_MS);
    const onVisible = () => document.visibilityState === 'visible' && load();
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [load, demoMode, dataEpoch]);

  const submit = async () => {
    const value = text.trim();
    if (!value || sending) return;
    setSending(true);
    setSupport(null);
    try {
      const res = await captureTasks(value);
      if (res.mode === 'support') {
        setSupport(res.support);
        return; // nothing was saved; keep the text so it isn't lost
      }
      setText('');
      const n = res.tasks.length;
      const dup = res.skipped_duplicates ? ` (${res.skipped_duplicates} already on your list)` : '';
      if (n === 0) showToast(res.skipped_duplicates ? 'Already on your list.' : 'No task found in that.');
      else if (res.mode === 'fallback') showToast(`Saved ${n} as written. AI was unavailable, so set times yourself.${dup}`);
      else showToast(`Added ${n} task${n === 1 ? '' : 's'}.${dup}`);
      await load();
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not add tasks'));
    } finally {
      setSending(false);
    }
  };

  const act = async (t: Task, fn: () => Promise<unknown>, okMsg?: string) => {
    setBusyId(t.id);
    try {
      await fn();
      if (okMsg) showToast(okMsg);
      await load();
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Something went wrong'));
    } finally {
      setBusyId(null);
    }
  };

  const rowProps = (t: Task, stale = false): RowProps => ({
    task: t,
    busy: busyId === t.id,
    stale,
    onDone: (x) => act(x, () => completeTask(x.id), x.repeat_days ? `Done. Next one in ${x.repeat_days} day${x.repeat_days === 1 ? '' : 's'}.` : undefined),
    onSnooze: (x) => act(x, () => snoozeTask(x.id, 60), 'Snoozed for an hour.'),
    onTomorrow: (x) => act(x, () => patchTask(x.id, { due: addDaysISO(localTodayISO(), 1) }), 'Moved to tomorrow.'),
    onDrop: (x) => act(x, () => deleteTask(x.id)),
  });

  const empty =
    focus !== null &&
    focus.now.length + focus.small.length + focus.later_today.length + focus.stale.length === 0;

  const renderSection = (label: string, items: Task[], opts: { stale?: boolean; footer?: string } = {}) =>
    items.length === 0 ? null : (
      <div className="pt-3" key={label}>
        <span className="font-caption text-caption text-muted-text uppercase tracking-wider">{label}</span>
        <div className="divide-y divide-line">
          {items.map((t) => (
            <TaskRow key={t.id} {...rowProps(t, opts.stale)} />
          ))}
        </div>
        {opts.footer && <p className="font-caption text-caption text-muted-text pt-1">{opts.footer}</p>}
      </div>
    );

  return (
    <section className="w-full bg-surface rounded-xl p-4 border border-line shadow-sm mb-8">
      <div className="flex items-baseline justify-between">
        <h3 className="font-section text-section text-ink">Tasks</h3>
        {focus && focus.backlog_count > 0 && (
          <span className="font-caption text-caption text-muted-text">{focus.backlog_count} with no date</span>
        )}
      </div>

      <div className="mt-3 flex flex-col gap-2">
        <textarea
          rows={2}
          value={text}
          maxLength={1000}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit();
          }}
          placeholder="Dump it in your own words: tasks, reminders, things you keep forgetting…"
          className="w-full bg-surface-container-low border border-line rounded-lg px-3 py-2 font-small text-ink resize-none"
        />
        <button
          type="button"
          disabled={sending || !text.trim()}
          onClick={submit}
          className="h-10 rounded-xl bg-ink text-ground-chalk font-body-strong disabled:opacity-40"
        >
          {sending ? 'Sorting…' : 'Add'}
        </button>
      </div>

      {support && (
        <div className="mt-3 p-3 rounded-xl bg-surface-container-low border border-line space-y-2">
          <p className="font-small text-ink">{support.message}</p>
          {support.resources.map((r) => (
            <p key={r.name} className="font-caption text-caption text-muted-text">
              <strong className="text-ink">{r.name}</strong> · {r.contact} · {r.detail}
            </p>
          ))}
        </div>
      )}

      {renderSection('Now', focus?.now ?? [], {
        footer: focus && focus.hidden_now > 0 ? `+${focus.hidden_now} more after these` : undefined,
      })}
      {renderSection('Small things', focus?.small ?? [])}
      {renderSection('Later today', focus?.later_today ?? [])}
      {renderSection('Stopped nudging. Still want these?', focus?.stale ?? [], { stale: true })}

      {empty && <p className="font-small text-muted-text pt-3">Nothing due. Anything on your mind goes in the box above.</p>}
    </section>
  );
};
