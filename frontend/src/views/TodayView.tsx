import React from 'react';
import { useApp } from '../context/AppContext';
import { SevenDayWeave } from '../components/SevenDayWeave';
import { TodayEntries } from '../components/TodayEntries';

export const TodayView: React.FC = () => {
  const {
    checkinView,
    setCheckinModalOpen,
    setUrgeQuickModalOpen,
  } = useApp();

  const isConfirmed = checkinView?.already_confirmed;

  return (
    <div className="flex flex-col w-full pb-8 max-w-md mx-auto">
      {/* Day Context Header */}
      <div className="flex items-baseline justify-between pt-2 pb-5">
        <div className="flex flex-col">
          <span className="font-title text-title text-ink tracking-tight">Thu 31 Dec</span>
          <span className="font-small text-small text-muted-text mt-0.5">
            11:30 pm · Late evening
          </span>
        </div>
        <div className="flex items-center gap-1.5 px-2.5 py-1 bg-surface-container rounded">
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              isConfirmed ? 'bg-domain-study-fill' : 'bg-ink animate-pulse'
            }`}
          />
          <span className="font-caption text-caption text-ink uppercase tracking-wider font-semibold">
            {isConfirmed ? 'Locked in' : 'Unclosed'}
          </span>
        </div>
      </div>

      {/* Ink Slab Primary Action */}
      <section className="w-full bg-ink rounded-xl p-5 text-ground-chalk flex flex-col justify-between mb-8 shadow-sm">
        <div className="flex flex-col mb-6">
          <span className="font-caption text-caption text-surface-dim uppercase tracking-wider mb-2">
            Daily protocol
          </span>
          <h2 className="font-title text-title text-ground-chalk leading-tight mb-2">
            Today's check-in.
          </h2>
          <p className="font-small text-small text-surface-dim leading-relaxed">
            About a minute. No catch-up needed. Just today.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCheckinModalOpen(true)}
          className="w-full h-[52px] bg-ground-chalk text-ink rounded-xl font-body-strong text-body-strong flex items-center justify-between px-5 active:bg-surface-dim transition-colors hover:bg-surface-bright"
        >
          <span>{isConfirmed ? 'Review today’s check-in' : 'Start check-in'}</span>
          <span className="material-symbols-outlined text-ink text-[20px]">arrow_forward</span>
        </button>
      </section>

      {/* 7-Day Weave Signature Matrix */}
      <SevenDayWeave />

      {/* Today's Domains Quick List */}
      <TodayEntries
        onOpenCheckin={() => setCheckinModalOpen(true)}
        onOpenUrgeCapture={() => setUrgeQuickModalOpen(true)}
      />

      {/* Footnote Ledger Status */}
      <div className="w-full flex items-center justify-between px-2 pt-2 text-muted-text font-caption text-caption">
        <span>Day record #412</span>
        <span>Auto-archives at 03:00 am</span>
      </div>
    </div>
  );
};
