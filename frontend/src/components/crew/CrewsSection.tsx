import React, { useCallback, useEffect, useState } from 'react';
import { useApp } from '../../context/AppContext';
import { ALL_PARTS, useCrew } from '../../context/CrewContext';
import { SupportCard } from '../SupportCard';
import type { SupportPayload } from '../../types';
import {
  createCrew, getCrewGoal, inviteToCrew, joinCrewWithCode, leaveCrew, makeInviteCode, proposeBuddy, proposeDuel,
  setCrewGoal, setCrewQuiet, type Crew, type CrewMember, type GoalInfo,
} from '../../api/crew';
import { Chip, OneLine } from './Bits';
import { DealCard, DuelCard } from './Deals';
import {
  box, btn, cleanCode, cleanHandle, copyText, dayLabel, ghost, head, hint, input, stampLabel, validateCode, validateHandle,
} from './ui';

const DEFAULT_MSG = "Hey, I've gone quiet. Could you check in on me?";
const MAX_MEMBERS = 6;
const MAX_CREWS = 3;

const activeMembers = (crew: Crew): CrewMember[] => crew.members.filter((m) => m.status === 'active');
const mates = (crew: Crew): CrewMember[] => activeMembers(crew).filter((m) => !m.is_me);

async function shareCode(crew: Crew, code: string, toast: (m: string) => void): Promise<void> {
  const text = `Join my crew "${crew.name}" on Lock'in with this code: ${code}`;
  if (typeof navigator.share === 'function') {
    try {
      await navigator.share({ text });
      return;
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return; // they closed the share sheet
    }
  }
  toast((await copyText(code)) ? 'Code copied' : 'Copy failed');
}

const InvitePanel: React.FC<{ crew: Crew }> = ({ crew }) => {
  const { showToast } = useApp();
  const { act, busy } = useCrew();
  const full = activeMembers(crew).length >= MAX_MEMBERS;

  return (
    <div className="space-y-3">
      {full ? (
        <p className="font-small text-small text-ink">This crew is full ({MAX_MEMBERS} people).</p>
      ) : (
        <div className="space-y-1">
          <p className={hint}>Invite by exact username. Nobody can be found by searching.</p>
          <OneLine
            placeholder="exact username"
            action="Invite"
            busy={busy}
            normalize={cleanHandle}
            validate={validateHandle}
            onSubmit={(u) => act(() => inviteToCrew(crew.id, u), { ok: 'Invite sent', reload: ['overview'] })}
          />
        </div>
      )}

      {crew.role === 'owner' && !full && (
        <div className="space-y-1.5">
          <p className={hint}>Or share a code. It works for 7 days and you can revoke it any time.</p>
          {crew.invite_code ? (
            <>
              <code className="block bg-surface-container-low border border-line rounded-lg px-2 py-1.5 font-caption text-[12px] text-ink break-all">
                {crew.invite_code}
              </code>
              {crew.invite_expires_at && <p className={hint}>Works until {stampLabel(crew.invite_expires_at)}.</p>}
              <div className="flex flex-wrap gap-1.5">
                {typeof navigator.share === 'function' && (
                  <button type="button" className={btn} onClick={() => void shareCode(crew, crew.invite_code as string, showToast)}>
                    Share
                  </button>
                )}
                <button
                  type="button"
                  className={ghost}
                  onClick={() => void copyText(crew.invite_code as string).then((ok) => showToast(ok ? 'Code copied' : 'Copy failed'))}
                >
                  Copy
                </button>
                <button
                  type="button"
                  className={ghost}
                  disabled={busy}
                  onClick={() => void act(() => makeInviteCode(crew.id, true), { ok: 'Code revoked', reload: ['overview'] })}
                >
                  Revoke
                </button>
              </div>
            </>
          ) : (
            <button
              type="button"
              className={ghost}
              disabled={busy}
              onClick={() => void act(() => makeInviteCode(crew.id), { ok: 'Code ready, good for 7 days', reload: ['overview'] })}
            >
              Make an invite code
            </button>
          )}
        </div>
      )}
    </div>
  );
};

const GoalPanel: React.FC<{ crew: Crew }> = ({ crew }) => {
  const { act, busy } = useCrew();
  const [goal, setGoal] = useState<GoalInfo | null>(null);
  const [failed, setFailed] = useState(false);
  const [hours, setHours] = useState('');
  const n = Number(hours);
  const valid = Number.isInteger(n) && n >= 1 && n <= 200;

  const load = useCallback(async () => {
    try {
      setGoal(await getCrewGoal(crew.id));
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [crew.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (value: number | null) => {
    const ok = await act(() => setCrewGoal(crew.id, value), { ok: value == null ? 'Goal cleared' : 'Goal set' });
    if (ok) {
      setHours('');
      await load();
    }
  };

  if (failed) {
    return (
      <div className="space-y-1.5">
        <p className="font-small text-small text-ink">Couldn't load the goal.</p>
        <button type="button" className={ghost} onClick={() => void load()}>Try again</button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <span className={head}>Crew goal{goal ? `, week of ${dayLabel(goal.week_start)}` : ''}</span>
      {goal?.target_minutes ? (
        <p className="font-small text-small text-ink">{Math.round(goal.target_minutes / 60)} hours of study, together. Everyone's part adds up.</p>
      ) : (
        <p className="font-caption text-caption text-muted-text">No goal set for that week.</p>
      )}
      {crew.role === 'owner' && (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (valid) void save(n);
          }}
        >
          <input
            className={input}
            inputMode="numeric"
            value={hours}
            maxLength={3}
            placeholder="Hours, 1 to 200"
            aria-label="Goal in hours"
            onChange={(e) => setHours(e.target.value.replace(/\D/g, ''))}
          />
          <button type="submit" className={btn} disabled={busy || !valid}>Set</button>
          {goal?.target_minutes ? (
            <button type="button" className={ghost} disabled={busy} onClick={() => void save(null)}>Clear</button>
          ) : null}
        </form>
      )}
      <p className={hint}>Counts only hours people chose to share, capped per person, and only shown once 2 people share.</p>
    </div>
  );
};

const BuddyPanel: React.FC<{ crew: Crew }> = ({ crew }) => {
  const { showToast } = useApp();
  const { buddies, act, busy } = useCrew();
  const people = mates(crew);
  const all = buddies?.deals ?? [];
  const deals = all.filter((d) => d.crew_id === crew.id);
  const ownerCount = all.filter((d) => d.role === 'owner').length; // the limit of 2 is per person, across crews

  const [to, setTo] = useState('');
  const [threshold, setThreshold] = useState(3);
  const [message, setMessage] = useState(DEFAULT_MSG);
  const [auto, setAuto] = useState(false);
  const [support, setSupport] = useState<SupportPayload | null>(null);
  const target = to || (people.length === 1 ? people[0].username : '');

  const propose = async () => {
    const out: { support: SupportPayload | null } = { support: null };
    const ok = await act(
      async () => {
        const res = await proposeBuddy({ crew_id: crew.id, to: target, threshold, message: message.trim(), auto_send: auto });
        out.support = res.support;
      },
      { reload: ['buddies'] },
    );
    if (out.support) {
      setSupport(out.support);
      return;
    }
    if (ok) {
      showToast('Deal proposed. They have to accept.');
      setTo('');
      setMessage(DEFAULT_MSG);
      setAuto(false);
    }
  };

  return (
    <div className="space-y-2">
      {support && <SupportCard support={support} />}
      {deals.map((d) => <DealCard key={d.id} deal={d} />)}

      {people.length === 0 && <p className="font-caption text-caption text-muted-text">Buddy deals are between crewmates. Invite someone first.</p>}
      {people.length > 0 && ownerCount >= 2 && (
        <p className="font-caption text-caption text-muted-text">You have two buddy deals, the limit. Cancel one to make another.</p>
      )}
      {people.length > 0 && ownerCount < 2 && (
        <div className="space-y-1.5">
          <p className={hint}>
            Pick a crewmate. If you go quiet, the app asks YOU whether to send them your message. Nothing is sent unless you tap, or you turn on auto-send.
          </p>
          <div className="flex gap-2">
            <select className={`${input} flex-1`} value={target} onChange={(e) => setTo(e.target.value)} aria-label="Buddy">
              <option value="">Choose a buddy</option>
              {people.map((m) => <option key={m.username} value={m.username}>@{m.username}</option>)}
            </select>
            <select className={`${input} w-24`} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} aria-label="Quiet planned days before it is due">
              {[2, 3, 4, 5, 6, 7].map((n) => <option key={n} value={n}>{n} days</option>)}
            </select>
          </div>
          <input className={input} maxLength={140} value={message} onChange={(e) => setMessage(e.target.value)} aria-label="Your message" />
          <label className="flex items-center gap-2 font-caption text-caption text-ink min-h-[36px]">
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
            Auto-send without asking me (off by default)
          </label>
          <button type="button" className={`${btn} w-full`} disabled={busy || !target || !message.trim()} onClick={() => void propose()}>
            Propose deal
          </button>
        </div>
      )}
    </div>
  );
};

const DuelPanel: React.FC<{ crew: Crew }> = ({ crew }) => {
  const { duels, act, busy } = useCrew();
  const people = mates(crew);
  const mine = duels.filter((d) => d.crew_id === crew.id);
  const [earlier, setEarlier] = useState(false);
  const [to, setTo] = useState('');
  const target = to || (people.length === 1 ? people[0].username : '');
  const shown = earlier ? mine : mine.slice(0, 4);

  const challenge = async () => {
    const ok = await act(() => proposeDuel(crew.id, target), { ok: 'Duel proposed', reload: ['duels'] });
    if (ok) setTo('');
  };

  return (
    <div className="space-y-2">
      {shown.map((d) => <DuelCard key={d.id} duel={d} />)}
      {mine.length > 4 && (
        <button type="button" className="font-caption text-caption text-muted-text underline" onClick={() => setEarlier((v) => !v)}>
          {earlier ? 'Show fewer' : `Show ${mine.length - 4} earlier`}
        </button>
      )}
      {people.length === 0 ? (
        <p className="font-caption text-caption text-muted-text">Duels are between crewmates. Invite someone first.</p>
      ) : (
        <div className="space-y-1.5">
          <p className={hint}>
            One week, two people, starting next week. Whoever improves most against their OWN last 4 weeks wins, not whoever has more hours. Declining is silent.
          </p>
          <div className="flex gap-2">
            <select className={`${input} flex-1`} value={target} onChange={(e) => setTo(e.target.value)} aria-label="Opponent">
              <option value="">Choose a crewmate</option>
              {people.map((m) => <option key={m.username} value={m.username}>@{m.username}</option>)}
            </select>
            <button type="button" className={btn} disabled={busy || !target} onClick={() => void challenge()}>Challenge</button>
          </div>
        </div>
      )}
    </div>
  );
};

const MorePanel: React.FC<{ crew: Crew }> = ({ crew }) => {
  const { act, busy } = useCrew();
  return (
    <div className="space-y-2.5">
      <div className="space-y-1">
        <p className="font-small text-small text-ink">{crew.quiet ? 'You are quiet in this crew.' : 'Need a breather from this crew?'}</p>
        <p className={hint}>While quiet, your week isn't shown to this crew. You still see theirs, and you can come back any time.</p>
        <button
          type="button"
          className={ghost}
          disabled={busy}
          onClick={() => void act(() => setCrewQuiet(crew.id, !crew.quiet), { ok: crew.quiet ? 'Sharing again' : 'You went quiet', reload: ['overview'] })}
        >
          {crew.quiet ? 'Resume sharing' : 'Go quiet'}
        </button>
      </div>
      <div className="space-y-1 pt-2 border-t border-line">
        <button
          type="button"
          className={ghost}
          disabled={busy}
          onClick={() => {
            if (window.confirm(`Leave ${crew.name}?`)) void act(() => leaveCrew(crew.id), { ok: 'You left the crew', reload: ALL_PARTS });
          }}
        >
          Leave crew
        </button>
      </div>
    </div>
  );
};

const PANELS = [
  ['invite', 'Invite'],
  ['goal', 'Goal'],
  ['buddy', 'Buddy'],
  ['duel', 'Duel'],
  ['more', 'More'],
] as const;
type PanelKey = (typeof PANELS)[number][0];

/** One crew. Closed it is a single row; open it shows five small chips and only ever one panel at a time. */
const CrewItem: React.FC<{ crew: Crew; defaultOpen: boolean }> = ({ crew, defaultOpen }) => {
  const { buddies, duels } = useCrew();
  const [open, setOpen] = useState(defaultOpen);
  const [panel, setPanel] = useState<PanelKey | null>(null);
  const count = activeMembers(crew).length;

  const buddyDot = (buddies?.deals ?? []).some(
    (d) => d.crew_id === crew.id && ((d.role === 'owner' && d.due) || (d.role === 'buddy' && d.status === 'pending')),
  );
  const duelDot = duels.some((d) => d.crew_id === crew.id && d.role === 'opponent' && d.status === 'pending');

  return (
    <div className="bg-surface rounded-xl border border-line overflow-hidden">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="w-full min-h-[48px] px-3 py-2.5 flex items-center justify-between gap-3 text-left"
      >
        <span className="flex items-center gap-2 min-w-0">
          <span className="font-small-medium text-small-medium text-ink truncate">{crew.name}</span>
          {(buddyDot || duelDot) && <span className="w-2 h-2 rounded-full bg-domain-habits-fill shrink-0" aria-label="Needs you" />}
        </span>
        <span className="flex items-center gap-1.5 shrink-0">
          <span className="font-caption text-caption text-muted-text">{count} of {MAX_MEMBERS}{crew.quiet ? ' · quiet' : ''}</span>
          <span className={`material-symbols-outlined text-[20px] text-muted-text transition-transform ${open ? 'rotate-180' : ''}`}>expand_more</span>
        </span>
      </button>

      {open && (
        <div className="px-3 pb-3 pt-2 border-t border-surface-container space-y-3">
          <p className="font-caption text-caption text-muted-text">
            {crew.members.map((m) => (m.is_me ? 'you' : `@${m.username}`) + (m.status === 'invited' ? ' (invited)' : '')).join(', ')}
          </p>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Crew actions">
            {PANELS.map(([key, label]) => (
              <Chip
                key={key}
                on={panel === key}
                dot={(key === 'buddy' && buddyDot) || (key === 'duel' && duelDot)}
                onClick={() => setPanel((cur) => (cur === key ? null : key))}
              >
                {label}
              </Chip>
            ))}
          </div>
          {panel === 'invite' && <InvitePanel crew={crew} />}
          {panel === 'goal' && <GoalPanel crew={crew} />}
          {panel === 'buddy' && <BuddyPanel crew={crew} />}
          {panel === 'duel' && <DuelPanel crew={crew} />}
          {panel === 'more' && <MorePanel crew={crew} />}
        </div>
      )}
    </div>
  );
};

const StartOrJoin: React.FC<{ count: number }> = ({ count }) => {
  const { act, busy } = useCrew();
  const [mode, setMode] = useState<'start' | 'join' | null>(count === 0 ? 'start' : null);

  if (count >= MAX_CREWS) {
    return <p className={hint}>You're in {MAX_CREWS} crews, the most there can be. Leave one to start or join another.</p>;
  }

  return (
    <div className={box}>
      <div className="flex gap-1.5" role="group" aria-label="Start or join">
        <Chip on={mode === 'start'} onClick={() => setMode((m) => (m === 'start' ? null : 'start'))}>Start a crew</Chip>
        <Chip on={mode === 'join'} onClick={() => setMode((m) => (m === 'join' ? null : 'join'))}>Join with a code</Chip>
      </div>
      {mode === 'start' && (
        <OneLine
          placeholder="Name your crew"
          action="Create"
          busy={busy}
          onSubmit={(name) => act(() => createCrew(name), { ok: 'Crew created', reload: ALL_PARTS })}
        />
      )}
      {mode === 'join' && (
        <OneLine
          placeholder="Paste an invite code"
          action="Join"
          busy={busy}
          maxLength={64}
          normalize={cleanCode}
          validate={validateCode}
          onSubmit={(code) => act(() => joinCrewWithCode(code), { ok: 'Joined', reload: ALL_PARTS })}
        />
      )}
    </div>
  );
};

/** Everything about the crews themselves: members, invites, goal, buddy deals, duels, quiet, leave. */
export const CrewsSection: React.FC = () => {
  const { overview } = useCrew();
  const crews = overview?.crews ?? [];

  return (
    <div className="space-y-3">
      <span className={head}>Your crews ({crews.length} of {MAX_CREWS})</span>
      {crews.length === 0 && (
        <p className="font-caption text-caption text-muted-text leading-relaxed">
          Small groups of 3 to 6. No rankings, no feed, no one can see a missed day. Start one, or join with a code.
        </p>
      )}
      {crews.map((c) => <CrewItem key={c.id} crew={c} defaultOpen={crews.length === 1} />)}
      <StartOrJoin key={crews.length} count={crews.length} />
    </div>
  );
};
