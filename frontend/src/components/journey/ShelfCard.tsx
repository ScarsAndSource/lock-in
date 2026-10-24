import React, { useCallback, useEffect, useState } from 'react';
import { useApp } from '../../context/AppContext';
import { graduateHabit, offerSnoozed, reviveHabit, shelfCheck, snoozeOffer, getShelf } from '../../api/journey';
import type { ShelfView } from '../../api/journey';
import { errorMessage } from '../../lib/format';
import { CLS } from '../growth/ui';

/** "Done becoming": habits that became automatic retire here, with a check-in at 30 and 90 days. */
export const ShelfCard: React.FC = () => {
  const { showToast, bumpData } = useApp();
  const [view, setView] = useState<ShelfView | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    getShelf()
      .then(setView)
      .catch(() => setView({ offers: [], shelf: [], checkin: null }));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const run = async (key: string, action: () => Promise<{ message: string }>) => {
    setBusy(key);
    try {
      const res = await action();
      showToast(res.message);
      load();
      bumpData();
    } catch (e) {
      showToast(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  if (!view) return <p className={CLS.muted}>Loading…</p>;
  const offers = view.offers.filter((o) => !offerSnoozed(o.habit_id));

  return (
    <div className="space-y-3">
      <p className={CLS.muted}>
        When a habit runs on its own, retire it here. I check in after 30 and 90 days. Less app, more life.
      </p>

      {offers.map((o) => (
        <div key={o.habit_id} className="border border-line rounded-xl p-3 space-y-2">
          <p className="font-small-medium text-small-medium text-ink">“{o.name}” looks automatic now ({Math.round(o.consistency_pct)}% lately). Retire it?</p>
          <div className="flex gap-2">
            <button type="button" className={CLS.primary} disabled={busy !== null} onClick={() => run(`g${o.habit_id}`, () => graduateHabit(o.habit_id))}>
              Move to shelf
            </button>
            <button
              type="button" className={CLS.ghost}
              onClick={() => {
                snoozeOffer(o.habit_id);
                load();
              }}
            >
              Not yet
            </button>
          </div>
        </div>
      ))}

      {view.shelf.length === 0 ? (
        <p className={CLS.muted}>Nothing on the shelf yet.</p>
      ) : (
        view.shelf.map((s) => (
          <div key={s.id} className="border border-line rounded-xl p-3 space-y-2">
            <div>
              <p className="font-section text-section text-ink">{s.name}</p>
              <p className={CLS.muted}>{s.days_on_shelf} days on the shelf</p>
            </div>
            {s.check_due && (
              <div className="space-y-2">
                <p className="font-small-medium text-small-medium text-ink">{s.check_due}-day check: still holding?</p>
                <div className="flex gap-2">
                  <button type="button" className={CLS.primary} disabled={busy !== null} onClick={() => run(`c${s.id}`, () => shelfCheck(s.id, true))}>
                    Still holding
                  </button>
                  <button type="button" className={CLS.ghost} disabled={busy !== null} onClick={() => run(`c${s.id}`, () => shelfCheck(s.id, false))}>
                    Slipping
                  </button>
                </div>
              </div>
            )}
            <button type="button" className={CLS.ghost} disabled={busy !== null} onClick={() => run(`r${s.id}`, () => reviveHabit(s.id))}>
              Bring it back
            </button>
          </div>
        ))
      )}
    </div>
  );
};