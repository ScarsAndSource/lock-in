import React from 'react';
import { useApp } from '../context/AppContext';

export const Toast: React.FC = () => {
  const { toastMessage } = useApp();

  if (!toastMessage) return null;

  return (
    <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-[80] pointer-events-none animate-fadeIn">
      <div className="px-4 py-2.5 rounded-xl bg-ink text-ground-chalk font-caption text-caption shadow-xl flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-domain-study-tint shrink-0" />
        <span>{toastMessage}</span>
      </div>
    </div>
  );
};
