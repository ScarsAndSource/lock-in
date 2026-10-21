import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useApp } from '../context/AppContext';
import {
  CalendarSourceDto,
  ExamDto,
  MAX_ICS_BYTES,
  deleteCalendarSource,
  getCalendarSources,
  getExams,
  importIcs,
  setEventKind,
} from '../api/calendar';
import { errorMessage } from '../lib/format';

const whenLabel = (e: ExamDto): string => {
  if (e.days_until === 0) return 'Today';
  if (e.days_until === 1) return 'Tomorrow';
  return `In ${e.days_until} days`;
};

const timeLabel = (e: ExamDto): string =>
  e.all_day
    ? 'All day'
    : new Date(e.starts_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

/**
 * Import a timetable or exam schedule (.ics exported from Google Calendar, Outlook, Apple Calendar or a university
 * portal). Re-importing the same file replaces its future events. Exams are guessed from titles; one tap fixes a guess.
 * Mounted inside Settings (the merge step adds the Disclosure row).
 */
export const CalendarImport: React.FC = () => {
  const { demoMode, bumpData, showToast } = useApp();
  const [sources, setSources] = useState<CalendarSourceDto[]>([]);
  const [exams, setExams] = useState<ExamDto[]>([]);
  const [busy, setBusy] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (demoMode) return;
    try {
      const [s, e] = await Promise.all([getCalendarSources(), getExams()]);
      setSources(s);
      setExams(e);
    } catch (err) {
      showToast(errorMessage(err, 'Could not load your calendar'));
    }
  }, [demoMode, showToast]);

  useEffect(() => {
    void load();
  }, [load]);

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    if (file.size > MAX_ICS_BYTES) {
      showToast('That file is too large. Export a shorter date range.');
      return;
    }
    setBusy(true);
    try {
      const label = file.name.replace(/\.[^.]+$/, '').trim().slice(0, 40) || undefined;
      const result = await importIcs(await file.text(), label);
      setWarnings(result.warnings);
      showToast(`Imported ${result.added} events${result.exams ? `, ${result.exams} look like exams` : ''}`);
      await load();
      bumpData();
    } catch (err) {
      showToast(errorMessage(err, 'Could not import that file'));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const notAnExam = async (e: ExamDto) => {
    try {
      await setEventKind(e.id, 'other');
      await load();
      bumpData();
    } catch (err) {
      showToast(errorMessage(err, 'Could not update that event'));
    }
  };

  const remove = async (s: CalendarSourceDto) => {
    try {
      await deleteCalendarSource(s.source);
      await load();
      bumpData();
      showToast(`Removed ${s.source}`);
    } catch (err) {
      showToast(errorMessage(err, 'Could not remove that calendar'));
    }
  };

  if (demoMode) {
    return (
      <p className="font-caption text-caption text-muted-text">
        Calendar import needs the live backend. Turn demo mode off first.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <p className="font-caption text-caption text-muted-text">
        Import an .ics file and the app will plan around your exams. Only titles and times are kept: no locations, notes
        or attendees.
      </p>

      <input
        ref={fileRef}
        type="file"
        accept=".ics,text/calendar"
        className="sr-only"
        aria-label="Choose a calendar file"
        onChange={(ev) => void onFile(ev.target.files?.[0])}
      />

      <button
        type="button"
        disabled={busy}
        onClick={() => fileRef.current?.click()}
        className="w-full min-h-[48px] rounded-xl bg-ink text-ground-chalk font-small-medium text-small-medium disabled:opacity-50"
      >
        {busy ? 'Importing…' : 'Choose .ics file'}
      </button>

      {warnings.length > 0 && (
        <ul className="font-caption text-caption text-muted-text list-disc pl-5">
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}

      {exams.length > 0 && (
        <div>
          <h4 className="font-small-medium text-small-medium text-ink mb-1">Upcoming exams</h4>
          <ul className="space-y-1.5">
            {exams.slice(0, 8).map((e) => (
              <li key={e.id} className="flex items-center gap-2 px-3 py-2 bg-surface border border-line rounded-xl">
                <span className="flex-1 min-w-0">
                  <span className="font-small-medium text-small-medium text-ink block truncate">{e.title}</span>
                  <span className="font-caption text-caption text-muted-text block">
                    {whenLabel(e)} · {timeLabel(e)}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => void notAnExam(e)}
                  className="min-h-[44px] px-3 rounded-lg border border-line text-ink font-caption text-caption"
                >
                  Not an exam
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {sources.length > 0 && (
        <div>
          <h4 className="font-small-medium text-small-medium text-ink mb-1">Imported calendars</h4>
          <ul className="space-y-1.5">
            {sources.map((s) => (
              <li key={s.source} className="flex items-center gap-2 px-3 py-2 bg-surface border border-line rounded-xl">
                <span className="flex-1 min-w-0">
                  <span className="font-small-medium text-small-medium text-ink block truncate">{s.source}</span>
                  <span className="font-caption text-caption text-muted-text block">
                    {s.events} events{s.exams ? `, ${s.exams} exams` : ''}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => void remove(s)}
                  className="min-h-[44px] px-3 rounded-lg border border-line text-ink font-caption text-caption"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
