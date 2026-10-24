import React, { useCallback, useEffect, useState } from 'react';
import { useApp } from '../../context/AppContext';
import { errorMessage } from '../../lib/format';
import { SupportCard } from '../SupportCard';
import type { SupportPayload } from '../../types';
import {
  CHEER_TEXT, closeCrewWeek, getCrewCard, getCrewWeek, sendBoost, sendCheer,
  type CardData, type CheerKind, type Crew, type ShareKey, type WeekInfo,
} from '../../api/crew';

const input = 'w-full bg-surface-container-low border border-line rounded-lg px-3 py-2 font-small text-ink';
const btn = 'h-9 px-3 rounded-lg bg-ink text-ground-chalk font-caption text-caption font-semibold disabled:opacity-40';
const ghost = 'h-8 px-2.5 rounded-lg bg-surface-container text-ink font-caption text-caption disabled:opacity-40';

function label(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

const Dots: React.FC<{ marks: number }> = ({ marks }) => (
  <span className="tracking-[0.35em] text-ink select-none" aria-hidden="true">
    {Array.from({ length: 7 }, (_, i) => ((marks >> i) & 1 ? '●' : '·')).join('')}
  </span>
);

interface Props {
  crew: Crew;
  share: Partial<Record<ShareKey, boolean>>;
}

/** Crew Sunday: close your own week first, then the crew's card opens. No ranks, no order, no "0". */
export const CrewCardView: React.FC<Props> = ({ crew, share }) => {
  const { showToast } = useApp();
  const [week, setWeek] = useState<WeekInfo | null>(null);
  const [card, setCard] = useState<CardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [proud, setProud] = useState('');
  const [focus, setFocus] = useState('');
  const [picked, setPicked] = useState<string[]>([]);
  const [support, setSupport] = useState<SupportPayload | null>(null);
  const [cheerFor, setCheerFor] = useState<string | null>(null);
  const [boostTo, setBoostTo] = useState('');

  const load = useCallback(async () => {
    try {
      const w = await getCrewWeek();
      setWeek(w);
      setCard(w.closed ? await getCrewCard(crew.id, w.week_start) : null);
    } catch (e) {
      showToast(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [crew.id, showToast]);

  useEffect(() => {
    void load();
  }, [load]);

  const close = async () => {
    setBusy(true);
    try {
      const res = await closeCrewWeek({ proud: proud.trim() || null, focus: focus.trim() || null, habits: picked });
      if (res.support) setSupport(res.support);
      await load();
    } catch (e) {
      showToast(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const cheer = async (to: string, kind: CheerKind) => {
    setCheerFor(null);
    try {
      await sendCheer(crew.id, to, kind);
      showToast('Cheer sent. It lands in their evening batch.');
    } catch (e) {
      showToast(errorMessage(e));
    }
  };

  const boost = async () => {
    setBusy(true);
    try {
      await sendBoost(crew.id, boostTo || null);
      showToast('Sent. They only see that you could use a hello.');
    } catch (e) {
      showToast(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <p className="font-caption text-caption text-muted-text py-2">Loading…</p>;
  if (!week) return null;

  const others = crew.members.filter((m) => m.status === 'active' && !m.is_me);
  const p = week.preview;

  return (
    <div className="space-y-3 pt-2">
      {support && <SupportCard support={support} />}

      {!week.closed && (
        <div className="space-y-2.5">
          <p className="font-small text-small text-ink">
            Close your week of {label(week.week_start)} to open the crew's card.
          </p>
          <p className="font-caption text-caption text-muted-text leading-relaxed">
            {share.days
              ? `Your crew will see: ${p.days_showed} of ${p.days_planned} planned days.`
              : 'Your share menu is off for days, so they see nothing about your days.'}
            {share.hours ? ` Study hours are added to a crew total.` : ''}
          </p>
          {share.proud && (
            <input className={input} maxLength={120} value={proud} onChange={(e) => setProud(e.target.value)}
              placeholder="One line: what I'm proud of this week" />
          )}
          {share.focus && (
            <input className={input} maxLength={120} value={focus} onChange={(e) => setFocus(e.target.value)}
              placeholder="One line: my focus for next week" />
          )}
          {share.habits && p.habit_names.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {p.habit_names.map((h) => {
                const on = picked.includes(h);
                return (
                  <button key={h} type="button" aria-pressed={on}
                    onClick={() => setPicked((cur) => (on ? cur.filter((x) => x !== h) : cur.length < 5 ? [...cur, h] : cur))}
                    className={`px-2.5 py-1 rounded-full border font-caption text-caption ${on ? 'bg-ink text-ground-chalk border-ink' : 'border-line text-ink'}`}>
                    {h}
                  </button>
                );
              })}
            </div>
          )}
          <button type="button" disabled={busy} onClick={() => void close()} className={`${btn} w-full`}>
            Close my week
          </button>
        </div>
      )}

      {card && !card.locked && (
        <div className="space-y-2">
          <div>
            <p className="font-small-medium text-small-medium text-ink">
              Crew Sunday · week of {label(card.week_start)}
            </p>
            {card.study_minutes != null && (
              <p className="font-caption text-caption text-muted-text">
                Crew studied {Math.round(card.study_minutes / 6) / 10} hours together
              </p>
            )}
            {card.goal && (
              <p className="font-caption text-caption text-muted-text">
                {card.goal.met == null
                  ? `Crew goal ${Math.round(card.goal.target_minutes / 60)}h: needs 2 people sharing hours`
                  : card.goal.met
                    ? `Crew goal ${Math.round(card.goal.target_minutes / 60)}h: hit`
                    : (card.study_minutes ?? 0) >= 0.75 * card.goal.target_minutes
                      ? `Crew goal ${Math.round(card.goal.target_minutes / 60)}h: not quite, close`
                      : `Crew goal ${Math.round(card.goal.target_minutes / 60)}h: a lighter week, and that's fine`}
              </p>
            )}
          </div>
          <ul>
            {card.members.map((m) => (
              <li key={m.username} className="py-2 border-t border-line first:border-t-0 space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-small-medium text-small-medium text-ink">{m.is_me ? 'You' : `@${m.username}`}</span>
                  {m.state === 'shared' && m.days_showed != null && (
                    <span className="font-caption text-caption text-muted-text">
                      {m.days_showed} of {m.days_planned} days
                    </span>
                  )}
                  {m.state === 'resting' && <span className="font-caption text-caption text-muted-text">resting</span>}
                </div>
                {m.state === 'shared' && m.marks != null && (
                  <p className="font-small text-small"><Dots marks={m.marks} /></p>
                )}
                {m.proud && <p className="font-caption text-caption text-ink">proud of: {m.proud}</p>}
                {m.focus && <p className="font-caption text-caption text-muted-text">next: {m.focus}</p>}
                {m.habits && m.habits.length > 0 && (
                  <p className="font-caption text-caption text-muted-text">{m.habits.join(' · ')}</p>
                )}
                {!m.is_me && (
                  cheerFor === m.username ? (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {(Object.keys(CHEER_TEXT) as CheerKind[]).map((k) => (
                        <button key={k} type="button" className={ghost} onClick={() => void cheer(m.username, k)}>
                          {CHEER_TEXT[k]}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <button type="button" className={ghost} onClick={() => setCheerFor(m.username)}>Send a cheer</button>
                  )
                )}
              </li>
            ))}
          </ul>

          {others.length > 0 && (
            <div className="pt-2 border-t border-line space-y-1.5">
              <p className="font-caption text-caption text-muted-text leading-relaxed">
                Not your best stretch? One tap tells them only that you could use a hello. Nothing else leaves the app.
              </p>
              <div className="flex gap-2">
                <select className={`${input} flex-1`} value={boostTo} onChange={(e) => setBoostTo(e.target.value)}
                  aria-label="Who to ask">
                  <option value="">Whole crew</option>
                  {others.map((m) => <option key={m.username} value={m.username}>@{m.username}</option>)}
                </select>
                <button type="button" disabled={busy} onClick={() => void boost()} className={btn}>
                  I could use a boost
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
