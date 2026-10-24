import React from 'react';
import { useApp } from '../context/AppContext';
import type { Tab } from '../context/AppContext';
import { useCrew } from '../context/CrewContext';
import { BUDDY_NAME } from './Buddy';
import { MarutiRoamer } from './maruti/MarutiRoamer';

const NAV_ITEMS: { key: Tab; label: string; icon: string }[] = [
  { key: 'now', label: 'Now', icon: 'today' },
  { key: 'companion', label: BUDDY_NAME, icon: 'chat_bubble_outline' },
  { key: 'mirror', label: 'Mirror', icon: 'insights' },
  { key: 'crew', label: 'Crew', icon: 'group' },
];

export const BottomNav: React.FC = () => {
  const { activeTab, setActiveTab } = useApp();
  const { attention } = useCrew();

  return (
    <>
      <MarutiRoamer />
      <nav className="fixed bottom-0 w-full z-50 pb-safe bg-surface border-t border-surface-container">
        <div className="flex items-stretch justify-around h-16 w-full max-w-md mx-auto">
          {NAV_ITEMS.map((item) => {
            const isActive = activeTab === item.key;
            const badge = item.key === 'crew' && attention > 0 ? attention : 0;
            return (
              <button
                key={item.key}
                type="button"
                aria-current={isActive ? 'page' : undefined}
                aria-label={badge ? `${item.label}, ${badge} waiting` : item.label}
                onClick={() => setActiveTab(item.key)}
                className={`relative flex-1 flex flex-col items-center justify-center min-w-[44px] min-h-[44px] transition-colors ${
                  isActive
                    ? "text-ink font-body-medium before:content-[''] before:absolute before:top-0 before:inset-x-0 before:h-[3px] before:bg-ink"
                    : 'text-muted-text hover:text-ink'
                }`}
              >
                <span className="relative">
                  <span className="material-symbols-outlined text-[22px] mb-0.5 block">{item.icon}</span>
                  {badge > 0 && (
                    <span
                      aria-hidden="true"
                      className="absolute -top-1 -right-2.5 min-w-[16px] h-4 px-1 rounded-full bg-domain-habits-fill text-ground-chalk font-caption text-[10px] leading-4 text-center"
                    >
                      {badge > 9 ? '9+' : badge}
                    </span>
                  )}
                </span>
                <span className="font-caption text-caption">{item.label}</span>
              </button>
            );
          })}
        </div>
      </nav>
    </>
  );
};
