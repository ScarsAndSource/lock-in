import React from 'react';
import { useCrew } from '../../context/CrewContext';
import {
  cancelBuddy, cancelDuel, holdBuddy, respondBuddy, respondDuel, sendBuddyMessage,
  type BuddyDeal, type Duel,
} from '../../api/crew';
import { btn, dayLabel, ghost } from './ui';

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

/** One buddy deal. Two-sided consent: nothing is sent unless the owner taps (or switched auto-send on). */
export const DealCard: React.FC<{ deal: BuddyDeal }> = ({ deal: d }) => {
  const { act, busy } = useCrew();
  const run = (fn: () => Promise<unknown>, ok?: string) => void act(fn, { ok, reload: ['buddies'] });

  return (
    <div className="rounded-lg border border-line p-2.5 space-y-1.5">
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
                <button type="button" className={btn} disabled={busy} onClick={() => run(() => sendBuddyMessage(d.id), 'Sent')}>
                  Send it
                </button>
                <button type="button" className={ghost} disabled={busy} onClick={() => run(() => holdBuddy(d.id), 'Okay, not now')}>
                  Not now
                </button>
              </div>
            </div>
          )}
        </>
      )}
      <div className="flex gap-1.5">
        {d.role === 'buddy' && d.status === 'pending' && (
          <>
            <button type="button" className={btn} disabled={busy} onClick={() => run(() => respondBuddy(d.id, true), "You're their buddy")}>
              Accept
            </button>
            <button type="button" className={ghost} disabled={busy} onClick={() => run(() => respondBuddy(d.id, false))}>
              Decline
            </button>
          </>
        )}
        {(d.status === 'active' || d.role === 'owner') && (
          <button type="button" className={ghost} disabled={busy} onClick={() => run(() => cancelBuddy(d.id), 'Deal cancelled')}>
            {d.role === 'buddy' ? 'Leave deal' : 'Cancel deal'}
          </button>
        )}
      </div>
    </div>
  );
};

/** One handicapped duel: you against your own last four weeks, not against each other's hours. Declining is silent. */
export const DuelCard: React.FC<{ duel: Duel }> = ({ duel: d }) => {
  const { act, busy } = useCrew();
  const run = (fn: () => Promise<unknown>, ok?: string) => void act(fn, { ok, reload: ['duels'] });
  const week = dayLabel(d.week_start);

  return (
    <div className="rounded-lg border border-line p-2.5 space-y-1.5">
      <p className="font-small text-small text-ink">
        {d.status === 'pending' && d.role === 'challenger' && `Waiting for @${d.other} · week of ${week}`}
        {d.status === 'pending' && d.role === 'opponent' && `@${d.other} invited you to a duel · week of ${week}`}
        {d.status === 'active' && !d.result && `Duel with @${d.other} · week of ${week}. Results appear once you both close your week.`}
        {d.status === 'active' && d.result && `Duel with @${d.other} · week of ${week}`}
      </p>
      <DuelResult d={d} />
      <div className="flex gap-1.5">
        {d.status === 'pending' && d.role === 'opponent' && (
          <>
            <button type="button" className={btn} disabled={busy} onClick={() => run(() => respondDuel(d.id, true), 'Duel on')}>
              Accept
            </button>
            <button type="button" className={ghost} disabled={busy} onClick={() => run(() => respondDuel(d.id, false))}>
              Decline
            </button>
          </>
        )}
        {!d.result && (
          <button type="button" className={ghost} disabled={busy} onClick={() => run(() => cancelDuel(d.id), 'Duel cancelled')}>
            Cancel
          </button>
        )}
      </div>
    </div>
  );
};
