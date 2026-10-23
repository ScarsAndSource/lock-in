import React, { useEffect, useState } from 'react';
import { useApp } from '../../context/AppContext';
import {
  MIRROR_SECTION_KEY, deferAutopsy, getGrowthPrompt, identitySnoozed, promptsEnabled, snoozeIdentity,
} from '../../api/growth';
import type { GrowthPrompt } from '../../api/growth';
import { CLS } from './ui';

/** The ONE ask slot on Now: a habit check-up first, else the identity question, else nothing at all. */
export const GentlePrompt: React.FC = () => {
  const { demoMode, dataEpoch, setActiveTab } = useApp();
  const [prompt, setPrompt] = useState<GrowthPrompt | null>(null);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    if (demoMode || !promptsEnabled()) return;
    let cancelled = false;
    getGrowthPrompt()
      .then((p) => {
        if (!cancelled) setPrompt(p);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [demoMode, dataEpoch]);

  if (hidden || !prompt) return null;

  const autopsy = prompt.autopsy;
  const showIdentity = !autopsy && prompt.identity_due && !identitySnoozed();
  if (!autopsy && !showIdentity) return null;

  const openGrowth = () => {
    try {
      sessionStorage.setItem(MIRROR_SECTION_KEY, 'growth');
    } catch {
      /* the Growth tab is still one tap away */
    }
    setActiveTab('mirror');
  };

  const later = () => {
    if (autopsy) deferAutopsy(autopsy.id, false).catch(() => undefined);
    else snoozeIdentity(7);
    setHidden(true);
  };

  return (
    <section className="w-full bg-surface rounded-xl px-4 py-3 border border-line space-y-2">
      <p className="font-small-medium text-small-medium text-ink">
        {autopsy
          ? `“${autopsy.habit_name}” has been rough for a few weeks. Want a 30-second fix?`
          : 'One minute to write down your “why”? It shows up in your weekly review.'}
      </p>
      <div className="flex gap-2">
        <button type="button" className={`${CLS.primary} h-9 px-4 text-small`} onClick={openGrowth}>
          {autopsy ? 'Fix it' : 'Set it up'}
        </button>
        <button type="button" className={CLS.ghost} onClick={later}>
          Later
        </button>
      </div>
    </section>
  );
};
