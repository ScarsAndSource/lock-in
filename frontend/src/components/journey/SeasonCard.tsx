import React, { useEffect, useState } from 'react';
import { useApp } from '../../context/AppContext';
import { getHabits } from '../../api/habits';
import { startSeason } from '../../api/journey';
import type { JourneyState } from '../../api/journey';
import { errorMessage } from '../../lib/format';
import type { Habit } from '../../types';
import { CLS } from '../growth/ui';

function phaseLine(state: JourneyState): string {
  const s = state.season;
  if (!s) return `No Season yet. All ${state.focus_ids.length} of your habits count as focus.`;
  if (s.phase === 'focus') return `Week ${s.week} of 6 · ${s.days_left} days until your easy week`;
  if (s.phase === 'rest') return `Easy week · ${s.days_left} days left. Just the check-in.`;
  return 'This Season is done. Pick what you focus on next.';
}

/** Seasons: 6 weeks, at most 3 focus habits, then an easy week. Benched habits stay loggable, just quiet. */
export const SeasonCard: React.FC<{ state: JourneyState | null }> = ({ state }) => {
  const { bumpData, showToast } = useApp();
  const [habits, setHabits] = useState<Habit[]>([]);
  const [picking, setPicking] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getHabits()
      .then(setHabits)
      .catch(() => setHabits([]));
  }, []);

  if (!state) return <p className={CLS.muted}>Loading…</p>;

  const names = new Map(habits.map((h) => [h.id, h.name]));
  const toggle = (id: string) =>
    setPicked((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : cur.length >= 3 ? cur : [...cur, id]));

  const begin = () => {
    setPicked(state.focus_ids.slice(0, 3));
    setPicking(true);
  };

  const submit = async () => {
    setBusy(true);
    try {
      await startSeason(name.trim() || null, picked);
      showToast('New Season started');
      setPicking(false);
      setName('');
      bumpData();
    } catch (e) {
      showToast(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <div>
        {state.season && <p className="font-section text-section text-ink">{state.season.name}</p>}
        <p className={CLS.muted}>{phaseLine(state)}</p>
      </div>

      <div className="space-y-1">
        <span className={CLS.label}>
          Focus · {state.focus_ids.length}/{state.slots}
        </span>
        {state.focus_ids.length === 0 ? (
          <p className={CLS.muted}>Nothing yet. Add a habit and it takes a slot.</p>
        ) : (
          <ul className="font-small-medium text-small-medium text-ink space-y-0.5">
            {state.focus_ids.map((id) => (
              <li key={id}>{names.get(id) ?? 'Habit'}</li>
            ))}
          </ul>
        )}
        {state.benched_ids.length > 0 && (
          <p className={CLS.muted}>{state.benched_ids.length} benched: still loggable, just quiet.</p>
        )}
      </div>

      {!picking ? (
        <button type="button" className={CLS.ghost} onClick={begin}>
          {state.season ? 'Start next Season' : 'Start a Season'}
        </button>
      ) : (
        <div className="space-y-2">
          <input
            className={CLS.input}
            placeholder="Name it (optional), e.g. Exam Arc"
            value={name}
            maxLength={60}
            onChange={(e) => setName(e.target.value)}
          />
          <span className={CLS.label}>Pick up to 3 focus habits</span>
          {habits.map((h) => (
            <label key={h.id} className="flex items-center gap-3 py-1">
              <input
                type="checkbox"
                className="w-5 h-5 accent-black"
                checked={picked.includes(h.id)}
                disabled={!picked.includes(h.id) && picked.length >= 3}
                onChange={() => toggle(h.id)}
              />
              <span className="font-small text-small text-ink">{h.name}</span>
            </label>
          ))}
          <p className={CLS.muted}>The rest get benched for this Season. Nothing is deleted.</p>
          <div className="flex gap-2">
            <button type="button" className={CLS.primary} disabled={busy || (habits.length > 0 && picked.length === 0)} onClick={submit}>
              Start
            </button>
            <button type="button" className={CLS.ghost} onClick={() => setPicking(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
