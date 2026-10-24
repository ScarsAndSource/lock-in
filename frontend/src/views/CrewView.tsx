import React, { useEffect, useRef, useState } from 'react';
import { useCrew } from '../context/CrewContext';
import { CrewsSection } from '../components/crew/CrewsSection';
import { UsernameCard, YouSection } from '../components/crew/YouSection';
import { WeekSection } from '../components/crew/WeekSection';
import { box, ghost } from '../components/crew/ui';

type Segment = 'week' | 'crews' | 'you';
const SEGMENTS: { key: Segment; label: string }[] = [
  { key: 'week', label: 'This week' },
  { key: 'crews', label: 'Crews' },
  { key: 'you', label: 'You' },
];

/**
 * The whole Crew feature. Three small sections instead of one long page:
 *   This week: what's waiting for you, closing your week once, and each crew's Sunday card.
 *   Crews:     members, invites, goal, buddy deals, duels, quiet, leave, start or join.
 *   You:       username, what you share, who you blocked.
 */
export const CrewView: React.FC = () => {
  const { live, overview, inbox, buddies, loading, error, attention, reload, refresh, markSeen } = useCrew();
  const [segment, setSegment] = useState<Segment | null>(null);
  const fresh = useRef<Set<string>>(new Set());

  // Opening the tab is the moment to look for anything new (skipped if the data is under 30 seconds old).
  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Whatever is unseen while this tab is open counts as seen. It stays highlighted for this visit only.
  useEffect(() => {
    let any = false;
    const note = (id: string, seen: boolean) => {
      if (!seen) {
        fresh.current.add(id);
        any = true;
      }
    };
    inbox?.cheers.forEach((c) => note(c.id, c.seen));
    inbox?.boosts.forEach((b) => note(b.id, b.seen));
    buddies?.messages.forEach((m) => note(m.id, m.seen));
    if (any) void markSeen();
  }, [inbox, buddies, markSeen]);

  if (!live) {
    return (
      <div className="w-full pb-24 max-w-md mx-auto animate-fadeIn">
        <p className="font-caption text-caption text-muted-text pt-2">Crew needs a real account. Sign in to use it.</p>
      </div>
    );
  }
  if (!overview) {
    if (error && !loading) {
      return (
        <div className="w-full pb-24 max-w-md mx-auto animate-fadeIn">
          <div className={box}>
            <p className="font-small text-small text-ink">{error}</p>
            <button type="button" className={ghost} onClick={() => void reload()}>Try again</button>
          </div>
        </div>
      );
    }
    return (
      <div className="w-full pb-24 max-w-md mx-auto animate-fadeIn">
        <p className="font-caption text-caption text-muted-text pt-2">Loading…</p>
      </div>
    );
  }
  if (!overview.username) {
    return (
      <div className="w-full pb-24 max-w-md mx-auto animate-fadeIn">
        <UsernameCard onboarding />
      </div>
    );
  }

  // Land where something is waiting: anyone in a crew, or holding an invite, starts on This week.
  const auto: Segment = overview.crews.length > 0 || overview.invites.length > 0 || attention > 0 ? 'week' : 'crews';
  const current = segment ?? auto;

  return (
    <div className="flex flex-col w-full pb-24 max-w-md mx-auto space-y-4 animate-fadeIn">
      <div className="flex gap-1 p-1 bg-surface-container rounded-xl" role="tablist" aria-label="Crew sections">
        {SEGMENTS.map((s) => {
          const on = current === s.key;
          return (
            <button
              key={s.key}
              type="button"
              role="tab"
              aria-selected={on}
              onClick={() => setSegment(s.key)}
              className={`relative flex-1 h-9 rounded-lg font-caption text-caption transition-colors ${
                on ? 'bg-surface text-ink font-semibold shadow-sm' : 'text-muted-text hover:text-ink'
              }`}
            >
              {s.label}
              {s.key === 'week' && attention > 0 && !on && (
                <span className="absolute top-1.5 right-2.5 w-2 h-2 rounded-full bg-domain-habits-fill" aria-label="Something is waiting" />
              )}
            </button>
          );
        })}
      </div>

      {current === 'week' && <WeekSection fresh={fresh.current} onGoCrews={() => setSegment('crews')} onGoYou={() => setSegment('you')} />}
      {current === 'crews' && <CrewsSection />}
      {current === 'you' && <YouSection />}
    </div>
  );
};
