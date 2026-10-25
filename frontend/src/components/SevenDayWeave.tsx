import React, { useEffect, useState } from 'react';
import { useApp } from '../context/AppContext';
import { getChain } from '../api/stats';
import type { ChainDomainStatus } from '../types';
import { formatDayShort, weekdayLetter } from '../lib/dates';
import { toWeaveStatus } from '../lib/format';

type DomainId = 'habits' | 'sleep' | 'screen' | 'study' | 'urges';

interface DayColumn {
  iso: string;
  letter: string;
  short: string;
  isToday: boolean;
  s: Record<DomainId, ChainDomainStatus>;
}

const DOMAINS: { id: DomainId; label: string; fill: string; tint: string; stroke: string }[] = [
  { id: 'habits', label: 'Habits', fill: 'bg-domain-habits-fill', tint: 'bg-domain-habits-tint', stroke: '#A8662F' },
  { id: 'sleep', label: 'Sleep', fill: 'bg-domain-sleep-fill', tint: 'bg-domain-sleep-tint', stroke: '#4F6F9C' },
  { id: 'screen', label: 'Screen', fill: 'bg-domain-screen-fill', tint: 'bg-domain-screen-tint', stroke: '#C29A33' },
  { id: 'study', label: 'Study', fill: 'bg-domain-study-fill', tint: 'bg-domain-study-tint', stroke: '#5C8758' },
  { id: 'urges', label: 'Urges', fill: 'bg-domain-urges-fill', tint: 'bg-domain-urges-tint', stroke: '#8D5570' },
];

const WORD: Record<ChainDomainStatus, string> = { good: 'good', partial: 'partial', missed: 'missed', none: 'not logged' };

/** One state per day: the mean of whatever was logged (good 1, partial 0.5, missed 0). */
function overall(s: DayColumn['s']): ChainDomainStatus {
  const known = DOMAINS.map((d) => s[d.id]).filter((v) => v !== 'none');
  if (known.length === 0) return 'none';
  const score = known.reduce((sum, v) => sum + (v === 'good' ? 1 : v === 'partial' ? 0.5 : 0), 0) / known.length;
  return score >= 0.75 ? 'good' : score >= 0.4 ? 'partial' : 'missed';
}

const Dot: React.FC<{ status: ChainDomainStatus }> = ({ status }) => {
  if (status === 'good') return <span className="block w-3.5 h-3.5 rounded-full bg-ink" />;
  if (status === 'partial') {
    return (
      <span
        className="block w-3.5 h-3.5 rounded-full border-2 border-ink"
        style={{ background: 'linear-gradient(to top, #262B36 50%, #EDF0F2 50%)' }}
      />
    );
  }
  if (status === 'missed') return <span className="block w-3.5 h-3.5 rounded-full border-2 border-ink bg-surface" />;
  return <span className="block w-2.5 h-[2px] bg-outline-variant" />;
};

const Cell: React.FC<{ status: ChainDomainStatus; fill: string; tint: string; stroke: string }> = ({
  status,
  fill,
  tint,
  stroke,
}) => {
  if (status === 'good') return <div className={`w-[20px] h-[14px] rounded ${fill}`} />;
  if (status === 'partial') {
    return (
      <div className={`w-[20px] h-[14px] rounded ${tint} overflow-hidden flex flex-col justify-end`}>
        <div className={`h-[7px] w-full ${fill}`} />
      </div>
    );
  }
  if (status === 'missed') {
    return (
      <svg width="20" height="14" viewBox="0 0 20 14">
        <rect fill="none" height="12" rx="3" stroke={stroke} strokeWidth="1.5" width="18" x="1" y="1" />
      </svg>
    );
  }
  return (
    <div className="w-[20px] h-[14px] flex items-center justify-center">
      <div className="w-3 h-[1px] bg-outline-variant" />
    </div>
  );
};

interface SevenDayWeaveProps {
  days?: number;
  defaultExpanded?: boolean;
}

/** Collapsed: one dot per day. Expanded: the five-domain grid with a day detail on tap. */
export const SevenDayWeave: React.FC<SevenDayWeaveProps> = ({ days = 7, defaultExpanded = false }) => {
  const { activeDate, dataEpoch, demoMode } = useApp();
  const [cols, setCols] = useState<DayColumn[]>([]);
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [selectedIso, setSelectedIso] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getChain(days, activeDate)
      .then((res) => {
        if (cancelled) return;
        setCols(
          res.days.slice(-days).map((d) => ({
            iso: d.day,
            letter: weekdayLetter(d.day),
            short: formatDayShort(d.day),
            isToday: d.day === activeDate,
            s: {
              habits: toWeaveStatus(d.habits),
              sleep: toWeaveStatus(d.sleep),
              screen: toWeaveStatus(d.screen_time),
              study: toWeaveStatus(d.study),
              urges: toWeaveStatus(d.urges),
            },
          }))
        );
      })
      .catch(() => {
        if (!cancelled) setCols([]);
      });
    return () => {
      cancelled = true;
    };
  }, [days, activeDate, dataEpoch, demoMode]);

  const selected = cols.find((c) => c.iso === selectedIso) ?? null;
  const title = days === 7 ? 'This week' : `Last ${days} days`;

  return (
    <section className="w-full bg-surface rounded-xl border border-line overflow-hidden">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
        className="w-full px-4 pt-3 pb-3 text-left"
      >
        <span className="flex items-center justify-between">
          <span className="font-section text-section text-ink">{title}</span>
          <span className="flex items-center gap-1 font-caption text-caption text-muted-text">
            {expanded ? 'Hide detail' : 'Detail'}
            <span className={`material-symbols-outlined text-[18px] transition-transform ${expanded ? 'rotate-180' : ''}`}>
              expand_more
            </span>
          </span>
        </span>
        {!expanded &&
          (cols.length === 0 ? (
            <span className="block font-caption text-caption text-muted-text pt-2">No data yet.</span>
          ) : (
            <span className="flex items-end justify-between pt-3">
              {cols.map((c) => (
                <span
                  key={c.iso}
                  title={`${c.short}: ${DOMAINS.map((d) => `${d.label} ${WORD[c.s[d.id]]}`).join(', ')}`}
                  className="flex flex-col items-center gap-2 flex-1"
                >
                  <Dot status={overall(c.s)} />
                  <span className={`font-caption text-caption ${c.isToday ? 'text-ink font-semibold' : 'text-muted-text'}`}>
                    {c.letter}
                  </span>
                </span>
              ))}
            </span>
          ))}
      </button>

      {expanded && (
        <div className="px-4 pb-4">
          {cols.length === 0 ? (
            <p className="font-caption text-caption text-muted-text">No data yet.</p>
          ) : (
            <div className="flex items-stretch gap-3 overflow-x-auto pb-1">
              <div className="flex flex-col justify-between pt-6 pb-1 shrink-0 select-none">
                {DOMAINS.map((d) => (
                  <div key={d.id} className="h-[14px] flex items-center font-caption text-caption text-muted-text">
                    {d.label}
                  </div>
                ))}
              </div>
              <div className="flex items-start gap-2.5 flex-1 justify-end">
                {cols.map((c) => (
                  <button
                    key={c.iso}
                    type="button"
                    title={c.short}
                    onClick={() => setSelectedIso(selectedIso === c.iso ? null : c.iso)}
                    className="flex flex-col items-center"
                  >
                    <span className={`font-caption text-caption mb-2 ${c.isToday ? 'text-ink font-semibold' : 'text-muted-text'}`}>
                      {c.letter}
                    </span>
                    <div className="flex flex-col gap-[3px]">
                      {DOMAINS.map((d) => (
                        <Cell key={d.id} status={c.s[d.id]} fill={d.fill} tint={d.tint} stroke={d.stroke} />
                      ))}
                    </div>
                    <div className={`w-full h-[2px] mt-2 ${c.isToday ? 'bg-ink' : selectedIso === c.iso ? 'bg-secondary' : 'bg-transparent'}`} />
                  </button>
                ))}
              </div>
            </div>
          )}

          {selected && (
            <div className="mt-3 p-3 bg-surface-container-low rounded-lg border border-surface-container animate-fadeIn">
              <span className="font-small-medium text-small-medium text-ink block">{selected.short}</span>
              <span className="font-caption text-caption text-muted-text">
                {DOMAINS.map((d) => `${d.label}: ${WORD[selected.s[d.id]]}`).join(' · ')}
              </span>
            </div>
          )}

          <p className="font-caption text-caption text-muted-text pt-3">
            Filled = good · half = partial · outline = missed · dash = not logged
          </p>
        </div>
      )}
    </section>
  );
};
