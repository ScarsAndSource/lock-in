import React from 'react';
import { useApp } from '../context/AppContext';

interface HeaderProps {
  title?: string;
  onProfileClick?: () => void;
}

export const Header: React.FC<HeaderProps> = ({ title = 'Today', onProfileClick }) => {
  const { demoMode, toggleDemoMode } = useApp();

  return (
    <header className="fixed top-0 w-full z-40 bg-surface pt-safe border-b border-surface-container">
      <div className="h-14 px-margin flex items-center justify-between max-w-md mx-auto">
        <div className="flex flex-col justify-center">
          <span className="font-caption text-caption text-muted-text uppercase tracking-wider">
            LOCK'IN WEAVE
          </span>
          <h1 className="font-section text-section text-ink leading-tight">{title}</h1>
        </div>
        <div className="flex items-center gap-space-xs">
          <button
            type="button"
            onClick={() => toggleDemoMode(!demoMode)}
            title={demoMode ? 'Demo Mode (Click to switch to live API)' : 'Live API Mode (Click to switch to Demo)'}
            className={`px-2 py-0.5 rounded text-[11px] font-caption uppercase tracking-wider font-semibold transition-colors ${
              demoMode
                ? 'bg-surface-container text-muted-text hover:bg-secondary-fixed'
                : 'bg-domain-study-tint text-domain-study-fill'
            }`}
          >
            {demoMode ? 'Demo' : 'Live'}
          </button>
          <button
            type="button"
            onClick={onProfileClick}
            aria-label="Profile settings"
            className="w-8 h-8 rounded-full bg-ink flex items-center justify-center hover:opacity-90 transition-opacity"
          >
            <span className="material-symbols-outlined text-ground-chalk text-[18px]">person</span>
          </button>
        </div>
      </div>
    </header>
  );
};
