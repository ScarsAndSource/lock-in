import React, { useState, useEffect } from 'react';
import { getChain } from '../api/stats';
import { ChainDay } from '../types';

export const ChainVisualizer: React.FC = () => {
  const [days, setDays] = useState<ChainDay[]>([]);
  const [selectedDay, setSelectedDay] = useState<ChainDay | null>(null);

  useEffect(() => {
    getChain(14).then((res) => {
      setDays(res.days);
    });
  }, []);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'good':
        return 'bg-ink border-ink text-ground-chalk';
      case 'partial':
        return 'bg-secondary-fixed border-ink text-ink';
      case 'missed':
        return 'bg-surface border-line text-muted-text';
      default:
        return 'bg-surface-container border-line text-muted-text';
    }
  };

  return (
    <div className="bg-surface rounded-xl p-4 border border-line shadow-sm space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-section text-section text-ink">Chain Visualization</h3>
          <p className="font-caption text-caption text-muted-text">
            Cross-domain cause & effect cascade across time
          </p>
        </div>
        <span className="font-caption text-caption text-muted-text uppercase tracking-wider">
          Last 14 Days
        </span>
      </div>

      {/* Horizontal Strip */}
      <div className="overflow-x-auto pb-2 pt-1">
        <div className="flex items-center gap-1.5 min-w-max">
          {days.map((d) => {
            const dateObj = new Date(d.day);
            const dateNum = dateObj.getDate();
            const isSelected = selectedDay?.day === d.day;

            return (
              <button
                key={d.day}
                type="button"
                onClick={() => setSelectedDay(isSelected ? null : d)}
                className={`flex flex-col items-center p-2 rounded-lg transition-all border ${
                  isSelected ? 'border-ink bg-surface-container' : 'border-transparent hover:bg-surface-container-low'
                }`}
              >
                <span className="font-caption text-[11px] text-muted-text mb-1.5">{dateNum}</span>
                <div className="flex flex-col gap-1 items-center">
                  {/* Habits Node */}
                  <div
                    className={`w-3.5 h-3.5 rounded-full border flex items-center justify-center ${getStatusColor(
                      d.habits
                    )}`}
                    title={`Habits: ${d.habits}`}
                  />
                  {/* Sleep Node */}
                  <div
                    className={`w-3.5 h-3.5 rounded-sm border flex items-center justify-center ${getStatusColor(
                      d.sleep
                    )}`}
                    title={`Sleep: ${d.sleep}`}
                  />
                  {/* Screen Node */}
                  <div
                    className={`w-3.5 h-3.5 rounded-xs border flex items-center justify-center ${getStatusColor(
                      d.screen_time
                    )}`}
                    title={`Screen: ${d.screen_time}`}
                  />
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Details pane if day tapped */}
      {selectedDay && (
        <div className="p-3 bg-surface-container-low rounded-lg border border-surface-container text-small space-y-1 animate-fadeIn">
          <div className="flex items-center justify-between font-small-medium text-ink">
            <span>Date: {selectedDay.day}</span>
            <button
              type="button"
              onClick={() => setSelectedDay(null)}
              className="font-caption text-caption text-muted-text hover:text-ink"
            >
              Close
            </button>
          </div>
          <div className="grid grid-cols-3 gap-2 pt-1 font-caption text-caption">
            <div className="p-2 bg-surface rounded">
              <span className="text-muted-text block">Habits</span>
              <strong className="text-ink capitalize">{selectedDay.habits}</strong>
            </div>
            <div className="p-2 bg-surface rounded">
              <span className="text-muted-text block">Sleep</span>
              <strong className="text-ink">
                {selectedDay.sleep_minutes ? `${Math.floor(selectedDay.sleep_minutes / 60)}h ${selectedDay.sleep_minutes % 60}m` : '—'}
              </strong>
            </div>
            <div className="p-2 bg-surface rounded">
              <span className="text-muted-text block">Screen</span>
              <strong className="text-ink">
                {selectedDay.screen_minutes ? `${Math.floor(selectedDay.screen_minutes / 60)}h ${selectedDay.screen_minutes % 60}m` : '—'}
              </strong>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
