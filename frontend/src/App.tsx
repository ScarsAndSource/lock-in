import React from 'react';
import { useApp } from './context/AppContext';
import { Header } from './components/Header';
import { BottomNav } from './components/BottomNav';
import { CheckinModal } from './components/CheckinModal';
import { UrgeQuickModal } from './components/UrgeQuickModal';
import { Toast } from './components/Toast';
import { TodayView } from './views/TodayView';
import { TrackView } from './views/TrackView';
import { ReviewView } from './views/ReviewView';
import { ChatView } from './views/ChatView';
import { MoreView } from './views/MoreView';

export const AppContent: React.FC = () => {
  const {
    activeTab,
    setActiveTab,
    checkinModalOpen,
    setCheckinModalOpen,
    urgeQuickModalOpen,
    setUrgeQuickModalOpen,
  } = useApp();

  const getTitle = () => {
    switch (activeTab) {
      case 'today':
        return 'Today';
      case 'track':
        return 'Track';
      case 'review':
        return 'Review';
      case 'chat':
        return 'Chat';
      case 'more':
        return 'More';
      default:
        return 'Lock’in';
    }
  };

  return (
    <div className="bg-ground-chalk font-body-default text-ink flex flex-col min-h-screen">
      {/* Top Header */}
      <Header title={getTitle()} onProfileClick={() => setActiveTab('more')} />

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col w-full pt-16 pb-20 px-margin bg-ground-chalk">
        {activeTab === 'today' && <TodayView />}
        {activeTab === 'track' && <TrackView />}
        {activeTab === 'review' && <ReviewView />}
        {activeTab === 'chat' && <ChatView />}
        {activeTab === 'more' && <MoreView />}
      </main>

      {/* Fixed Bottom Navigation */}
      <BottomNav />

      {/* Checkin and Urge Quick Modals */}
      <CheckinModal
        isOpen={checkinModalOpen}
        onClose={() => setCheckinModalOpen(false)}
      />
      <UrgeQuickModal
        isOpen={urgeQuickModalOpen}
        onClose={() => setUrgeQuickModalOpen(false)}
      />

      {/* Toast Notification */}
      <Toast />
    </div>
  );
};
