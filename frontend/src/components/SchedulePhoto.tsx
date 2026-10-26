import React, { useEffect, useRef, useState } from 'react';
import { useApp } from '../context/AppContext';
import { addPhotoEvents, parseScheduleImage, type CalendarKind, type ProposedItem, type ScheduleProposal } from '../api/calendar';
import { createTask } from '../api/tasks';
import { errorMessage } from '../lib/format';
import { formatDayShort } from '../lib/dates';
import { shrinkImageIfNeeded } from '../lib/image';
import { Sheet } from './Sheet';

interface SchedulePhotoProps {
  /** Called after something was saved, so the task list reloads. */
  onAdded: () => Promise<void> | void;
  className?: string;
  disabled?: boolean;
  /** A picture that arrived some other way (Android share sheet): read it right away, with no button press. */
  autoFile?: File | null;
  /** The auto-read picture is finished with (saved, dismissed, or nothing found). */
  onAutoDone?: () => void;
  /** Render only the review sheet (used with autoFile). */
  hideButton?: boolean;
}

const KIND_LABEL: Record<CalendarKind, string> = { exam: 'Exam', class: 'Class', other: 'Event' };

function describe(i: ProposedItem): string {
  const day = i.date ? formatDayShort(i.date) : 'No date';
  const time = i.start ? (i.end ? `${i.start} to ${i.end}` : i.start) : i.type === 'event' ? 'all day' : '';
  const what = i.type === 'event' ? KIND_LABEL[i.kind ?? 'other'] : 'Task';
  return [what, day, time].filter(Boolean).join(' · ');
}

/**
 * Photo or screenshot of a timetable, date sheet or notice -> events and tasks. The model only PROPOSES; every row is
 * ticked by default and the person unticks what is wrong before anything is saved. Events go to the calendar (exam
 * nudges use them), tasks go to the task list with their deadline.
 */
export const SchedulePhoto: React.FC<SchedulePhotoProps> = ({ onAdded, className, disabled, autoFile, onAutoDone, hideButton }) => {
  const { showToast, bumpData } = useApp();
  const fileRef = useRef<HTMLInputElement>(null);
  const [reading, setReading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [proposal, setProposal] = useState<ScheduleProposal | null>(null);
  const [picked, setPicked] = useState<boolean[]>([]);

  const autoActive = useRef(false);
  const autoStartedFor = useRef<File | null>(null);
  const finishAuto = () => {
    if (autoActive.current) {
      autoActive.current = false;
      onAutoDone?.();
    }
  };

  const readFile = async (file: File) => {
    if (reading) return;
    setReading(true);
    let opened = false;
    try {
      const blob = await shrinkImageIfNeeded(file);
      const res = await parseScheduleImage(blob);
      if (res.items.length === 0) {
        showToast(
          res.skipped > 0
            ? `Nothing with a calendar date in that (${res.skipped} undated). A weekly timetable is easier to bring in as a calendar file.`
            : 'I could not find anything dated in that picture.'
        );
        return;
      }
      setProposal(res);
      setPicked(res.items.map(() => true));
      opened = true;
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not read that picture'));
    } finally {
      setReading(false);
      if (!opened) finishAuto();
    }
  };

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // the same photo can be chosen again
    if (!file) return;
    await readFile(file);
  };

  useEffect(() => {
    if (!autoFile || autoStartedFor.current === autoFile) return; // StrictMode runs effects twice: read the picture once
    autoStartedFor.current = autoFile;
    autoActive.current = true;
    void readFile(autoFile);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoFile]);

  const close = () => {
    if (saving) return;
    setProposal(null);
    finishAuto();
  };

  const save = async () => {
    if (!proposal || saving) return;
    const chosen = proposal.items.filter((_, i) => picked[i]);
    const events = chosen.filter((i) => i.type === 'event' && i.date);
    const tasks = chosen.filter((i) => i.type === 'task');
    if (chosen.length === 0) return;
    setSaving(true);
    let eventsAdded = 0;
    let eventsSeen = 0;
    let tasksAdded = 0;
    let failed = 0;
    try {
      if (events.length > 0) {
        try {
          const r = await addPhotoEvents(
            events.map((i) => ({ title: i.title, date: i.date as string, start: i.start, end: i.end, kind: i.kind ?? 'other' }))
          );
          eventsAdded = r.added;
          eventsSeen = r.duplicates;
        } catch (err: unknown) {
          failed += events.length;
          showToast(errorMessage(err, 'Could not add the events'));
        }
      }
      for (const t of tasks) {
        try {
          await createTask({
            title: t.title,
            importance: t.date ? 3 : 2, // a dated deadline off a notice is a real deadline
            due: t.date ? (t.start ? `${t.date}T${t.start}` : t.date) : null,
          });
          tasksAdded += 1;
        } catch {
          failed += 1;
        }
      }
    } finally {
      setSaving(false);
    }
    const parts = [
      eventsAdded > 0 ? `${eventsAdded} event${eventsAdded === 1 ? '' : 's'}` : '',
      tasksAdded > 0 ? `${tasksAdded} task${tasksAdded === 1 ? '' : 's'}` : '',
    ].filter(Boolean);
    if (parts.length > 0) showToast(`Added ${parts.join(' and ')}.${failed ? ` ${failed} could not be added.` : ''}`);
    else if (eventsSeen > 0 && failed === 0) showToast('Those events were already in your calendar.');
    else if (failed > 0) showToast(`${failed} could not be added. Try again.`);
    if (parts.length > 0 || eventsSeen > 0) {
      setProposal(null);
      bumpData();
      await onAdded();
    }
  };

  const count = picked.filter(Boolean).length;

  return (
    <>
      <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => void onFile(e)} />
      <button
        type="button"
        aria-label="Add from a photo of a timetable or notice"
        title="Photo of a timetable or notice"
        disabled={disabled || reading}
        onClick={() => fileRef.current?.click()}
        className={
          className ??
          'w-10 h-10 shrink-0 rounded-xl bg-surface-container text-ink flex items-center justify-center hover:bg-secondary-fixed disabled:opacity-40'
        }
      >
        <span className="material-symbols-outlined text-[20px]">{reading ? 'hourglass_top' : 'photo_camera'}</span>
      </button>

      <Sheet
        open={proposal !== null}
        onClose={close}
        eyebrow="From your picture"
        title="Add these?"
        footer={
          <button
            type="button"
            disabled={saving || count === 0}
            onClick={() => void save()}
            className="w-full h-12 rounded-xl bg-ink text-ground-chalk font-body-strong disabled:opacity-40"
          >
            {saving ? 'Adding…' : count === 0 ? 'Nothing selected' : `Add ${count}`}
          </button>
        }
      >
        {proposal && (
          <div className="space-y-3">
            <p className="font-caption text-caption text-muted-text leading-relaxed">
              Check each one against the picture. Untick anything that looks wrong.
            </p>
            <div className="divide-y divide-line">
              {proposal.items.map((i, idx) => (
                <label key={`${i.type}-${i.title}-${i.date}-${idx}`} className="flex items-start gap-3 py-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={picked[idx] ?? false}
                    onChange={() => setPicked((p) => p.map((v, j) => (j === idx ? !v : v)))}
                    className="mt-1 w-5 h-5 shrink-0 accent-black"
                  />
                  <span className="min-w-0">
                    <span className="font-small-medium text-small-medium text-ink block break-words">{i.title}</span>
                    <span className="font-caption text-caption text-muted-text block">{describe(i)}</span>
                  </span>
                </label>
              ))}
            </div>
            {proposal.skipped > 0 && (
              <p className="font-caption text-caption text-muted-text leading-relaxed">
                {proposal.skipped} more had no calendar date, like a weekly timetable, so I left {proposal.skipped === 1 ? 'it' : 'them'} out.
                Add those by hand, or import a calendar file.
              </p>
            )}
          </div>
        )}
      </Sheet>
    </>
  );
};
