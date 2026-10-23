import React, { useCallback, useEffect, useState } from 'react';
import { useApp } from '../../context/AppContext';
import { getGrowthPrompt, promptsEnabled, setPromptsEnabled } from '../../api/growth';
import type { GrowthAutopsy } from '../../api/growth';
import { AutopsyCard } from './AutopsyCard';
import { IdentityCard } from './IdentityCard';
import { JournalJar } from './JournalJar';
import { FutureSelfCard } from './FutureSelfCard';
import { CLS } from './ui';

type FoldKey = 'checkup' | 'identity' | 'notes' | 'future';

interface FoldProps {
  title: string;
  hint: string;
  icon: string;
  open: boolean;
  onToggle: () => void;
  badge?: string;
  children: React.ReactNode;
}

const Fold: React.FC<FoldProps> = ({ title, hint, icon, open, onToggle, badge, children }) => (
  <section className="bg-surface rounded-xl border border-line overflow-hidden">
    <button type="button" onClick={onToggle} aria-expanded={open} className="w-full px-4 py-3 flex items-center gap-3 text-left">
      <span className="material-symbols-outlined text-[20px] text-ink shrink-0">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="font-section text-section text-ink block truncate">{title}</span>
        <span className={`${CLS.muted} block truncate`}>{hint}</span>
      </span>
      {badge && (
        <span className="px-2 py-0.5 rounded bg-domain-study-tint text-domain-study-fill font-caption text-caption font-semibold shrink-0">
          {badge}
        </span>
      )}
      <span className="material-symbols-outlined text-[20px] text-muted-text shrink-0">
        {open ? 'expand_less' : 'expand_more'}
      </span>
    </button>
    {open && <div className="px-4 pb-4">{children}</div>}
  </section>
);

/** The Growth sub-tab of Mirror. Everything is folded shut except a pending habit check-up. */
export const GrowthPanel: React.FC = () => {
  const { demoMode, dataEpoch } = useApp();
  const [autopsy, setAutopsy] = useState<GrowthAutopsy | null>(null);
  const [open, setOpen] = useState<FoldKey | null>(null);
  const [prompts, setPrompts] = useState<boolean>(promptsEnabled());

  const loadPrompt = useCallback(() => {
    if (demoMode) return;
    getGrowthPrompt()
      .then((p) => {
        setAutopsy(p.autopsy);
        if (p.autopsy) setOpen((cur) => cur ?? 'checkup');
      })
      .catch(() => setAutopsy(null));
  }, [demoMode]);

  useEffect(() => {
    loadPrompt();
  }, [loadPrompt, dataEpoch]);

  if (demoMode) {
    return (
      <p className="py-10 text-center font-small text-muted-text">
        Growth needs a real account, because it keeps your private notes. Sign in to use it.
      </p>
    );
  }

  const toggle = (k: FoldKey) => setOpen((cur) => (cur === k ? null : k));

  return (
    <div className="flex flex-col w-full pb-24 space-y-3 animate-fadeIn">
      {autopsy && (
        <Fold
          title="Habit check-up"
          hint={`“${autopsy.habit_name}” has been rough lately`}
          icon="healing"
          badge="1 waiting"
          open={open === 'checkup'}
          onToggle={() => toggle('checkup')}
        >
          <AutopsyCard
            autopsy={autopsy}
            onDone={() => {
              setAutopsy(null);
              setOpen(null);
            }}
          />
        </Fold>
      )}

      <Fold title="Who I’m becoming" hint="Your why, in one sentence" icon="flag" open={open === 'identity'} onToggle={() => toggle('identity')}>
        <IdentityCard />
      </Fold>

      <Fold title="Little notes" hint="One tiny thing a day, no pressure" icon="edit_note" open={open === 'notes'} onToggle={() => toggle('notes')}>
        <JournalJar />
      </Fold>

      <Fold title="Notes to future me" hint="Played right when you usually slip" icon="schedule_send" open={open === 'future'} onToggle={() => toggle('future')}>
        <FutureSelfCard />
      </Fold>

      <label className="flex items-center justify-between gap-3 px-1 pt-2">
        <span className={CLS.muted}>Show gentle prompts on Now</span>
        <input
          type="checkbox"
          checked={prompts}
          onChange={(e) => {
            setPrompts(e.target.checked);
            setPromptsEnabled(e.target.checked);
          }}
          className="w-5 h-5 accent-black"
        />
      </label>
    </div>
  );
};
