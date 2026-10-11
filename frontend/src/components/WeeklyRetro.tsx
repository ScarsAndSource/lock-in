import React, { useState, useEffect } from 'react';
import { getLatestRetro, updateRetroTone, completeRetro } from '../api/retros';
import { RetroDetail, WeekMode } from '../types';
import { useApp } from '../context/AppContext';

export const WeeklyRetro: React.FC = () => {
  const { showToast } = useApp();
  const [retro, setRetro] = useState<RetroDetail | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    getLatestRetro().then(setRetro);
  }, []);

  if (!retro) return null;

  const handleToneChange = async (mode: WeekMode) => {
    setIsSubmitting(true);
    try {
      const updated = await updateRetroTone(retro.week_start, mode);
      setRetro(updated);
      showToast(`Retro tone set to ${mode.toUpperCase()} mode`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleComplete = async () => {
    setIsSubmitting(true);
    try {
      await completeRetro(retro.week_start);
      setRetro((prev) => (prev ? { ...prev, status: 'completed', completed_at: new Date().toISOString() } : null));
      showToast('Weekly retrospective closed and feedback archived!');
    } finally {
      setIsSubmitting(false);
    }
  };

  const currentMode = retro.week_mode?.mode || 'normal';

  return (
    <div className="bg-surface rounded-xl p-5 border border-line shadow-sm space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <span className="font-caption text-caption text-muted-text uppercase tracking-wider block">
            Weekly Protocol Review
          </span>
          <h3 className="font-title text-title text-ink text-xl">
            Week of {retro.week_start}
          </h3>
        </div>
        <div className="flex items-center gap-1 bg-surface-container p-0.5 rounded-lg">
          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => handleToneChange('normal')}
            className={`px-2 py-1 rounded text-[11px] font-semibold transition-colors ${
              currentMode === 'normal' ? 'bg-ink text-ground-chalk' : 'text-ink'
            }`}
          >
            Normal
          </button>
          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => handleToneChange('rough')}
            className={`px-2 py-1 rounded text-[11px] font-semibold transition-colors ${
              currentMode === 'rough' ? 'bg-ink text-ground-chalk' : 'text-ink'
            }`}
          >
            Rough Week
          </button>
        </div>
      </div>

      <p className="font-small-medium text-ink leading-relaxed">{retro.narrative}</p>

      {/* Concrete next step */}
      <div className="p-3 bg-surface-container-low rounded-lg border border-surface-container">
        <span className="font-caption text-caption text-muted-text uppercase tracking-wider block mb-0.5">
          Priority Focus For Upcoming Week
        </span>
        <p className="font-small text-small text-ink font-semibold">{retro.next_step}</p>
      </div>

      {/* Metric chips */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
        {Object.entries(retro.summary).map(([key, val]) => (
          <div key={key} className="p-2.5 bg-surface-container-low rounded-lg text-center">
            <span className="font-caption text-caption text-muted-text block capitalize">
              {key.replace('_', ' ')}
            </span>
            <strong className="font-small-medium text-ink text-base">{String(val)}</strong>
          </div>
        ))}
      </div>

      {/* Complete Button */}
      {retro.status !== 'completed' ? (
        <button
          type="button"
          disabled={isSubmitting}
          onClick={handleComplete}
          className="w-full h-11 bg-ink text-ground-chalk rounded-xl font-body-strong text-body-strong flex items-center justify-center gap-2 hover:bg-secondary transition-colors"
        >
          <span>Close & Archive Week</span>
          <span className="material-symbols-outlined text-[18px]">done_all</span>
        </button>
      ) : (
        <div className="text-center py-1 font-caption text-caption text-muted-text">
          ✓ Completed on {new Date(retro.completed_at || '').toLocaleDateString()}
        </div>
      )}
    </div>
  );
};
