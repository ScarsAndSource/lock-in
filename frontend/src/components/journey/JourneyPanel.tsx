import React, { useState } from 'react';
import { useApp } from '../../context/AppContext';
import { useJourney } from '../../hooks/useJourney';
import { CLS } from '../growth/ui';
import { RadarCard } from './RadarCard';
import { SeasonCard } from './SeasonCard';
import { ShelfCard } from './ShelfCard';
import { SnapshotCard } from './SnapshotCard';

type FoldKey = 'season' | 'radar' | 'snapshot' | 'shelf';

const Fold: React.FC<{
  title: string;
  hint: string;
  icon: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}> = ({ title, hint, icon, open, onToggle, children }) => (
  <section className="bg-surface rounded-xl border border-line overflow-hidden">
    <button type="button" onClick={onToggle} aria-expanded={open} className="w-full px-4 py-3 flex items-center gap-3 text-left">
      <span className="material-symbols-outlined text-[20px] text-ink shrink-0">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="font-section text-section text-ink block truncate">{title}</span>
        <span className={`${CLS.muted} block truncate`}>{hint}</span>
      </span>
      <span className="material-symbols-outlined text-[20px] text-muted-text shrink-0">{open ? 'expand_less' : 'expand_more'}</span>
    </button>
    {open && <div className="px-4 pb-4">{children}</div>}
  </section>
);

/** The Journey sub-tab of Mirror: Season, exam radar, monthly snapshot, Done Becoming shelf. All folded shut. */
export const JourneyPanel: React.FC = () => {
  const { demoMode } = useApp();
  const { state, showAll, setShowAll } = useJourney();
  const [open, setOpen] = useState<FoldKey | null>(null);
  const toggle = (k: FoldKey) => setOpen((cur) => (cur === k ? null : k));

  if (demoMode) {
    return <p className="py-10 text-center font-small text-muted-text">Journey needs a real account, because it keeps your private notes. Sign in to use it.</p>;
  }

  return (
    <div className="flex flex-col w-full pb-24 space-y-3 animate-fadeIn">
      <Fold title="Season" hint="6 weeks, 3 focus habits, then an easy week" icon="event_repeat" open={open === 'season'} onToggle={() => toggle('season')}>
        <SeasonCard state={state} />
      </Fold>
      <Fold title="Exam radar" hint="Topic names that will come, brought back on schedule" icon="radar" open={open === 'radar'} onToggle={() => toggle('radar')}>
        <RadarCard />
      </Fold>
      <Fold title="Monthly snapshot" hint="Six questions, your 30/60/90 day change" icon="monitoring" open={open === 'snapshot'} onToggle={() => toggle('snapshot')}>
        <SnapshotCard />
      </Fold>
      <Fold title="Done becoming" hint="Habits that run on their own" icon="workspace_premium" open={open === 'shelf'} onToggle={() => toggle('shelf')}>
        <ShelfCard />
      </Fold>

      <label className="flex items-center justify-between gap-3 px-1 pt-2">
        <span className={CLS.muted}>Show every feature now (skip the slow unlock)</span>
        <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} className="w-5 h-5 accent-black" />
      </label>
    </div>
  );
};