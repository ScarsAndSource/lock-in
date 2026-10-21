import type { CheckinEntry, CheckinView, Task, TaskFocus } from '../types';
import { taskMeta } from './taskLabels';

/**
 * Picks the ONE thing the Now screen leads with. Pure: no clock, no network, so it is trivially testable.
 * (Phase 2 moves this ranking to the server with the rhythm model; the card and its target shape stay the same.)
 */
export type NextTarget =
  | { type: 'habit'; habitId: string; status: 'done' | 'floor' }
  | { type: 'task'; taskId: string }
  | { type: 'checkin' }
  | { type: 'urge' }
  | { type: 'none' };

export interface NextAction {
  /** Stable id, so "Not now" can hide exactly this suggestion for the session. */
  key: string;
  kind: 'floor' | 'deadline' | 'guard' | 'close' | 'habit' | 'task' | 'checkin' | 'clear' | 'exam';
  eyebrow: string;
  title: string;
  detail: string | null;
  cta: string | null;
  target: NextTarget;
  /** Set by the server companion: its one-line voice and the honest reason this card is on top. */
  voice?: string | null;
  why?: string | null;
}

export interface NextInput {
  checkin: CheckinView;
  focus: TaskFocus | null;
  now: Date;
  skipped: ReadonlySet<string>;
}

const EVENING_HOUR = 20;

function clear(confirmed: boolean): NextAction {
  return {
    key: 'clear',
    kind: 'clear',
    eyebrow: 'All clear',
    title: confirmed ? 'Locked in.' : 'Nothing open.',
    detail: 'Nothing else needs you right now.',
    cta: null,
    target: { type: 'none' },
  };
}

function taskAction(t: Task, kind: 'deadline' | 'task'): NextAction {
  return {
    key: `task:${t.id}`,
    kind,
    eyebrow: kind === 'deadline' ? 'Deadline' : 'Next up',
    title: t.title,
    detail: taskMeta(t) || null,
    cta: 'Done',
    target: { type: 'task', taskId: t.id },
  };
}

function floorAction(e: CheckinEntry): NextAction {
  return {
    key: `floor:${e.habit_id}`,
    kind: 'floor',
    eyebrow: 'Floor day',
    title: e.habit_name,
    detail: e.floor_text ? `Floor: ${e.floor_text}` : 'Keep it small today. The floor version counts.',
    cta: 'Floor done',
    target: { type: 'habit', habitId: e.habit_id, status: 'floor' },
  };
}

export function pickNextAction({ checkin, focus, now, skipped }: NextInput): NextAction {
  const entries = checkin.entries.filter((e) => e.is_scheduled !== false);
  const confirmed = checkin.already_confirmed;
  const bounce = checkin.bounce?.active === true;
  const nowTasks = focus?.now ?? [];
  const out: NextAction[] = [];

  if (bounce) {
    // After a slip the proposals are already lowered to the floor; lead with the first one not yet done.
    const e = entries.find((x) => x.status === null || (x.is_default && x.status === 'floor'));
    if (e) out.push(floorAction(e));
  }

  const deadline = nowTasks.find((t) => t.importance === 3);
  if (deadline) out.push(taskAction(deadline, 'deadline'));

  if (!confirmed && now.getHours() >= EVENING_HOUR) {
    out.push({
      key: 'close',
      kind: 'close',
      eyebrow: 'End of day',
      title: 'Close today',
      detail: 'About 10 seconds. Defaults cover the usual.',
      cta: 'Lock it in',
      target: { type: 'checkin' },
    });
  }

  if (!bounce) {
    // status === null means there is nothing to propose (a new habit). A proposed default is handled by the check-in.
    const open = entries.find((e) => e.status === null);
    if (open) {
      out.push({
        key: `habit:${open.habit_id}`,
        kind: 'habit',
        eyebrow: 'Next habit',
        title: open.habit_name,
        detail: open.floor_text ? `Floor: ${open.floor_text}` : null,
        cta: 'Done',
        target: { type: 'habit', habitId: open.habit_id, status: 'done' },
      });
    }
  }

  const other = nowTasks.find((t) => t.id !== deadline?.id);
  if (other) out.push(taskAction(other, 'task'));

  if (!confirmed) {
    out.push({
      key: 'checkin',
      kind: 'checkin',
      eyebrow: 'Check-in',
      title: 'Today’s check-in',
      detail: 'Whenever you’re ready. Defaults cover the usual.',
      cta: 'Open',
      target: { type: 'checkin' },
    });
  }

  return out.find((a) => !skipped.has(a.key)) ?? clear(confirmed);
}
