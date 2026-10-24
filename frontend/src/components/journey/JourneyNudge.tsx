import React, { useCallback, useEffect, useState } from 'react';
import { useApp } from '../../context/AppContext';
import {
  doneReview, getDueRecall, getNudge, graduateHabit, offerSnoozed, shelfCheck, snoozeOffer,
} from '../../api/journey';
import type { JourneyNudgeData, RecallDue } from '../../api/journey';
import { MIRROR_SECTION_KEY } from '../../api/growth';
import { errorMessage } from '../../lib/format';
import { CLS } from '../growth/ui';

/** The one journey ask on Now: today's exam-topic look, else a shelf check-in, else the monthly snapshot, else a graduation offer. */
export const JourneyNudge: React.FC = () => {
  const { demoMode, dataEpoch, setActiveTab, bumpData, showToast } = useApp();
  const [nudge, setNudge] = useState<JourneyNudgeData | null>(null);
  const [due, setDue] = useState<RecallDue[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const n = await getNudge();
      setNudge(n);
      setDue(n && n.kind === 'recall' ? await getDueRecall() : []);
    } catch {
      setNudge(null);
      setDue([]);
    }
  }, []);

  useEffect(() => {
    if (demoMode) return;
    load();
  }, [demoMode, dataEpoch, load]);

  if (demoMode || !nudge) return null;
  if (nudge.kind === 'graduate' && offerSnoozed(nudge.habit_id)) return null;

  const act = async (fn: () => Promise<unknown>, message?: string) => {
    setBusy(true);
    try {
      await fn();
      if (message) showToast(message);
      setNudge(null);
      bumpData();
    } catch (e) {
      showToast(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const openJourney = () => {
    try {
      sessionStorage.setItem(MIRROR_SECTION_KEY, 'journey');
    } catch {
      /* the Journey tab is still one tap away */
    }
    setActiveTab('mirror');
  };

  return (
    <section className="w-full bg-surface rounded-xl px-4 py-3 border border-line space-y-2">
      {nudge.kind === 'recall' &&
        due.map((d) => (
          <div key={d.review_id} className="space-y-2">
            <p className="font-small-medium text-small-medium text-ink">
              Quick look: {d.label}
              {d.days_to_exam !== null ? ` · exam in ${d.days_to_exam} days` : ''}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {d.topics.map((t) => (
                <span key={t} className="px-2 py-0.5 rounded bg-surface-container font-caption text-caption text-ink">
                  {t}
                </span>
              ))}
            </div>
            <button type="button" className={`${CLS.primary} h-9 px-4 text-small`} disabled={busy} onClick={() => act(() => doneReview(d.review_id, null))}>
              Seen them
            </button>
          </div>
        ))}

      {nudge.kind === 'shelf_check' && (
        <div className="space-y-2">
          <p className="font-small-medium text-small-medium text-ink">
            “{nudge.habit_name}” has been on your shelf. Still holding?
          </p>
          <div className="flex gap-2">
            <button type="button" className={`${CLS.primary} h-9 px-4 text-small`} disabled={busy} onClick={() => act(() => shelfCheck(nudge.graduation_id, true), 'Still holding. That’s the proof.')}>
              Still holding
            </button>
            <button type="button" className={CLS.ghost} disabled={busy} onClick={() => act(() => shelfCheck(nudge.graduation_id, false), 'Okay. You can bring it back from the shelf.')}>
              Slipping
            </button>
          </div>
        </div>
      )}

      {nudge.kind === 'snapshot' && (
        <div className="space-y-2">
          <p className="font-small-medium text-small-medium text-ink">Monthly check: six quick questions on how things are going.</p>
          <button type="button" className={`${CLS.primary} h-9 px-4 text-small`} onClick={openJourney}>
            Open it
          </button>
        </div>
      )}

      {nudge.kind === 'graduate' && (
        <div className="space-y-2">
          <p className="font-small-medium text-small-medium text-ink">“{nudge.name}” looks automatic now. Retire it to your shelf?</p>
          <div className="flex gap-2">
            <button type="button" className={`${CLS.primary} h-9 px-4 text-small`} disabled={busy} onClick={() => act(() => graduateHabit(nudge.habit_id), 'On your Done Becoming shelf.')}>
              Move to shelf
            </button>
            <button
              type="button" className={CLS.ghost}
              onClick={() => {
                snoozeOffer(nudge.habit_id);
                setNudge(null);
              }}
            >
              Not yet
            </button>
          </div>
        </div>
      )}
    </section>
  );
};
