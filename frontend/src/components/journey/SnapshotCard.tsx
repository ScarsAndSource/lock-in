import React, { useCallback, useEffect, useState } from 'react';
import { useApp } from '../../context/AppContext';
import { getSnapshot, submitSnapshot } from '../../api/journey';
import type { SnapshotScores, SnapshotView } from '../../api/journey';
import { errorMessage } from '../../lib/format';
import { SupportCard } from '../SupportCard';
import { CLS } from '../growth/ui';

const QUESTIONS: { key: keyof SnapshotScores; q: string }[] = [
  { key: 'wellbeing', q: 'How are you doing overall?' },
  { key: 'sleep', q: 'How has your sleep been?' },
  { key: 'focus', q: 'How has your focus been?' },
  { key: 'becoming', q: 'How much am I who I want to be?' },
  { key: 'automatic', q: 'How automatic do your habits feel?' },
];

const signed = (n: number) => (n > 0 ? `+${n}` : String(n));

/** Monthly life snapshot: six quick questions and your 30/60/90 day change. A check-in, not a diagnosis. */
export const SnapshotCard: React.FC = () => {
  const { showToast, bumpData } = useApp();
  const [view, setView] = useState<SnapshotView | null>(null);
  const [editing, setEditing] = useState(false);
  const [vals, setVals] = useState<SnapshotScores>({ wellbeing: 5, sleep: 5, focus: 5, becoming: 5, automatic: 5 });
  const [label, setLabel] = useState('');
  const [num, setNum] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    getSnapshot()
      .then(setView)
      .catch(() => setView(null));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!view) return <p className={CLS.muted}>Loading…</p>;

  const submit = async () => {
    setBusy(true);
    try {
      const hasCustom = label.trim() !== '' && num.trim() !== '' && Number.isFinite(Number(num));
      setView(await submitSnapshot({ ...vals, custom_label: hasCustom ? label.trim() : null, custom_value: hasCustom ? Number(num) : null }));
      setEditing(false);
      setLabel('');
      setNum('');
      bumpData();
    } catch (e) {
      showToast(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const showForm = view.due || editing;
  const windows = view.deltas.filter((d) => d.metrics !== null);

  return (
    <div className="space-y-3">
      {view.support && <SupportCard support={view.support} />}

      {showForm ? (
        <div className="space-y-3">
          <p className={CLS.muted}>Six quick questions, 0 to 10. This is a check-in, not a diagnosis.</p>
          {QUESTIONS.map(({ key, q }) => (
            <label key={key} className="block space-y-1">
              <span className="flex items-center justify-between font-small-medium text-small-medium text-ink">
                {q}
                <span className="font-caption text-caption text-muted-text">{vals[key]}</span>
              </span>
              <input
                type="range" min={0} max={10} step={1} value={vals[key]} className="w-full accent-black"
                onChange={(e) => setVals((cur) => ({ ...cur, [key]: Number(e.target.value) }))}
              />
            </label>
          ))}
          <div className="space-y-1">
            <span className="font-small-medium text-small-medium text-ink">One real number you care about</span>
            <div className="flex gap-2">
              <input className={CLS.input} placeholder="e.g. CGPA, weight, income" value={label} maxLength={40} onChange={(e) => setLabel(e.target.value)} />
              <input className={`${CLS.input} max-w-[110px]`} inputMode="decimal" placeholder="number" value={num} onChange={(e) => setNum(e.target.value)} />
            </div>
          </div>
          <div className="flex gap-2">
            <button type="button" className={CLS.primary} disabled={busy} onClick={submit}>
              Save snapshot
            </button>
            {editing && (
              <button type="button" className={CLS.ghost} onClick={() => setEditing(false)}>
                Cancel
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          {view.latest && <p className={CLS.muted}>Last snapshot: {new Date(`${view.latest.taken_on}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}. Next one in about a month.</p>}
          {windows.length === 0 ? (
            <p className={CLS.muted}>Your 30, 60 and 90 day change shows up here once you have a second snapshot.</p>
          ) : (
            windows.map((w) => (
              <div key={w.days} className="border border-line rounded-xl p-3 space-y-1">
                <span className={CLS.label}>{w.days} days</span>
                <p className="font-small text-small text-ink">
                  {QUESTIONS.map(({ key }) => `${key} ${signed(w.metrics ? w.metrics[key] : 0)}`).join(' · ')}
                </p>
                {w.custom && (
                  <p className="font-small-medium text-small-medium text-ink">
                    {w.custom.label}: {w.custom.from} to {w.custom.to} ({signed(w.custom.change)})
                  </p>
                )}
              </div>
            ))
          )}
          <button type="button" className={CLS.ghost} onClick={() => setEditing(true)}>
            Redo it now
          </button>
        </div>
      )}
    </div>
  );
};