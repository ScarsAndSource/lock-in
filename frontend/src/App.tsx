import React, { lazy, Suspense, useState } from 'react';
import { useApp } from './context/AppContext';
import { Header } from './components/Header';
import { BottomNav } from './components/BottomNav';
import { CheckinModal } from './components/CheckinModal';
import { UrgeQuickModal } from './components/UrgeQuickModal';
import { UrgeFab } from './components/UrgeFab';
import { Toast } from './components/Toast';
import { LoginScreen } from './components/LoginScreen';
import { useDeepLink } from './lib/deepLink';

// Each tab and sheet is its own chunk: a screen's code only downloads when it is first opened.
const NowView = lazy(() => import('./views/NowView').then((m) => ({ default: m.NowView })));
const ChatView = lazy(() => import('./views/ChatView').then((m) => ({ default: m.ChatView })));
const MirrorView = lazy(() => import('./views/MirrorView').then((m) => ({ default: m.MirrorView })));
const CrewView = lazy(() => import('./views/CrewView').then((m) => ({ default: m.CrewView })));
const SettingsSheet = lazy(() => import('./components/SettingsSheet').then((m) => ({ default: m.SettingsSheet })));
const DomainSheet = lazy(() => import('./components/DomainSheet').then((m) => ({ default: m.DomainSheet })));
const TriageSheet = lazy(() => import('./components/TriageSheet').then((m) => ({ default: m.TriageSheet })));
const FutureSelfPlayer = lazy(() => import('./components/growth/FutureSelfPlayer').then((m) => ({ default: m.FutureSelfPlayer })));

const TITLES = { now: 'Now', companion: 'Companion', mirror: 'Mirror', crew: 'Crew' } as const;

export const AppContent: React.FC = () => {
  const {
    activeTab,
    setActiveTab,
    openDomain,
    checkinModalOpen,
    setCheckinModalOpen,
    urgeQuickModalOpen,
    setUrgeQuickModalOpen,
    settingsOpen,
    setSettingsOpen,
    domainSheet,
    demoMode,
    token,
  } = useApp();

  const [triageOpen, setTriageOpen] = useState(false);
  const [futureId, setFutureId] = useState<string | null>(null);

  // A notification body tap lands on /?a=<where>. Every push the companion sends names one of these, and on iPhone
  // (no lock-screen buttons) this is how the tap finishes the job. Must run before the signed-out early return.
  useDeepLink((link, params) => {
    switch (link) {
      case 'tasks':
        setActiveTab('now');
        setTriageOpen(true);
        break;
      case 'checkin':
        setCheckinModalOpen(true);
        break;
      case 'plan':
        setSettingsOpen(true);
        break;
      case 'sleep':
        openDomain('sleep');
        break;
      case 'study':
        openDomain('study');
        break;
      case 'insight':
        setActiveTab('mirror');
        break;
      case 'crew':
        setActiveTab('crew');
        break;
      case 'future':
        if (params?.id) setFutureId(params.id);
        break;
      default: // habit, focus, comeback: the Now tab shows the next thing itself
        setActiveTab('now');
    }
  });

  // Live mode with no session: login first. Demo mode is an explicit opt-in from the login screen.
  if (!demoMode && !token) {
    return <LoginScreen />;
  }

  return (
    <div className="bg-ground-chalk font-body-default text-ink flex flex-col min-h-screen">
      <Header title={TITLES[activeTab]} onProfileClick={() => setSettingsOpen(true)} />

      <main className="flex-1 flex flex-col w-full pt-16 pb-20 px-margin bg-ground-chalk">
        <Suspense fallback={<p className="py-10 text-center font-small text-muted-text">Loading…</p>}>
          {activeTab === 'now' && <NowView />}
          {activeTab === 'companion' && <ChatView />}
          {activeTab === 'mirror' && <MirrorView />}
          {activeTab === 'crew' && <CrewView />}
        </Suspense>
      </main>

      {activeTab !== 'companion' && <UrgeFab />}
      <BottomNav />

      <CheckinModal isOpen={checkinModalOpen} onClose={() => setCheckinModalOpen(false)} />
      <UrgeQuickModal isOpen={urgeQuickModalOpen} onClose={() => setUrgeQuickModalOpen(false)} />

      <Suspense fallback={null}>
        {domainSheet && <DomainSheet />}
        {settingsOpen && <SettingsSheet />}
        {triageOpen && <TriageSheet open onClose={() => setTriageOpen(false)} />}
        {futureId && <FutureSelfPlayer id={futureId} onClose={() => setFutureId(null)} />}
      </Suspense>

      <Toast />
    </div>
  );
};
