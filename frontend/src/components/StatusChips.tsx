import React, { useEffect, useState } from 'react';
import { useApp } from '../context/AppContext';
import type { DomainKey } from '../context/AppContext';
import { getStudySessions } from '../api/tracking';
import { formatMinutes } from '../lib/format';

const Chip: React.FC<{ dot: string; label: string; value: string; onClick: () => void }> = ({
  dot,
  label,
  value,
  onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    className="flex-1 min-w-0 min-h-[56px] px-3 py-2 bg-surface border border-line rounded-xl text-left hover:bg-surface-container-low transition-colors"
  >
    <span className="flex items-center gap-1.5">
      <span className={`w-2 h-2 rounded-full ${dot}`} />
      <span className="font-caption text-caption text-muted-text">{label}</span>
    </span>
    <span className="font-small-medium text-small-medium text-ink block truncate">{value}</span>
  </button>
);

/** Sleep, screen and study at a glance. Tapping one opens its detail sheet, where it can be logged properly. */
export const StatusChips: React.FC = () => {
  const { checkinView, activeDate, dataEpoch, demoMode, openDomain } = useApp();
  const [studyMinutes, setStudyMinutes] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    getStudySessions(activeDate, 2)
      .then((sessions) => {
        if (cancelled) return;
        setStudyMinutes(sessions.filter((s) => s.log_date === activeDate).reduce((sum, s) => sum + s.actual_minutes, 0));
      })
      .catch(() => {
        if (!cancelled) setStudyMinutes(null);
      });
    return () => {
      cancelled = true;
    };
  }, [activeDate, dataEpoch, demoMode]);

  const sleep = checkinView?.sleep.logged ?? null;
  const screen = checkinView?.screen_time.logged ?? null;
  const approx = (guess: boolean, text: string) => (guess && text !== '—' ? `~${text}` : text);

  const go = (key: DomainKey) => () => openDomain(key);

  return (
    <div className="flex gap-2">
      <Chip
        dot="bg-domain-sleep-fill"
        label="Sleep"
        value={sleep ? approx(sleep.is_default, formatMinutes(sleep.duration_minutes)) : '—'}
        onClick={go('sleep')}
      />
      <Chip
        dot="bg-domain-screen-fill"
        label="Screen"
        value={screen ? approx(screen.is_default, formatMinutes(screen.total_minutes)) : '—'}
        onClick={go('screen')}
      />
      <Chip
        dot="bg-domain-study-fill"
        label="Study"
        value={studyMinutes === null ? '—' : studyMinutes === 0 ? 'None yet' : formatMinutes(studyMinutes)}
        onClick={go('study')}
      />
    </div>
  );
};
