import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useApp } from '../../context/AppContext';
import { errorMessage } from '../../lib/format';
import {
  CHEER_TEXT, SHARE_ROWS, blockUser, createCrew, getCrewInbox, getCrewOverview, inviteToCrew, joinCrewWithCode,
  leaveCrew, makeInviteCode, markCrewInboxSeen, respondToInvite, sendCheer, setCrewQuiet, setCrewShare,
  setCrewUsername, unblockUser, type Crew, type CrewInbox, type CrewOverview, type ShareKey,
} from '../../api/crew';
import { CrewCardView } from './CrewCardView';
import { CrewExtras } from './CrewExtras';

const input = 'w-full bg-surface-container-low border border-line rounded-lg px-3 py-2 font-small text-ink';
const btn = 'h-9 px-3 rounded-lg bg-ink text-ground-chalk font-caption text-caption font-semibold disabled:opacity-40 shrink-0';
const ghost = 'h-8 px-2.5 rounded-lg bg-surface-container text-ink font-caption text-caption disabled:opacity-40';
const head = 'font-caption text-[11px] text-muted-text uppercase tracking-wider';

type Act = (fn: () => Promise<unknown>, ok?: string) => Promise<void>;

const OneLine: React.FC<{
  placeholder: string;
  action: string;
  busy: boolean;
  maxLength?: number;
  onSubmit: (value: string) => void;
}> = ({ placeholder, action, busy, maxLength = 40, onSubmit }) => {
  const [value, setValue] = useState('');
  const go = () => {
    if (!value.trim()) return;
    onSubmit(value.trim());
    setValue('');
  };
  return (
    <div className="flex gap-2">
      <input className={input} value={value} maxLength={maxLength} placeholder={placeholder}
        onChange={(e) => setValue(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && go()} />
      <button type="button" disabled={busy || !value.trim()} onClick={go} className={btn}>{action}</button>
    </div>
  );
};

const CrewRow: React.FC<{
  crew: Crew;
  share: CrewOverview['share'];
  busy: boolean;
  act: Act;
}> = ({ crew, share, busy, act }) => {
  const { showToast } = useApp();
  const [card, setCard] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [extras, setExtras] = useState(false);
  const active = crew.members.filter((m) => m.status === 'active').length;

  const copy = (code: string) =>
    navigator.clipboard.writeText(code).then(() => showToast('Code copied'), () => showToast('Copy failed'));

  return (
    <div className="bg-surface rounded-xl border border-line p-3 space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="font-small-medium text-small-medium text-ink">{crew.name}</span>
        <span className="font-caption text-caption text-muted-text">{active} of 6</span>
      </div>
      <p className="font-caption text-caption text-muted-text">
        {crew.members.map((m) => (m.is_me ? 'you' : `@${m.username}`) + (m.status === 'invited' ? ' (invited)' : '')).join(', ')}
      </p>

      <div className="flex flex-wrap gap-1.5">
        <button type="button" className={ghost} onClick={() => setCard((v) => !v)}>
          {card ? 'Hide Sunday card' : 'Sunday card'}
        </button>
        <button type="button" className={ghost} onClick={() => setInviting((v) => !v)}>Invite</button>
        <button type="button" className={ghost} onClick={() => setExtras((v) => !v)}>Goal, deals, duels</button>
        <button type="button" disabled={busy} className={ghost}
          onClick={() => void act(() => setCrewQuiet(crew.id, !crew.quiet), crew.quiet ? 'Sharing again' : 'You went quiet')}>
          {crew.quiet ? 'Resume sharing' : 'Go quiet'}
        </button>
        <button type="button" disabled={busy} className={ghost}
          onClick={() => window.confirm(`Leave ${crew.name}?`) && void act(() => leaveCrew(crew.id), 'You left the crew')}>
          Leave
        </button>
      </div>

      {inviting && (
        <div className="space-y-2">
          <OneLine placeholder="exact username" action="Invite" busy={busy}
            onSubmit={(u) => void act(() => inviteToCrew(crew.id, u), 'Invite sent')} />
          {crew.role === 'owner' && (
            <div className="flex flex-wrap items-center gap-1.5">
              {crew.invite_code ? (
                <>
                  <code className="bg-surface-container-low border border-line rounded-lg px-2 py-1 font-caption text-[12px] text-ink break-all">
                    {crew.invite_code}
                  </code>
                  <button type="button" className={ghost} onClick={() => void copy(crew.invite_code as string)}>Copy</button>
                  <button type="button" className={ghost} disabled={busy}
                    onClick={() => void act(() => makeInviteCode(crew.id, true), 'Code revoked')}>Revoke</button>
                </>
              ) : (
                <button type="button" className={ghost} disabled={busy}
                  onClick={() => void act(() => makeInviteCode(crew.id), 'Code ready, good for 7 days')}>
                  Make an invite code
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {card && <CrewCardView crew={crew} share={share} />}
      {extras && <CrewExtras crew={crew} />}
    </div>
  );
};

/** The whole Crew feature in one panel. Everything here is opt-in; nothing is public, ranked or searchable. */
export const CrewPanel: React.FC = () => {
  const { demoMode, showToast } = useApp();
  const [ov, setOv] = useState<CrewOverview | null>(null);
  const [inbox, setInbox] = useState<CrewInbox | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [editName, setEditName] = useState(false);
  const seenOnce = useRef(false);

  useEffect(() => {
    sessionStorage.removeItem('lockin_crew'); // a push tap opened Settings on this panel; the flag is one-shot
  }, []);

  const load = useCallback(async () => {
    try {
      const [o, i] = await Promise.all([getCrewOverview(), getCrewInbox()]);
      setOv(o);
      setInbox(i);
      if (!seenOnce.current && (i.cheers.some((c) => !c.seen) || i.boosts.some((b) => !b.seen))) {
        seenOnce.current = true;
        void markCrewInboxSeen().catch(() => undefined); // the list below still shows what was new
      }
    } catch (e) {
      showToast(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    if (!demoMode) void load();
  }, [demoMode, load]);

  const act: Act = async (fn, ok) => {
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

  if (demoMode) {
    return <p className="font-caption text-caption text-muted-text pt-2">Crew needs a real account. Sign in to use it.</p>;
  }
  if (loading || !ov) return <p className="font-caption text-caption text-muted-text pt-2">Loading…</p>;

  const toggleShare = (key: ShareKey) => {
    const next = { days: false, hours: false, proud: false, focus: false, habits: false, ...ov.share, [key]: !ov.share[key] };
    void act(() => setCrewShare(next));
  };

  return (
    <div className="space-y-4 pt-2">
      <p className="font-caption text-caption text-muted-text leading-relaxed">
        Small groups of 3 to 6. No rankings, no feed, no one can see a missed day.
      </p>

      {/* identity */}
      <div className="space-y-1.5">
        <span className={head}>Your username</span>
        {ov.username && !editName ? (
          <div className="flex items-center justify-between">
            <span className="font-small-medium text-small-medium text-ink">@{ov.username}</span>
            <button type="button" className={ghost} onClick={() => setEditName(true)}>Change</button>
          </div>
        ) : (
          <OneLine placeholder="3-20 chars: a-z, 0-9, _" action="Save" busy={busy}
            onSubmit={(u) => { setEditName(false); void act(() => setCrewUsername(u), 'Username saved'); }} />
        )}
        <p className="font-caption text-[11px] text-muted-text">People find you only by typing this exactly.</p>
      </div>

      {ov.username && (
        <>
          {/* for you */}
          {inbox && (inbox.boosts.length > 0 || inbox.cheers.length > 0) && (
            <div className="space-y-1.5">
              <span className={head}>For you</span>
              {inbox.boosts.map((b) => (
                <div key={b.id} className="flex items-center justify-between gap-2">
                  <span className="font-small text-small text-ink">@{b.from_username} could use a hello</span>
                  <button type="button" className={ghost}
                    onClick={() => void act(() => sendCheer(b.crew_id, b.from_username, 'rooting'), 'Cheer sent')}>
                    {CHEER_TEXT.rooting}
                  </button>
                </div>
              ))}
              {inbox.cheers.slice(0, 8).map((c) => (
                <p key={c.id} className={`font-small text-small ${c.seen ? 'text-muted-text' : 'text-ink'}`}>
                  @{c.from_username}: {CHEER_TEXT[c.kind]}
                </p>
              ))}
            </div>
          )}

          {/* invites */}
          {ov.invites.length > 0 && (
            <div className="space-y-1.5">
              <span className={head}>Invites</span>
              {ov.invites.map((i) => (
                <div key={i.crew_id} className="flex items-center justify-between gap-2">
                  <span className="font-small text-small text-ink">
                    {i.from_username ? `@${i.from_username} invited you to ` : 'Invited to '}{i.crew_name}
                  </span>
                  <span className="flex gap-1.5">
                    <button type="button" disabled={busy} className={ghost}
                      onClick={() => void act(() => respondToInvite(i.crew_id, true), 'Joined')}>Join</button>
                    <button type="button" disabled={busy} className={ghost}
                      onClick={() => void act(() => respondToInvite(i.crew_id, false))}>Ignore</button>
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* crews */}
          <div className="space-y-2">
            <span className={head}>Your crews ({ov.crews.length} of 3)</span>
            {ov.crews.map((c) => <CrewRow key={c.id} crew={c} share={ov.share} busy={busy} act={act} />)}
            {ov.crews.length < 3 && (
              <>
                <OneLine placeholder="New crew name" action="Create" busy={busy}
                  onSubmit={(n) => void act(() => createCrew(n), 'Crew created')} />
                <OneLine placeholder="Have an invite code?" action="Join" busy={busy} maxLength={64}
                  onSubmit={(k) => void act(() => joinCrewWithCode(k), 'Joined')} />
              </>
            )}
          </div>

          {/* share menu */}
          <div className="space-y-1.5">
            <span className={head}>What I share</span>
            {SHARE_ROWS.map((r) => (
              <label key={r.key} className="flex items-start gap-2.5 min-h-[40px]">
                <input type="checkbox" className="mt-1" checked={!!ov.share[r.key]} disabled={busy}
                  onChange={() => toggleShare(r.key)} />
                <span>
                  <span className="font-small text-small text-ink block">{r.label}</span>
                  <span className="font-caption text-[11px] text-muted-text block">{r.hint}</span>
                </span>
              </label>
            ))}
            <p className="font-caption text-[11px] text-muted-text leading-relaxed">
              Never shared, and there's no switch for it: journal, mood, urges, sleep and screen-time details, anything about a hard moment.
            </p>
          </div>

          {/* blocks */}
          <div className="space-y-1.5">
            <span className={head}>Blocked</span>
            {ov.blocks.map((u) => (
              <div key={u} className="flex items-center justify-between">
                <span className="font-small text-small text-ink">@{u}</span>
                <button type="button" disabled={busy} className={ghost}
                  onClick={() => void act(() => unblockUser(u), 'Unblocked')}>Unblock</button>
              </div>
            ))}
            <OneLine placeholder="Block a username" action="Block" busy={busy}
              onSubmit={(u) => void act(() => blockUser(u), 'Blocked. They won\'t be told.')} />
          </div>
        </>
      )}
    </div>
  );
};
