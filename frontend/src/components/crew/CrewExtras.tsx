import React, { useCallback, useEffect, useState } from 'react';
import { useApp } from '../../context/AppContext';
import { errorMessage } from '../../lib/format';
import { SupportCard } from '../SupportCard';
import type { SupportPayload } from '../../types';
import {
  cancelBuddy, cancelDuel, getBuddies, getCrewGoal, getDuels, holdBuddy, proposeBuddy, proposeDuel, respondBuddy,
  respondDuel, sendBuddyMessage, setCrewGoal,
  type BuddyOverview, type Crew, type Duel, type GoalInfo,
} from '../../api/crew';

const input = 'w-full bg-surface-container-low border border-line rounded-lg px-3 py-2 font-small text-ink';
const btn = 'h-9 px-3 rounded-lg bg-ink text-ground-chalk font-caption text-caption font-semibold disabled:opacity-40 shrink-0';
const ghost = 'h-8 px-2.5 rounded-lg bg-surface-container text-ink font-caption text-caption disabled:opacity-40';
const head = 'font-caption text-[11px] text-muted-text uppercase tracking-wider';
const DEFAULT_MSG = "Hey, I've gone quiet. Could you check in on me?";

const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
const pts = (v: number) => `${v > 0 ? '+' : ''}${v} pts`;

const DuelResult: React.FC<{ d: Duel }> = ({ d }) => {
  if (!d.result) return null;
  const { mine, theirs } = d.result;
  const both = mine.delta_pct >= 0 && theirs.delta_pct >= 0;
  const gap = mine.delta_pct - theirs.delta_pct;
  return (
    <div className="space-y-0.5">
      <p className="font-small-medium text-small-medium text-ink">
        {both ? 'You both grew.' : 'A tough week for the numbers. You still showed up for the duel.'}
      </p>
      <p className="font-caption text-caption text-muted-text">
        You {pts(mine.delta_pct)} vs your usual · @{d.other} {pts(theirs.delta_pct)} vs theirs
      </p>
      {both && Math.abs(gap) >= 5 && (
        <p className="font-caption text-caption text-muted-text">Biggest jump: {gap > 0 ? 'you' : `@${d.other}`}</p>
      )}
    </div>
  );
};

/** Goal, buddy deal and duels for ONE crew. Everything is two-sided consent; declining and ignoring are silent. */
export const CrewExtras: React.FC<{ crew: Crew }> = ({ crew }) => {
  const { showToast } = useApp();
  const [goal, setGoal] = useState<GoalInfo | null>(null);
  const [buddies, setBuddies] = useState<BuddyOverview | null>(null);
  const [duels, setDuels] = useState<Duel[]>([]);
  const [busy, setBusy] = useState(false);
  const [support, setSupport] = useState<SupportPayload | null>(null);
  const [hours, setHours] = useState('');
  const [to, setTo] = useState('');
  const [threshold, setThreshold] = useState(3);
  const [message, setMessage] = useState(DEFAULT_MSG);
  const [auto, setAuto] = useState(false);
  const [duelTo, setDuelTo] = useState('');

  const mates = crew.members.filter((m) => m.status === 'active' && !m.is_me);

  const load = useCallback(async () => {
    try {
      const [g, b, d] = await Promise.all([getCrewGoal(crew.id), getBuddies(), getDuels()]);
      setGoal(g);
      setBuddies(b);
      setDuels(d.duels.filter((x) => x.crew_id === crew.id));
    } catch (e) {
      showToast(errorMessage(e));
    }
  }, [crew.id, showToast]);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true);
    try {
      await fn();
      if (ok) showToast(ok);
      await load();
    } catch (e) {
      showToast(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const propose = async () => {
    setBusy(true);
    try {
      const res = await proposeBuddy({ crew_id: crew.id, to, threshold, message, auto_send: auto });
      if (res.support) setSupport(res.support);
      else showToast('Deal proposed. They have to accept.');
      await load();
    } catch (e) {
      showToast(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const deals = (buddies?.deals ?? []).filter((d) => d.crew_id === crew.id);
  const messages = (buddies?.messages ?? []).filter((m) => m.crew_id === crew.id);
  const mine = deals.filter((d) => d.role === 'owner');

  return (
    <div className="space-y-4 pt-3 border-t border-line">
      {support && <SupportCard support={support} />}

      {/* goal */}
      <div className="space-y-1.5">
        <span className={head}>Crew goal{goal ? `, week of ${day(goal.week_start)}` : ''}</span>
        {goal?.target_minutes ? (
          <p className="font-small text-small text-ink">
            {Math.round(goal.target_minutes / 60)} hours of study, together. Everyone's part adds up.
          </p>
        ) : (
          <p className="font-caption text-caption text-muted-text">No goal set for that week.</p>
        )}
        {crew.role === 'owner' && (
          <div className="flex gap-2">
            <input className={input} inputMode="numeric" value={hours} maxLength={3} placeholder="Hours, e.g. 40"
              onChange={(e) => setHours(e.target.value.replace(/\D/g, ''))} />
            <button type="button" className={btn} disabled={busy || !hours}
              onClick={() => void act(() => setCrewGoal(crew.id, Number(hours)), 'Goal set').then(() => setHours(''))}>
              Set
            </button>
            {goal?.target_minutes ? (
              <button type="button" className={ghost} disabled={busy}
                onClick={() => void act(() => setCrewGoal(crew.id, null), 'Goal cleared')}>Clear</button>
            ) : null}
          </div>
        )}
        <p className="font-caption text-[11px] text-muted-text">
          Counts only hours people chose to share, capped per person, and only shown once 2 people share.
        </p>
      </div>

      {/* buddy deals */}
      <div className="space-y-2">
        <span className={head}>Buddy deal</span>
        {messages.map((m) => (
          <p key={m.id} className={`font-small text-small ${m.seen ? 'text-muted-text' : 'text-ink'}`}>
            @{m.from_username}: {m.body}
          </p>
        ))}
        {deals.map((d) => (
          <div key={d.id} className="rounded-lg border border-line p-2.5 space-y-1.5">
            {d.role === 'owner' && d.status === 'pending' && (
              <p className="font-small text-small text-ink">Waiting for @{d.other} to accept.</p>
            )}
            {d.role === 'buddy' && d.status === 'pending' && (
              <p className="font-small text-small text-ink">
                @{d.other} wants you as a buddy. If they go quiet for {d.threshold} planned days, they may send you:
                <span className="block text-muted-text">"{d.message}"</span>
              </p>
            )}
            {d.status === 'active' && d.role === 'buddy' && (
              <p className="font-small text-small text-ink">You're @{d.other}'s buddy.</p>
            )}
            {d.status === 'active' && d.role === 'owner' && (
              <>
                <p className="font-small text-small text-ink">
                  Buddy: @{d.other}. After {d.threshold} quiet planned days you decide whether to send:
                  <span className="block text-muted-text">"{d.message}"</span>
                  {d.auto_send && <span className="block text-muted-text">Auto-send is on.</span>}
                </p>
                {d.due && (
                  <div className="space-y-1.5 bg-surface-container rounded-lg p-2">
                    <p className="font-small text-small text-ink">
                      It's been {d.misses} quiet planned days. Send your promised message to @{d.other}?
                    </p>
                    <div className="flex gap-1.5">
                      <button type="button" className={btn} disabled={busy}
                        onClick={() => void act(() => sendBuddyMessage(d.id), 'Sent')}>Send it</button>
                      <button type="button" className={ghost} disabled={busy}
                        onClick={() => void act(() => holdBuddy(d.id), 'Okay, not now')}>Not now</button>
                    </div>
                  </div>
                )}
              </>
            )}
            <div className="flex gap-1.5">
              {d.role === 'buddy' && d.status === 'pending' && (
                <>
                  <button type="button" className={ghost} disabled={busy}
                    onClick={() => void act(() => respondBuddy(d.id, true), 'You\'re their buddy')}>Accept</button>
                  <button type="button" className={ghost} disabled={busy}
                    onClick={() => void act(() => respondBuddy(d.id, false))}>Decline</button>
                </>
              )}
              {(d.status === 'active' || d.role === 'owner') && (
                <button type="button" className={ghost} disabled={busy}
                  onClick={() => void act(() => cancelBuddy(d.id), 'Deal cancelled')}>
                  {d.role === 'buddy' ? 'Leave deal' : 'Cancel deal'}
                </button>
              )}
            </div>
          </div>
        ))}
        {mine.length < 2 && mates.length > 0 && (
          <div className="space-y-1.5">
            <p className="font-caption text-[11px] text-muted-text leading-relaxed">
              Pick a crewmate. If you go quiet, the app asks YOU whether to send them your message. Nothing is sent
              unless you tap, or you turn on auto-send.
            </p>
            <div className="flex gap-2">
              <select className={`${input} flex-1`} value={to} onChange={(e) => setTo(e.target.value)} aria-label="Buddy">
                <option value="">Choose a buddy</option>
                {mates.map((m) => <option key={m.username} value={m.username}>@{m.username}</option>)}
              </select>
              <select className={`${input} w-24`} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))}
                aria-label="Quiet days">
                {[2, 3, 4, 5, 6, 7].map((n) => <option key={n} value={n}>{n} days</option>)}
              </select>
            </div>
            <input className={input} maxLength={140} value={message} onChange={(e) => setMessage(e.target.value)} />
            <label className="flex items-center gap-2 font-caption text-caption text-ink">
              <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
              Auto-send without asking me (off by default)
            </label>
            <button type="button" className={`${btn} w-full`} disabled={busy || !to || !message.trim()}
              onClick={() => void propose()}>Propose deal</button>
          </div>
        )}
      </div>

      {/* duels */}
      <div className="space-y-2">
        <span className={head}>Handicapped duel</span>
        {duels.map((d) => (
          <div key={d.id} className="rounded-lg border border-line p-2.5 space-y-1.5">
            <p className="font-small text-small text-ink">
              {d.status === 'pending' && d.role === 'challenger' && `Waiting for @${d.other} · week of ${day(d.week_start)}`}
              {d.status === 'pending' && d.role === 'opponent' && `@${d.other} invited you to a duel · week of ${day(d.week_start)}`}
              {d.status === 'active' && !d.result && `Duel with @${d.other} · week of ${day(d.week_start)}. Results appear once you both close your week.`}
              {d.status === 'active' && d.result && `Duel with @${d.other} · week of ${day(d.week_start)}`}
            </p>
            <DuelResult d={d} />
            <div className="flex gap-1.5">
              {d.status === 'pending' && d.role === 'opponent' && (
                <>
                  <button type="button" className={ghost} disabled={busy}
                    onClick={() => void act(() => respondDuel(d.id, true), 'Duel on')}>Accept</button>
                  <button type="button" className={ghost} disabled={busy}
                    onClick={() => void act(() => respondDuel(d.id, false))}>Decline</button>
                </>
              )}
              {!d.result && (
                <button type="button" className={ghost} disabled={busy}
                  onClick={() => void act(() => cancelDuel(d.id), 'Duel cancelled')}>Cancel</button>
              )}
            </div>
          </div>
        ))}
        {mates.length > 0 && (
          <div className="space-y-1.5">
            <p className="font-caption text-[11px] text-muted-text leading-relaxed">
              One week, two people. Whoever improves most against their OWN last 4 weeks, not who has more hours.
              Declining is silent.
            </p>
            <div className="flex gap-2">
              <select className={`${input} flex-1`} value={duelTo} onChange={(e) => setDuelTo(e.target.value)}
                aria-label="Opponent">
                <option value="">Choose a crewmate</option>
                {mates.map((m) => <option key={m.username} value={m.username}>@{m.username}</option>)}
              </select>
              <button type="button" className={btn} disabled={busy || !duelTo}
                onClick={() => void act(() => proposeDuel(crew.id, duelTo), 'Duel proposed').then(() => setDuelTo(''))}>
                Challenge
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
