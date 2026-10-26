import React, { createContext, useContext, useState, useEffect, useRef, useCallback, ReactNode } from 'react';
import { isDemoMode, setDemoMode, getAuthToken, setAuthToken } from '../api/client';
import { ApiError } from '../api/client';
import { getCheckinDefaults } from '../api/checkins';
import { getProfile } from '../api/profile';
import { CheckinView, Profile } from '../types';
import { localTodayISO } from '../lib/dates';
import { errorMessage } from '../lib/format';

export type Tab = 'now' | 'companion' | 'mirror' | 'crew';
export type DomainKey = 'habits' | 'sleep' | 'screen' | 'study' | 'urges' | 'pauses';

interface AppContextType {
  activeTab: Tab;
  setActiveTab: (tab: Tab) => void;
  activeDate: string;
  setActiveDate: (date: string) => void;
  checkinModalOpen: boolean;
  setCheckinModalOpen: (open: boolean) => void;
  urgeQuickModalOpen: boolean;
  setUrgeQuickModalOpen: (open: boolean) => void;
  settingsOpen: boolean;
  setSettingsOpen: (open: boolean) => void;
  domainSheet: DomainKey | null;
  openDomain: (key: DomainKey) => void;
  closeDomain: () => void;
  demoMode: boolean;
  toggleDemoMode: (val: boolean) => void;
  token: string | null;
  saveToken: (token: string | null) => void;
  profile: Profile | null;
  checkinView: CheckinView | null;
  checkinLoading: boolean;
  refreshCheckinView: () => Promise<void>;
  dataEpoch: number;
  bumpData: () => void;
  toastMessage: string | null;
  showToast: (msg: string) => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [activeTab, setActiveTab] = useState<Tab>('now');
  const [activeDate, setActiveDate] = useState<string>(localTodayISO());
  const [checkinModalOpen, setCheckinModalOpen] = useState(false);
  const [urgeQuickModalOpen, setUrgeQuickModalOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [domainSheet, setDomainSheet] = useState<DomainKey | null>(null);
  const [demoMode, setDemoModeState] = useState(isDemoMode());
  const [token, setTokenState] = useState<string | null>(getAuthToken());
  const [profile, setProfile] = useState<Profile | null>(null);
  const [checkinView, setCheckinView] = useState<CheckinView | null>(null);
  const checkinViewRef = useRef<CheckinView | null>(null);
  checkinViewRef.current = checkinView;
  const [checkinLoading, setCheckinLoading] = useState(false);
  const [dataEpoch, setDataEpoch] = useState(0);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const toastTimer = useRef<number | null>(null);
  const checkinSeq = useRef(0);

  const bumpData = useCallback(() => setDataEpoch((n) => n + 1), []);
  const openDomain = useCallback((key: DomainKey) => setDomainSheet(key), []);
  const closeDomain = useCallback(() => setDomainSheet(null), []);

  const showToast = useCallback((msg: string) => {
    setToastMessage(msg);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => {
      setToastMessage((curr) => (curr === msg ? null : curr));
    }, 3200);
  }, []);

  const toggleDemoMode = (val: boolean) => {
    setDemoMode(val);
    setDemoModeState(val);
    setCheckinView(null);
    showToast(val ? 'Switched to local demo data' : 'Switched to live backend API');
  };

  const saveToken = (newToken: string | null) => {
    setAuthToken(newToken);
    setTokenState(newToken);
    showToast(newToken ? 'Bearer token saved' : 'Token cleared');
  };

  const refreshCheckinView = useCallback(async () => {
    if (!isDemoMode() && !getAuthToken()) {
      setCheckinView(null); // signed out: the login screen is showing, nothing to load
      return;
    }
    // Responses can arrive out of order (the profile fetch changes activeDate mid-flight); only the latest counts.
    const seq = ++checkinSeq.current;
    setCheckinLoading(true);
    try {
      const view = await getCheckinDefaults(activeDate);
      if (seq !== checkinSeq.current) return;
      setCheckinView(view);
    } catch (err) {
      if (seq !== checkinSeq.current) return;
      if (err instanceof ApiError && err.status === 0 && checkinViewRef.current) return;
      setCheckinView(null);
      if (!isDemoMode()) {
        showToast(errorMessage(err, 'Could not load today’s check-in'));
      }
    } finally {
      if (seq === checkinSeq.current) setCheckinLoading(false);
    }
  }, [activeDate, showToast]);

  useEffect(() => {
    let cancelled = false;
    if (!isDemoMode() && !getAuthToken()) return; // signed out: nothing to load
    (async () => {
      try {
        const p = await getProfile();
        if (cancelled) return;
        setProfile(p);
        if (p.today && p.today !== activeDate) {
          setActiveDate(p.today);
        }
      } catch {
        if (!cancelled) {
          setProfile(null);
          setActiveDate(localTodayISO());
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload identity, not every date change
  }, [demoMode, token]);

  useEffect(() => {
    refreshCheckinView();
  }, [refreshCheckinView, demoMode, token, dataEpoch]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const shortcut = params.get('shortcut');
    if (shortcut === 'urge-quick') {
      setUrgeQuickModalOpen(true);
    } else if (shortcut === 'checkin') {
      setCheckinModalOpen(true);
    }
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimer.current) window.clearTimeout(toastTimer.current);
    };
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
        settingsOpen,
        setSettingsOpen,
        domainSheet,
        openDomain,
        closeDomain,
        demoMode,
        toggleDemoMode,
        token,
        saveToken,
        profile,
        checkinView,
        checkinLoading,
        refreshCheckinView,
        dataEpoch,
        bumpData,
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
