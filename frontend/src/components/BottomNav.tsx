import React from 'react';
import { useApp } from '../context/AppContext';
import type { Tab } from '../context/AppContext';

const NAV_ITEMS: { key: Tab; label: string; icon: string }[] = [
  { key: 'now', label: 'Now', icon: 'today' },
  { key: 'companion', label: 'Companion', icon: 'chat_bubble_outline' },
  { key: 'mirror', label: 'Mirror', icon: 'insights' },
];

export const BottomNav: React.FC = () => {
  const { activeTab, setActiveTab } = useApp();

  return (
    <nav className="fixed bottom-0 w-full z-50 pb-safe bg-surface border-t border-surface-container">
      <div className="flex items-stretch justify-around h-16 w-full max-w-md mx-auto">
        {NAV_ITEMS.map((item) => {
          const isActive = activeTab === item.key;
          return (
            <button
              key={item.key}
              type="button"
              aria-current={isActive ? 'page' : undefined}
              onClick={() => setActiveTab(item.key)}
              className={`relative flex-1 flex flex-col items-center justify-center min-w-[44px] min-h-[44px] transition-colors ${
                isActive
                  ? "text-ink font-body-medium before:content-[''] before:absolute before:top-0 before:inset-x-0 before:h-[3px] before:bg-ink"
                  : 'text-muted-text hover:text-ink'
              }`}
            >
              <span className="material-symbols-outlined text-[22px] mb-0.5">{item.icon}</span>
              <span className="font-caption text-caption">{item.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
