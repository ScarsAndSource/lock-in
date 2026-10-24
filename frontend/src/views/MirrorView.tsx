import React, { lazy, Suspense, useEffect, useState } from 'react';
import { useApp } from '../context/AppContext';
import type { DomainKey } from '../context/AppContext';
import { WeeklyRetro } from '../components/WeeklyRetro';
import { SevenDayWeave } from '../components/SevenDayWeave';
import { ExperimentCard } from '../components/ExperimentCard';
import { PatternsFeed } from '../components/PatternsFeed';
import { InsightsFeed } from '../components/InsightsFeed';
import { getActiveMission } from '../api/profile';
import type { MissionDetail } from '../types';
import { MIRROR_SECTION_KEY } from '../api/growth';
import { useJourney } from '../hooks/useJourney';

const GrowthPanel = lazy(() => import('../components/growth/GrowthPanel').then((m) => ({ default: m.GrowthPanel })));
const JourneyPanel = lazy(() => import('../components/journey/JourneyPanel').then((m) => ({ default: m.JourneyPanel })));

const DOMAIN_TILES: { key: DomainKey; label: string; dot: string }[] = [
  { key: 'habits', label: 'Habits', dot: 'bg-domain-habits-fill' },
  { key: 'sleep', label: 'Sleep', dot: 'bg-domain-sleep-fill' },
  { key: 'screen', label: 'Screen', dot: 'bg-domain-screen-fill' },
  { key: 'study', label: 'Study', dot: 'bg-domain-study-fill' },
  { key: 'urges', label: 'Urges', dot: 'bg-domain-urges-fill' },
  { key: 'pauses', label: 'Pauses', dot: 'bg-ink' },
];

type Lens = 'insights' | 'patterns';

const MirrorOverview: React.FC = () => {
  const { openDomain, demoMode, dataEpoch } = useApp();
  const [mission, setMission] = useState<MissionDetail | null>(null);
  const [lens, setLens] = useState<Lens>('insights');

  useEffect(() => {
    let cancelled = false;
    getActiveMission()
      .then((m) => {
        if (!cancelled) setMission(m);
      })
      .catch(() => {
        if (!cancelled) setMission(null);
      });
    return () => {
      cancelled = true;
    };
  }, [demoMode, dataEpoch]);

  return (
    <div className="flex flex-col w-full pb-24 max-w-md mx-auto space-y-5 animate-fadeIn">
      <WeeklyRetro />

      {mission && (
        <section className="bg-surface rounded-xl p-4 border border-line space-y-2">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <span className="font-caption text-caption text-muted-text uppercase tracking-wider block">Mission</span>
              <h3 className="font-section text-section text-ink truncate">{mission.mission.title}</h3>
            </div>
            <span className="px-2.5 py-1 rounded bg-domain-study-tint text-domain-study-fill font-caption text-caption font-semibold shrink-0">
              Day {mission.progress.day_number}/{mission.progress.days_total}
            </span>
          </div>
          <div className="w-full bg-surface-container rounded-full h-2 overflow-hidden">
            <div className="bg-ink h-full rounded-full transition-all" style={{ width: `${mission.progress.elapsed_pct}%` }} />
          </div>
          <div className="flex justify-between font-caption text-caption text-muted-text">
            <span>{mission.progress.phase}</span>
            <span>
              {mission.progress.next_checkpoint
                ? `Next: ${mission.progress.next_checkpoint.label} (${mission.progress.next_checkpoint.checkpoint_date})`
                : `${mission.progress.days_left} days left`}
            </span>
          </div>
        </section>
      )}

      <SevenDayWeave days={14} defaultExpanded />

      <ExperimentCard />

      <section className="space-y-2">
        <h3 className="font-section text-section text-ink">Log and review</h3>
        <div className="grid grid-cols-3 gap-2">
          {DOMAIN_TILES.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => openDomain(t.key)}
              className="h-14 px-3 bg-surface border border-line rounded-xl flex items-center gap-2 hover:bg-surface-container-low transition-colors"
            >
              <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${t.dot}`} />
              <span className="font-small-medium text-small-medium text-ink truncate">{t.label}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center bg-surface-container p-0.5 rounded-lg">
          {(['insights', 'patterns'] as Lens[]).map((l) => (
            <button
              key={l}
              type="button"
              onClick={() => setLens(l)}
              className={`flex-1 h-9 rounded font-caption text-caption capitalize transition-colors ${
                lens === l ? 'bg-ink text-ground-chalk font-semibold' : 'text-ink'
              }`}
            >
              {l}
            </button>
          ))}
        </div>
        {lens === 'insights' ? <InsightsFeed /> : <PatternsFeed />}
      </section>
    </div>
  );
};

type Section = 'overview' | 'growth' | 'journey';

/** Mirror sub-tabs: the review screen untouched, Growth for reflective extras, Journey for seasons and the shelf. */
export const MirrorView: React.FC = () => {
  const { stage } = useJourney();
  const [section, setSection] = useState<Section>(() => {
    try {
      const stored = sessionStorage.getItem(MIRROR_SECTION_KEY);
      return stored === 'growth' || stored === 'journey' ? stored : 'overview';
    } catch {
      return 'overview';
    }
  });

  useEffect(() => {
    try {
      sessionStorage.removeItem(MIRROR_SECTION_KEY); // the hand-off from the Now prompt is one-shot
    } catch {
      /* ignore */
    }
  }, []);

  // Growth and Journey unlock at stage 3 (existing accounts and "show everything" start there).
  const sections: Section[] = stage >= 3 ? ['overview', 'growth', 'journey'] : ['overview'];
  const active: Section = sections.includes(section) ? section : 'overview';
  const loading = <p className="py-10 text-center font-small text-muted-text">Loading…</p>;

  return (
    <div className="flex flex-col w-full max-w-md mx-auto space-y-4">
      {sections.length > 1 && (
        <div className="flex items-center bg-surface-container p-0.5 rounded-lg">
          {sections.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSection(s)}
              className={`flex-1 h-9 rounded font-caption text-caption capitalize transition-colors ${
                active === s ? 'bg-ink text-ground-chalk font-semibold' : 'text-ink'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      )}
      {active === 'overview' && <MirrorOverview />}
      {active === 'growth' && (
        <Suspense fallback={loading}>
          <GrowthPanel />
        </Suspense>
      )}
      {active === 'journey' && (
        <Suspense fallback={loading}>
          <JourneyPanel />
        </Suspense>
      )}
    </div>
  );
};
