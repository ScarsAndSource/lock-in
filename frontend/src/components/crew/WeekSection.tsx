import React, { useCallback, useEffect, useState } from 'react';
import { useCrew } from '../../context/CrewContext';
import { errorMessage } from '../../lib/format';
import { SupportCard } from '../SupportCard';
import type { SupportPayload } from '../../types';
import {
  CHEER_TEXT, closeCrewWeek, getCrewCard, getCrewWeek, sendBoost, sendCheer,
  type CardData, type CheerKind, type Crew, type CrewOverview, type WeekInfo,
} from '../../api/crew';
import { Chip, Dots } from './Bits';
import { ForYou } from './ForYou';
import { btn, box, dayLabel, ghost, hint, input } from './ui';

function goalLine(goal: { target_minutes: number; met: boolean | null }, minutes: number | null): string {
  const h = Math.round(goal.target_minutes / 60);
  if (goal.met == null) return `Crew goal ${h}h: needs 2 people sharing hours`;
  if (goal.met) return `Crew goal ${h}h: hit`;
  return minutes != null && minutes >= 0.75 * goal.target_minutes
    ? `Crew goal ${h}h: not quite, close`
    : `Crew goal ${h}h: a lighter week, and that's fine`;
}

/** Closing your week is once per person, not once per crew. It is what opens every crew's card. */
const CloseWeek: React.FC<{
  week: WeekInfo;
  share: CrewOverview['share'];
  onGoYou: () => void;
  onClosed: (support: SupportPayload | null) => void;
}> = ({ week, share, onGoYou, onClosed }) => {
  const { act, busy } = useCrew();
  const [proud, setProud] = useState('');
  const [focus, setFocus] = useState('');
  const [picked, setPicked] = useState<string[]>([]);
  const p = week.preview;
  const nothingShared = !share.days && !share.hours && !share.proud && !share.focus && !share.habits;

  const close = async () => {
    const out: { support: SupportPayload | null } = { support: null };
    const ok = await act(
      async () => {
        const res = await closeCrewWeek({ proud: proud.trim() || null, focus: focus.trim() || null, habits: picked });
        out.support = res.support;
      },
      { ok: "Week closed. Your crews' cards are open.", reload: ['duels'] }, // closing is what scores a duel
    );
    if (ok) onClosed(out.support);
  };

  return (
    <div className={box}>
      <p className="font-small-medium text-small-medium text-ink">Close your week of {dayLabel(week.week_start)}</p>
      <p className="font-caption text-caption text-muted-text leading-relaxed">
        One tap opens the card for every crew you're in. You see theirs only after yours is closed.
      </p>
      <p className="font-caption text-caption text-ink leading-relaxed">
        {share.days
          ? `Your crews will see: ${p.days_showed} of ${p.days_planned} planned days.`
          : 'Days are switched off in your share menu, so they see nothing about your days.'}
        {share.hours ? ' Study hours are added to a crew total.' : ''}
      </p>
      {share.proud && (
        <input className={input} maxLength={120} value={proud} onChange={(e) => setProud(e.target.value)}
          placeholder="One line: what I'm proud of this week (optional)" />
      )}
      {share.focus && (
        <input className={input} maxLength={120} value={focus} onChange={(e) => setFocus(e.target.value)}
          placeholder="One line: my focus for next week (optional)" />
      )}
      {share.habits && p.habit_names.length > 0 && (
        <div className="space-y-1">
          <p className={hint}>Habit names to show (up to 5, optional)</p>
          <div className="flex flex-wrap gap-1.5">
            {p.habit_names.map((h) => {
              const on = picked.includes(h);
              return (
                <button
                  key={h}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setPicked((cur) => (on ? cur.filter((x) => x !== h) : cur.length < 5 ? [...cur, h] : cur))}
                  className={`px-2.5 py-1 rounded-full border font-caption text-caption ${on ? 'bg-ink text-ground-chalk border-ink' : 'border-line text-ink'}`}
                >
                  {h}
                </button>
              );
            })}
          </div>
        </div>
      )}
      <button type="button" disabled={busy} onClick={() => void close()} className={`${btn} w-full`}>
        Close my week
      </button>
      <button type="button" className="font-caption text-caption text-muted-text underline" onClick={onGoYou}>
        {nothingShared ? 'Nothing is shared yet. Change what I share' : 'Change what I share'}
      </button>
    </div>
  );
};

/** Crew Sunday for one crew. No ranks, no order, no "0". */
const CrewCard: React.FC<{ crew: Crew; week: WeekInfo; onGoCrews: () => void }> = ({ crew, week, onGoCrews }) => {
  const { act, busy } = useCrew();
  const [card, setCard] = useState<CardData | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [cheerFor, setCheerFor] = useState<string | null>(null);
  const [cheered, setCheered] = useState<ReadonlySet<string>>(new Set());
  const [boostTo, setBoostTo] = useState('');
  const [boosted, setBoosted] = useState(false);

  const load = useCallback(async () => {
    try {
      setCard(await getCrewCard(crew.id, week.week_start));
      setFailed(null);
    } catch (e) {
      setFailed(errorMessage(e));
    }
  }, [crew.id, week.week_start]);

  useEffect(() => {
    void load();
  }, [load]);

  const others = crew.members.filter((m) => m.status === 'active' && !m.is_me);

  const cheer = async (to: string, kind: CheerKind) => {
    setCheerFor(null);
    const ok = await act(() => sendCheer(crew.id, to, kind), { ok: 'Cheer sent. It lands in their evening batch.' });
    if (ok) setCheered((prev) => new Set(prev).add(to));
  };

  const boost = async () => {
    const ok = await act(() => sendBoost(crew.id, boostTo || null), { ok: 'Sent. They only see that you could use a hello.' });
    if (ok) setBoosted(true);
  };

  if (failed && !card) {
    return (
      <div className={box}>
        <p className="font-small text-small text-ink">{failed}</p>
        <button type="button" className={ghost} onClick={() => void load()}>Try again</button>
      </div>
    );
  }
  if (!card) return <p className="font-caption text-caption text-muted-text py-2">Loading…</p>;
  if (card.locked) {
    return (
      <div className={box}>
        <p className="font-small text-small text-ink">Close your week to open this card.</p>
      </div>
    );
  }

  return (
    <div className={box}>
      <div>
        <p className="font-small-medium text-small-medium text-ink">
          {crew.name} · week of {dayLabel(card.week_start)}
        </p>
        {card.study_minutes != null && (
          <p className="font-caption text-caption text-muted-text">
            Crew studied {Math.round(card.study_minutes / 6) / 10} hours together
          </p>
        )}
        {card.goal && <p className="font-caption text-caption text-muted-text">{goalLine(card.goal, card.study_minutes)}</p>}
        {crew.quiet && <p className="font-caption text-caption text-muted-text">You're quiet here, so your week isn't shown to this crew.</p>}
      </div>

      <ul>
        {card.members.map((m) => (
          <li key={m.username} className="py-2 border-t border-line first:border-t-0 space-y-1">
            <div className="flex items-center justify-between gap-2">
              <span className="font-small-medium text-small-medium text-ink">{m.is_me ? 'You' : `@${m.username}`}</span>
              {m.state === 'shared' && m.days_showed != null && (
                <span className="font-caption text-caption text-muted-text">{m.days_showed} of {m.days_planned} days</span>
              )}
              {m.state === 'resting' && <span className="font-caption text-caption text-muted-text">resting</span>}
            </div>
            {m.state === 'shared' && m.marks != null && <p className="font-small text-small"><Dots marks={m.marks} /></p>}
            {m.proud && <p className="font-caption text-caption text-ink">proud of: {m.proud}</p>}
            {m.focus && <p className="font-caption text-caption text-muted-text">next: {m.focus}</p>}
            {m.habits && m.habits.length > 0 && <p className="font-caption text-caption text-muted-text">{m.habits.join(' · ')}</p>}
            {!m.is_me &&
              (cheered.has(m.username) ? (
                <p className="font-caption text-caption text-muted-text">Cheer sent</p>
              ) : cheerFor === m.username ? (
                <div className="space-y-1 pt-1">
                  <div className="flex flex-wrap gap-1.5">
                    {(Object.keys(CHEER_TEXT) as CheerKind[]).map((k) => (
                      <button key={k} type="button" disabled={busy} className={ghost} onClick={() => void cheer(m.username, k)}>
                        {CHEER_TEXT[k]}
                      </button>
                    ))}
                  </div>
                  <p className={hint}>One cheer per person per day. It arrives in their evening batch.</p>
                </div>
              ) : (
                <button type="button" className={ghost} onClick={() => setCheerFor(m.username)}>Send a cheer</button>
              ))}
          </li>
        ))}
      </ul>

      {others.length === 0 && (
        <div className="pt-2 border-t border-line space-y-1.5">
          <p className="font-caption text-caption text-muted-text">Just you so far. A crew works with 3 to 6.</p>
          <button type="button" className={ghost} onClick={onGoCrews}>Invite someone</button>
        </div>
      )}

      {others.length > 0 && (
        <div className="pt-2 border-t border-line space-y-1.5">
          <p className="font-caption text-caption text-muted-text leading-relaxed">
            Not your best stretch? One tap tells them only that you could use a hello. Nothing else leaves the app.
          </p>
          {boosted ? (
            <p className="font-caption text-caption text-muted-text">Sent.</p>
          ) : (
            <div className="flex gap-2">
              <select className={`${input} flex-1`} value={boostTo} onChange={(e) => setBoostTo(e.target.value)} aria-label="Who to ask">
                <option value="">Whole crew</option>
                {others.map((m) => <option key={m.username} value={m.username}>@{m.username}</option>)}
              </select>
              <button type="button" disabled={busy} onClick={() => void boost()} className={btn}>
                I could use a boost
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export const WeekSection: React.FC<{
  fresh: ReadonlySet<string>;
  onGoCrews: () => void;
  onGoYou: () => void;
}> = ({ fresh, onGoCrews, onGoYou }) => {
  const { overview } = useCrew();
  const crews = overview?.crews ?? [];
  const hasCrews = crews.length > 0;
  const [week, setWeek] = useState<WeekInfo | null>(null);
  const [weekError, setWeekError] = useState<string | null>(null);
  const [support, setSupport] = useState<SupportPayload | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const crew = crews.find((c) => c.id === selected) ?? crews[0];

  const loadWeek = useCallback(async () => {
    try {
      setWeek(await getCrewWeek());
      setWeekError(null);
    } catch (e) {
      setWeekError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    if (hasCrews) void loadWeek();
  }, [hasCrews, loadWeek]);

  return (
    <div className="space-y-4">
      <ForYou fresh={fresh} />
      {support && <SupportCard support={support} />}

      {!hasCrews && (
        <div className={box}>
          <p className="font-small-medium text-small-medium text-ink">No crew yet</p>
          <p className="font-caption text-caption text-muted-text leading-relaxed">
            Start one or join with a code. Small groups of 3 to 6, no rankings, no feed, no one can see a missed day.
          </p>
          <button type="button" className={`${btn} w-full`} onClick={onGoCrews}>Start or join a crew</button>
        </div>
      )}

      {hasCrews && !week && weekError && (
        <div className={box}>
          <p className="font-small text-small text-ink">{weekError}</p>
          <button type="button" className={ghost} onClick={() => void loadWeek()}>Try again</button>
        </div>
      )}
      {hasCrews && !week && !weekError && <p className="font-caption text-caption text-muted-text py-2">Loading…</p>}

      {hasCrews && week && !week.closed && overview && (
        <CloseWeek
          week={week}
          share={overview.share}
          onGoYou={onGoYou}
          onClosed={(s) => {
            setSupport(s);
            void loadWeek();
          }}
        />
      )}

      {hasCrews && week && week.closed && crew && (
        <div className="space-y-2">
          {crews.length > 1 && (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Crew">
              {crews.map((c) => (
                <Chip key={c.id} on={c.id === crew.id} onClick={() => setSelected(c.id)}>{c.name}</Chip>
              ))}
            </div>
          )}
          <CrewCard key={crew.id} crew={crew} week={week} onGoCrews={onGoCrews} />
        </div>
      )}
    </div>
  );
};
