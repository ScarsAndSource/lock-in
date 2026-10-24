import React, { useState } from 'react';
import { useCrew } from '../../context/CrewContext';
import { CHEER_TEXT, respondToInvite, sendCheer } from '../../api/crew';
import { DealCard, DuelCard } from './Deals';
import { btn, ghost, head } from './ui';

const SHOWN = 3;

/**
 * Everything waiting on you, in one place, most actionable first. Renders nothing when there is nothing,
 * so a quiet crew is a quiet screen. `fresh` holds ids that were new when the tab opened (they were
 * marked seen on arrival, so they stay highlighted for this visit only).
 */
export const ForYou: React.FC<{ fresh: ReadonlySet<string> }> = ({ fresh }) => {
  const { overview, inbox, buddies, duels, answered, act, busy, markAnswered } = useCrew();
  const [allCheers, setAllCheers] = useState(false);

  const invites = overview?.invites ?? [];
  const dueDeals = (buddies?.deals ?? []).filter((d) => d.role === 'owner' && d.status === 'active' && d.due);
  const dealRequests = (buddies?.deals ?? []).filter((d) => d.role === 'buddy' && d.status === 'pending');
  const duelInvites = duels.filter((d) => d.role === 'opponent' && d.status === 'pending');
  const boosts = (inbox?.boosts ?? []).filter((b) => !answered.has(b.id));
  const messages = buddies?.messages ?? [];
  const cheers = inbox?.cheers ?? [];
  const shownCheers = allCheers ? cheers : cheers.slice(0, SHOWN);
  const isNew = (id: string, seen: boolean) => !seen || fresh.has(id);

  const total =
    invites.length + dueDeals.length + dealRequests.length + duelInvites.length + boosts.length + messages.length + cheers.length;
  if (total === 0) return null;

  return (
    <section className="space-y-2" aria-label="For you">
      <span className={head}>For you</span>

      {invites.map((i) => (
        <div key={i.crew_id} className="bg-surface rounded-xl border border-line p-3 flex items-center justify-between gap-2">
          <span className="font-small text-small text-ink">
            {i.from_username ? `@${i.from_username} invited you to ` : 'Invited to '}
            <strong>{i.crew_name}</strong>
          </span>
          <span className="flex gap-1.5 shrink-0">
            <button
              type="button"
              disabled={busy}
              className={btn}
              onClick={() => void act(() => respondToInvite(i.crew_id, true), { ok: 'Joined', reload: ['overview', 'inbox', 'buddies', 'duels'] })}
            >
              Join
            </button>
            <button
              type="button"
              disabled={busy}
              className={ghost}
              onClick={() => void act(() => respondToInvite(i.crew_id, false), { reload: ['overview'] })}
            >
              Ignore
            </button>
          </span>
        </div>
      ))}

      {dueDeals.map((d) => <DealCard key={d.id} deal={d} />)}
      {dealRequests.map((d) => <DealCard key={d.id} deal={d} />)}
      {duelInvites.map((d) => <DuelCard key={d.id} duel={d} />)}

      {boosts.map((b) => (
        <div key={b.id} className="bg-surface rounded-xl border border-line p-3 flex items-center justify-between gap-2">
          <span className={`font-small text-small ${isNew(b.id, b.seen) ? 'text-ink' : 'text-muted-text'}`}>
            @{b.from_username} could use a hello
          </span>
          <button
            type="button"
            disabled={busy}
            className={ghost}
            onClick={() =>
              void act(
                async () => {
                  await sendCheer(b.crew_id, b.from_username, 'rooting');
                  markAnswered(b.id);
                },
                { ok: 'Cheer sent' },
              )
            }
          >
            Say: {CHEER_TEXT.rooting}
          </button>
        </div>
      ))}

      {messages.map((m) => (
        <p key={m.id} className={`font-small text-small px-1 ${isNew(m.id, m.seen) ? 'text-ink' : 'text-muted-text'}`}>
          @{m.from_username}: {m.body}
        </p>
      ))}

      {cheers.length > 0 && (
        <div className="space-y-1 px-1">
          {shownCheers.map((c) => (
            <p key={c.id} className={`font-small text-small ${isNew(c.id, c.seen) ? 'text-ink' : 'text-muted-text'}`}>
              @{c.from_username}: {CHEER_TEXT[c.kind]}
            </p>
          ))}
          {cheers.length > SHOWN && (
            <button type="button" className="font-caption text-caption text-muted-text underline" onClick={() => setAllCheers((v) => !v)}>
              {allCheers ? 'Show fewer' : `Show ${cheers.length - SHOWN} earlier`}
            </button>
          )}
        </div>
      )}
    </section>
  );
};
