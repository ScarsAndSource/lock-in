import React, { useCallback, useEffect, useState } from 'react';
import { useApp } from '../../context/AppContext';
import { archiveRecall, createRecall, listRecall } from '../../api/journey';
import type { RecallSet } from '../../api/journey';
import { errorMessage } from '../../lib/format';
import { CLS } from '../growth/ui';

export function shortDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

/** Exam radar: just the subject and the topic NAMES that will come in the exam. Not notes, not a study tool. */
export const RadarCard: React.FC = () => {
  const { showToast, bumpData } = useApp();
  const [sets, setSets] = useState<RecallSet[] | null>(null);
  const [label, setLabel] = useState('');
  const [topics, setTopics] = useState('');
  const [exam, setExam] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    listRecall()
      .then(setSets)
      .catch(() => setSets([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const add = async () => {
    setBusy(true);
    try {
      setSets(await createRecall(label.trim(), topics, exam || null));
      setLabel('');
      setTopics('');
      setExam('');
      bumpData();
    } catch (e) {
      showToast(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await archiveRecall(id);
      load();
      bumpData();
    } catch (e) {
      showToast(errorMessage(e));
    }
  };

  return (
    <div className="space-y-3">
      <p className={CLS.muted}>
        Write what will come in the exam: subject and topic names, nothing more. I bring the list back after 1, 3, 7 and
        14 days, and re-plan around easy weeks, pauses and other exams.
      </p>

      {(sets ?? []).map((s) => (
        <div key={s.id} className="border border-line rounded-xl p-3 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="font-section text-section text-ink truncate">{s.label}</p>
              <p className={CLS.muted}>
                {s.exam_date ? `Exam ${shortDate(s.exam_date)}` : 'No exam date'}
                {s.next_due ? ` · next look ${shortDate(s.next_due)}` : s.exam_date ? ' · no more looks before the exam' : ''}
              </p>
            </div>
            <button type="button" className={CLS.ghost} onClick={() => remove(s.id)} aria-label={`Remove ${s.label}`}>
              Remove
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {s.topics.map((t) => (
              <span key={t} className="px-2 py-0.5 rounded bg-surface-container font-caption text-caption text-ink">
                {t}
              </span>
            ))}
          </div>
        </div>
      ))}

      <div className="space-y-2">
        <span className={CLS.label}>Add a subject</span>
        <input className={CLS.input} placeholder="Subject, e.g. ADS" value={label} maxLength={60} onChange={(e) => setLabel(e.target.value)} />
        <textarea
          className={CLS.area}
          rows={3}
          placeholder="Topics that will come, separated by commas or new lines"
          value={topics}
          maxLength={2000}
          onChange={(e) => setTopics(e.target.value)}
        />
        <label className="flex items-center justify-between gap-3">
          <span className={CLS.muted}>Exam date (optional)</span>
          <input type="date" className="h-10 px-2 bg-surface border border-line rounded-xl font-small text-small text-ink" value={exam} onChange={(e) => setExam(e.target.value)} />
        </label>
        <button type="button" className={CLS.primary} disabled={busy || !label.trim() || !topics.trim()} onClick={add}>
          Add to radar
        </button>
      </div>
    </div>
  );
};