import React from 'react';
import { useApp } from '../context/AppContext';
import { usePendingSync } from '../hooks/usePendingSync';

interface HeaderProps {
  title?: string;
  onProfileClick?: () => void;
}

export const Header: React.FC<HeaderProps> = ({ title = 'Now', onProfileClick }) => {
  const { demoMode, token } = useApp();
  const pending = usePendingSync(token);

  return (
    <header className="fixed top-0 w-full z-40 bg-surface pt-safe border-b border-surface-container">
      <div className="h-14 px-margin flex items-center justify-between max-w-md mx-auto">
        <h1 className="font-section text-section text-ink leading-tight">{title}</h1>
        <div className="flex items-center gap-space-xs">
          {pending > 0 && (
            <span
              role="status"
              title="Saved on this phone, waiting for a connection"
              className="px-2 py-0.5 rounded text-[11px] font-caption font-semibold bg-surface-container text-muted-text flex items-center gap-1"
            >
              <span className="material-symbols-outlined text-[13px]">cloud_off</span>
              {pending} to sync
            </span>
          )}
          {demoMode && (
            <span className="px-2 py-0.5 rounded text-[11px] font-caption uppercase tracking-wider font-semibold bg-surface-container text-muted-text">
              Demo
            </span>
          )}
          <button
            type="button"
            onClick={onProfileClick}
            aria-label="Settings"
            className="w-9 h-9 rounded-full bg-ink flex items-center justify-center hover:opacity-90 transition-opacity"
          >
            <span className="material-symbols-outlined text-ground-chalk text-[18px]">person</span>
          </button>
        </div>
      </div>
    </header>
  );
};
