import React, { useState } from 'react';

export type CellStatus = 'good' | 'partial' | 'missed' | 'none';

export interface DayColumnData {
  dayLabel: string;
  dateStr: string;
  isToday?: boolean;
  habits: CellStatus;
  sleep: CellStatus;
  screen: CellStatus;
  study: CellStatus;
  urges: CellStatus;
}

const DEFAULT_DAYS: DayColumnData[] = [
  {
    dayLabel: 'F',
    dateStr: '25 Dec',
    habits: 'good',
    sleep: 'good',
    screen: 'partial',
    study: 'good',
    urges: 'good',
  },
  {
    dayLabel: 'S',
    dateStr: '26 Dec',
    habits: 'partial',
    sleep: 'good',
    screen: 'missed',
    study: 'none',
    urges: 'good',
  },
  {
    dayLabel: 'S',
    dateStr: '27 Dec',
    habits: 'missed',
    sleep: 'partial',
    screen: 'good',
    study: 'missed',
    urges: 'good',
  },
  {
    dayLabel: 'M',
    dateStr: '28 Dec',
    habits: 'good',
    sleep: 'good',
    screen: 'good',
    study: 'good',
    urges: 'partial',
  },
  {
    dayLabel: 'T',
    dateStr: '29 Dec',
    habits: 'good',
    sleep: 'partial',
    screen: 'good',
    study: 'good',
    urges: 'good',
  },
  {
    dayLabel: 'W',
    dateStr: '30 Dec',
    habits: 'good',
    sleep: 'good',
    screen: 'partial',
    study: 'partial',
    urges: 'missed',
  },
  {
    dayLabel: 'T',
    dateStr: '31 Dec',
    isToday: true,
    habits: 'good',
    sleep: 'good',
    screen: 'partial',
    study: 'none',
    urges: 'none',
  },
];

interface SevenDayWeaveProps {
  days?: DayColumnData[];
  onSelectDay?: (day: DayColumnData) => void;
}

export const SevenDayWeave: React.FC<SevenDayWeaveProps> = ({
  days = DEFAULT_DAYS,
  onSelectDay,
}) => {
  const [selectedDay, setSelectedDay] = useState<DayColumnData | null>(null);

  const handleDayClick = (day: DayColumnData) => {
    setSelectedDay(selectedDay?.dateStr === day.dateStr ? null : day);
    onSelectDay?.(day);
  };

  const renderCell = (
    status: CellStatus,
    domainFill: string,
    domainTint: string,
    domainStroke: string,
    isToday: boolean
  ) => {
    if (status === 'good') {
      return <div className={`w-[20px] h-[14px] rounded ${domainFill}`} />;
    }
    if (status === 'partial') {
      return (
        <div className={`w-[20px] h-[14px] rounded ${domainTint} overflow-hidden flex flex-col justify-end`}>
          <div className={`h-[7px] w-full ${domainFill}`} />
        </div>
      );
    }
    if (status === 'missed') {
      return (
        <div className="w-[20px] h-[14px] rounded bg-transparent flex items-center justify-center">
          <svg className="w-full h-full" height="14" viewBox="0 0 20 14" width="20">
            <rect fill="none" height="12" rx="3" stroke={domainStroke} strokeWidth="1.5" width="18" x="1" y="1" />
          </svg>
        </div>
      );
    }
    // 'none' or not logged
    return (
      <div className="w-[20px] h-[14px] flex items-center justify-center">
        <div className={`w-3 h-[1px] ${isToday ? 'bg-ink' : 'bg-outline-variant'}`} />
      </div>
    );
  };

  return (
    <section className="w-full bg-surface rounded-xl p-4 mb-6 shadow-sm border border-line">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-section text-section text-ink">Recent days</h3>
        <span className="font-caption text-caption text-muted-text tracking-wide uppercase">
          Past 7 days
        </span>
      </div>

      {/* Matrix: Domain Legend + 7 Columns */}
      <div className="flex items-stretch justify-between gap-2 overflow-x-auto pb-1">
        {/* Legend Column */}
        <div className="flex flex-col justify-between py-1 pr-1 shrink-0 select-none">
          {/* Habits */}
          <div className="h-[14px] flex items-center gap-2" title="Habits">
            <svg className="shrink-0" height="12" viewBox="0 0 12 12" width="12">
              <circle cx="6" cy="6" fill="#C84A21" r="5" />
            </svg>
            <span className="font-caption text-caption text-muted-text">Habits</span>
          </div>

          {/* Sleep */}
          <div className="h-[14px] flex items-center gap-2" title="Sleep">
            <svg className="shrink-0" height="12" viewBox="0 0 12 12" width="12">
              <path d="M 6 1 A 5 5 0 0 1 6 11 Z" fill="#1D5F73" />
            </svg>
            <span className="font-caption text-caption text-muted-text">Sleep</span>
          </div>

          {/* Screen */}
          <div className="h-[14px] flex items-center gap-2" title="Screen">
            <svg className="shrink-0" height="12" viewBox="0 0 12 12" width="12">
              <rect fill="#E0A21B" height="10" rx="2" width="8" x="2" y="1" />
            </svg>
            <span className="font-caption text-caption text-muted-text">Screen</span>
          </div>

          {/* Study */}
          <div className="h-[14px] flex items-center gap-2" title="Study">
            <svg className="shrink-0" height="12" viewBox="0 0 12 12" width="12">
              <polygon fill="#4F7A2E" points="6,1 11,10 1,10" />
            </svg>
            <span className="font-caption text-caption text-muted-text">Study</span>
          </div>

          {/* Urges */}
          <div className="h-[14px] flex items-center gap-2" title="Urges">
            <svg className="shrink-0" height="12" viewBox="0 0 12 12" width="12">
              <path d="M 1 6 Q 3.5 2 6 6 T 11 6" fill="none" stroke="#92405F" strokeLinecap="round" strokeWidth="2" />
            </svg>
            <span className="font-caption text-caption text-muted-text">Urges</span>
          </div>
        </div>

        {/* 7 Day Columns Container */}
        <div className="flex items-start justify-end gap-2.5 flex-1">
          {days.map((col, idx) => {
            const isSelected = selectedDay?.dateStr === col.dateStr;
            return (
              <button
                type="button"
                key={idx}
                onClick={() => handleDayClick(col)}
                className={`flex flex-col items-center group transition-transform ${
                  isSelected ? 'scale-105' : 'hover:opacity-90'
                }`}
                title={`${col.dateStr} (Click to inspect)`}
              >
                <span
                  className={`font-caption text-caption mb-2 ${
                    col.isToday ? 'text-ink font-semibold' : 'text-muted-text'
                  }`}
                >
                  {col.dayLabel}
                </span>

                <div className="flex flex-col gap-[3px]">
                  {renderCell(col.habits, 'bg-domain-habits-fill', 'bg-domain-habits-tint', '#C84A21', !!col.isToday)}
                  {renderCell(col.sleep, 'bg-domain-sleep-fill', 'bg-domain-sleep-tint', '#1D5F73', !!col.isToday)}
                  {renderCell(col.screen, 'bg-domain-screen-fill', 'bg-domain-screen-tint', '#E0A21B', !!col.isToday)}
                  {renderCell(col.study, 'bg-domain-study-fill', 'bg-domain-study-tint', '#4F7A2E', !!col.isToday)}
                  {renderCell(col.urges, 'bg-domain-urges-fill', 'bg-domain-urges-tint', '#92405F', !!col.isToday)}
                </div>

                {/* Day indicator under column */}
                <div
                  className={`w-full h-[2px] mt-2 transition-colors ${
                    col.isToday ? 'bg-ink' : isSelected ? 'bg-secondary' : 'bg-transparent'
                  }`}
                />
              </button>
            );
          })}
        </div>
      </div>

      {/* Selected Day Inspect Card if tapped */}
      {selectedDay && (
        <div className="mt-3 p-3 bg-surface-container-low rounded-lg text-small border border-surface-container flex items-center justify-between animate-fadeIn">
          <div>
            <span className="font-small-medium text-ink block">{selectedDay.dateStr} Overview</span>
            <span className="font-caption text-caption text-muted-text">
              Habits: {selectedDay.habits} · Sleep: {selectedDay.sleep} · Screen: {selectedDay.screen}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setSelectedDay(null)}
            className="text-caption text-muted-text hover:text-ink font-medium px-2 py-1"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Word Legend Underneath */}
      <div className="flex flex-wrap items-center justify-between gap-y-2 pt-4 mt-3 bg-surface-container-low p-2.5 rounded">
        {/* Good */}
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-sm bg-ink" />
          <span className="font-caption text-caption text-ink">Good</span>
        </div>
        {/* Partial */}
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-sm bg-secondary-fixed flex flex-col justify-end overflow-hidden">
            <div className="w-full h-1 bg-ink" />
          </div>
          <span className="font-caption text-caption text-ink">Partial</span>
        </div>
        {/* Missed */}
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-sm bg-surface flex items-center justify-center">
            <svg height="10" viewBox="0 0 10 10" width="10">
              <rect fill="none" height="9" stroke="#1B1C1A" strokeWidth="1" width="9" x="0.5" y="0.5" />
            </svg>
          </div>
          <span className="font-caption text-caption text-ink">Missed</span>
        </div>
        {/* Not logged */}
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-[1px] bg-outline" />
          <span className="font-caption text-caption text-ink">Not logged</span>
        </div>
      </div>
    </section>
  );
};
