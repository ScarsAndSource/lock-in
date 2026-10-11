import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { isDemoMode, setDemoMode, getAuthToken, setAuthToken } from '../api/client';
import { getCheckinDefaults } from '../api/checkins';
import { CheckinView } from '../types';

interface AppContextType {
  activeTab: 'today' | 'track' | 'review' | 'chat' | 'more';
  setActiveTab: (tab: 'today' | 'track' | 'review' | 'chat' | 'more') => void;
  activeDate: string;
  setActiveDate: (date: string) => void;
  checkinModalOpen: boolean;
  setCheckinModalOpen: (open: boolean) => void;
  urgeQuickModalOpen: boolean;
  setUrgeQuickModalOpen: (open: boolean) => void;
  demoMode: boolean;
  toggleDemoMode: (val: boolean) => void;
  token: string | null;
  saveToken: (token: string | null) => void;
  checkinView: CheckinView | null;
  refreshCheckinView: () => Promise<void>;
  toastMessage: string | null;
  showToast: (msg: string) => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [activeTab, setActiveTab] = useState<'today' | 'track' | 'review' | 'chat' | 'more'>('today');
  const [activeDate, setActiveDate] = useState<string>('2026-12-31');
  const [checkinModalOpen, setCheckinModalOpen] = useState(false);
  const [urgeQuickModalOpen, setUrgeQuickModalOpen] = useState(false);
  const [demoMode, setDemoModeState] = useState(isDemoMode());
  const [token, setTokenState] = useState<string | null>(getAuthToken());
  const [checkinView, setCheckinView] = useState<CheckinView | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage((curr) => (curr === msg ? null : curr));
    }, 3200);
  };

  const toggleDemoMode = (val: boolean) => {
    setDemoMode(val);
    setDemoModeState(val);
    showToast(val ? 'Switched to local demo data' : 'Switched to live backend API');
  };

  const saveToken = (newToken: string | null) => {
    setAuthToken(newToken);
    setTokenState(newToken);
    showToast(newToken ? 'Bearer token saved' : 'Token cleared');
  };

  const refreshCheckinView = async () => {
    try {
      const view = await getCheckinDefaults(activeDate);
      setCheckinView(view);
    } catch (err: any) {
      console.warn('Could not fetch checkin view:', err);
    }
  };

  useEffect(() => {
    refreshCheckinView();
  }, [activeDate, demoMode, token]);

  // Handle URL shortcut params (e.g. ?shortcut=urge-quick or ?shortcut=checkin)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const shortcut = params.get('shortcut');
    if (shortcut === 'urge-quick') {
      setUrgeQuickModalOpen(true);
    } else if (shortcut === 'checkin') {
      setCheckinModalOpen(true);
    }
  }, []);

  return (
    <AppContext.Provider
      value={{
        activeTab,
        setActiveTab,
        activeDate,
        setActiveDate,
        checkinModalOpen,
        setCheckinModalOpen,
        urgeQuickModalOpen,
        setUrgeQuickModalOpen,
        demoMode,
        toggleDemoMode,
        token,
        saveToken,
        checkinView,
        refreshCheckinView,
        toastMessage,
        showToast,
      }}
    >
      {children}
    </AppContext.Provider>
  );
};

export function useApp(): AppContextType {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
}
