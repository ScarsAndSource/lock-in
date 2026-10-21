import React from 'react';
import { useApp } from '../context/AppContext';

/** Always one tap away, never part of a list. Opens the 2-tap urge capture. */
export const UrgeFab: React.FC = () => {
  const { setUrgeQuickModalOpen } = useApp();
  return (
    <button
      type="button"
      aria-label="Urge quick capture"
      onClick={() => setUrgeQuickModalOpen(true)}
      style={{ bottom: 'calc(4.75rem + env(safe-area-inset-bottom, 0px))' }}
      className="fixed right-4 z-40 w-12 h-12 rounded-full bg-domain-urges-fill text-ground-chalk shadow-lg flex items-center justify-center active:scale-95 transition-transform"
    >
      <span className="material-symbols-outlined text-[22px]">shield</span>
    </button>
  );
};
