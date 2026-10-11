import React from 'react';
import { useApp } from '../context/AppContext';

export const BottomNav: React.FC = () => {
  const { activeTab, setActiveTab } = useApp();

  const navItems = [
    { key: 'today', label: 'Today', icon: 'today' },
    { key: 'track', label: 'Track', icon: 'data_exploration' },
    { key: 'review', label: 'Review', icon: 'fact_check' },
    { key: 'chat', label: 'Chat', icon: 'chat_bubble_outline' },
    { key: 'more', label: 'More', icon: 'more_horiz' },
  ] as const;

  return (
    <nav
      className="fixed bottom-0 w-full z-50 pb-safe bg-surface border-t border-surface-container"
      data-active-classes="text-ink font-body-medium before:content-[''] before:absolute before:top-0 before:inset-x-0 before:h-[3px] before:bg-ink"
    >
      <div className="flex items-stretch justify-around h-16 w-full max-w-md mx-auto">
        {navItems.map((item) => {
          const isActive = activeTab === item.key;
          return (
            <button
              key={item.key}
              type="button"
              data-path={item.key}
              aria-current={isActive ? 'page' : undefined}
              onClick={() => setActiveTab(item.key)}
              className={`relative flex-1 flex flex-col items-center justify-center min-w-[44px] min-h-[44px] transition-colors ${
                isActive
                  ? "text-ink font-body-medium before:content-[''] before:absolute before:top-0 before:inset-x-0 before:h-[3px] before:bg-ink"
                  : 'text-muted-text hover:text-ink'
              }`}
            >
              <span className="material-symbols-outlined text-[20px] mb-0.5">{item.icon}</span>
              <span className="font-caption text-caption">{item.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
