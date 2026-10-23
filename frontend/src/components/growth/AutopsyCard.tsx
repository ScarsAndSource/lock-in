import React, { useState } from 'react';
import { useApp } from '../../context/AppContext';
import { applyAutopsy, deferAutopsy } from '../../api/growth';
import type { AutopsyReason, GrowthAutopsy } from '../../api/growth';
import { errorMessage } from '../../lib/format';
import { CLS } from './ui';

const REASONS: { key: AutopsyReason; title: string; sub: string }[] = [
  { key: 'too_big', title: 'It’s too big', sub: 'More than I can do on a normal day' },
  { key: 'wrong_time', title: 'Wrong time', sub: 'My day has no room for it then' },
  { key: 'wrong_trigger', title: 'Wrong trigger', sub: 'Nothing sets it off, I just forget' },
  { key: 'dont_care', title: 'I don’t really care', sub: 'It stopped being mine' },
];

interface Props {
  autopsy: GrowthAutopsy;
  onDone: () => void;
}

export const AutopsyCard: React.FC<Props> = ({ autopsy, onDone }) => {
  const { showToast } = useApp();
  const [reason, setReason] = useState<AutopsyReason | null>(null);
  const [floor, setFloor] = useState(autopsy.floor_text ?? '');
  const [cue, setCue] = useState('');
  const [busy, setBusy] = useState(false);
  const lowConfidence = autopsy.identity_confidence !== null && autopsy.identity_confidence < 5;

  const run = async (fn: () => Promise<void>, fallback: string) => {
    setBusy(true);
    try {
      await fn();
      onDone();
    } catch (err) {
      showToast(errorMessage(err, fallback));
    } finally {
      setBusy(false);
    }
  };

  const apply = (choice?: 'archive' | 'keep') =>
    run(async () => {
      if (!reason) return;
      const res = await applyAutopsy(autopsy.id, {
        reason,
        floor_text: reason === 'too_big' ? floor : undefined,
        cue: reason === 'wrong_time' || reason === 'wrong_trigger' ? cue : undefined,
        choice,
      });
      showToast(res.message);
    }, 'Could not apply that');

  const defer = (skip: boolean) => run(() => deferAutopsy(autopsy.id, skip), 'Could not do that');

  return (
    <div className="space-y-3">
      <p className="font-small text-small text-ink">
        “{autopsy.habit_name}” landed about {Math.round(autopsy.consistency_pct)}% over the last {autopsy.window_days} days.
        That usually means the habit was designed badly, not that you are. What’s closest?
      </p>

      {!reason ? (
        <div className="space-y-2">
          {REASONS.map((r) => (
            <button
              key={r.key}
              type="button"
              disabled={busy}
              onClick={() => setReason(r.key)}
              className="w-full text-left px-3 py-2.5 bg-surface border border-line rounded-xl hover:bg-surface-container-low transition-colors"
            >
              <span className="font-small-medium text-small-medium text-ink block">{r.title}</span>
              <span className={CLS.muted}>{r.sub}</span>
              {r.key === 'too_big' && lowConfidence && (
                <span className="font-caption text-caption text-ink block mt-0.5">
                  You rated your confidence {autopsy.identity_confidence}/10, so smaller often wins.
                </span>
              )}
            </button>
          ))}
          <div className="flex gap-2 pt-1">
            <button type="button" className={CLS.ghost} disabled={busy} onClick={() => void defer(false)}>
              Later
            </button>
            <button type="button" className={CLS.ghost} disabled={busy} onClick={() => void defer(true)}>
              Skip for a month
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {reason === 'too_big' && (
            <>
              <label className="block space-y-1.5">
                <span className="font-body-strong text-body-strong text-ink">What’s the tiny version?</span>
                <input className={CLS.input} value={floor} maxLength={120} onChange={(e) => setFloor(e.target.value)} placeholder="e.g. put on my gym shoes" autoFocus />
              </label>
              {autopsy.lighter_label && (
                <p className={CLS.muted}>
                  I’ll also ease the target from {autopsy.current_label} to {autopsy.lighter_label}.
                </p>
              )}
            </>
          )}
          {(reason === 'wrong_time' || reason === 'wrong_trigger') && (
            <label className="block space-y-1.5">
              <span className="font-body-strong text-body-strong text-ink">
                {reason === 'wrong_time' ? 'When will it actually fit?' : 'What do you do right before it?'}
              </span>
              <input
                className={CLS.input}
                value={cue}
                maxLength={200}
                onChange={(e) => setCue(e.target.value)}
                placeholder={reason === 'wrong_time' ? 'e.g. 7:30 am, right after lunch' : 'e.g. after I brush my teeth'}
                autoFocus
              />
            </label>
          )}
          {reason === 'dont_care' && (
            <p className="font-small text-small text-ink">
              {autopsy.identity_sentence
                ? `You wrote: “${autopsy.identity_sentence}”. Does this habit still serve that?`
                : 'Habits you don’t care about cost energy. Letting one go is a real choice.'}
            </p>
          )}

          <div className="flex items-center gap-2">
            <button type="button" className={CLS.ghost} disabled={busy} onClick={() => setReason(null)}>
              Back
            </button>
            {reason === 'dont_care' ? (
              <>
                <button type="button" className={CLS.ghost} disabled={busy} onClick={() => void apply('keep')}>
                  Keep it
                </button>
                <button type="button" className={`${CLS.primary} flex-1`} disabled={busy} onClick={() => void apply('archive')}>
                  Let it go
                </button>
              </>
            ) : (
              <button
                type="button"
                className={`${CLS.primary} flex-1`}
                disabled={busy || (reason === 'too_big' ? !floor.trim() : !cue.trim())}
                onClick={() => void apply()}
              >
                {busy ? 'Applying…' : 'Apply fix'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
