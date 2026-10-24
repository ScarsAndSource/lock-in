import React, { useState } from 'react';
import { useCrew, ALL_PARTS } from '../../context/CrewContext';
import { SHARE_ROWS, blockUser, setCrewShare, setCrewUsername, unblockUser, type ShareKey } from '../../api/crew';
import { OneLine } from './Bits';
import { NO_SHARE, USERNAME_HINT, box, cleanHandle, ghost, head, hint, validateHandle } from './ui';

/** Pick or change the username. First time, this is the only thing on the whole tab. */
export const UsernameCard: React.FC<{ onboarding?: boolean }> = ({ onboarding = false }) => {
  const { overview, act, busy } = useCrew();
  const [editing, setEditing] = useState(false);
  const name = overview?.username ?? null;

  const save = (u: string) =>
    act(() => setCrewUsername(u), { ok: 'Username saved', reload: ['overview'] }).then((ok) => {
      if (ok) setEditing(false);
      return ok;
    });

  return (
    <div className={box}>
      {onboarding && (
        <>
          <p className="font-small-medium text-small-medium text-ink">Pick a username to start</p>
          <p className="font-caption text-caption text-muted-text leading-relaxed">
            Crews are small groups of 3 to 6. No rankings, no feed, no one can see a missed day. Everything is opt-in.
          </p>
        </>
      )}
      {!onboarding && <span className={head}>Your username</span>}
      {name && !editing ? (
        <div className="flex items-center justify-between">
          <span className="font-small-medium text-small-medium text-ink">@{name}</span>
          <button type="button" className={ghost} onClick={() => setEditing(true)}>Change</button>
        </div>
      ) : (
        <OneLine placeholder="3-20 chars: a-z, 0-9, _" action="Save" busy={busy} normalize={cleanHandle} validate={validateHandle} onSubmit={save} />
      )}
      <p className={hint}>
        People find you only by typing this exactly. {onboarding ? USERNAME_HINT : ''}
      </p>
    </div>
  );
};

/** What I share, who I blocked. Nothing about a hard moment ever has a switch. */
export const YouSection: React.FC = () => {
  const { overview, act, busy, patchShare } = useCrew();
  if (!overview) return null;

  const toggleShare = async (key: ShareKey) => {
    const prev = overview.share;
    const next: Record<ShareKey, boolean> = { ...NO_SHARE, ...prev, [key]: !prev[key] };
    patchShare(next); // flip instantly, undo if the server says no
    const ok = await act(() => setCrewShare(next));
    if (!ok) patchShare(prev);
  };

  return (
    <div className="space-y-4">
      <UsernameCard />

      <div className={box}>
        <span className={head}>What I share</span>
        {SHARE_ROWS.map((r) => (
          <label key={r.key} className="flex items-start gap-2.5 min-h-[44px]">
            <input type="checkbox" className="mt-1" checked={!!overview.share[r.key]} disabled={busy} onChange={() => void toggleShare(r.key)} />
            <span>
              <span className="font-small text-small text-ink block">{r.label}</span>
              <span className="font-caption text-[11px] text-muted-text block">{r.hint}</span>
            </span>
          </label>
        ))}
        <p className={hint}>
          Never shared, and there's no switch for it: journal, mood, urges, sleep and screen-time details, anything about a hard moment.
        </p>
      </div>

      <div className={box}>
        <span className={head}>Blocked</span>
        {overview.blocks.length === 0 && <p className="font-caption text-caption text-muted-text">No one. Blocking is silent: they aren't told.</p>}
        {overview.blocks.map((u) => (
          <div key={u} className="flex items-center justify-between">
            <span className="font-small text-small text-ink">@{u}</span>
            <button
              type="button"
              disabled={busy}
              className={ghost}
              onClick={() => void act(() => unblockUser(u), { ok: 'Unblocked', reload: ALL_PARTS })}
            >
              Unblock
            </button>
          </div>
        ))}
        <OneLine
          placeholder="Block a username"
          action="Block"
          busy={busy}
          normalize={cleanHandle}
          validate={validateHandle}
          onSubmit={(u) => act(() => blockUser(u), { ok: "Blocked. They won't be told.", reload: ALL_PARTS })}
        />
      </div>
    </div>
  );
};
