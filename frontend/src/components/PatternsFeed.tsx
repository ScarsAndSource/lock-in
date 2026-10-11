import React, { useState, useEffect } from 'react';
import { getPatterns } from '../api/stats';
import { Pattern } from '../types';

export const PatternsFeed: React.FC = () => {
  const [patterns, setPatterns] = useState<Pattern[]>([]);

  useEffect(() => {
    getPatterns(30).then((res) => {
      setPatterns(res.patterns);
    });
  }, []);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-section text-section text-ink">Correlations & Triggers</h3>
        <span className="font-caption text-caption text-muted-text">30-day window</span>
      </div>

      <div className="space-y-3">
        {patterns.map((p) => {
          const impactMultiplier = (p.rate_after_trigger / Math.max(p.baseline_rate, 0.01)).toFixed(1);
          return (
            <div
              key={p.key}
              className="p-4 bg-surface rounded-xl border border-line shadow-sm space-y-2 hover:border-secondary transition-colors"
            >
              <div className="flex items-center justify-between">
                <span className="px-2 py-0.5 rounded text-[11px] font-caption font-semibold bg-domain-habits-tint text-domain-habits-fill">
                  {impactMultiplier}x Likelihood Spike
                </span>
                <span className="font-caption text-caption text-muted-text">
                  Lag: {p.lag_days === 0 ? 'Same day' : `${p.lag_days} day`}
                </span>
              </div>

              <p className="font-small-medium text-ink leading-snug">{p.statement}</p>

              <div className="pt-1 border-t border-surface-container flex items-center justify-between font-caption text-caption text-muted-text">
                <span>Trigger: {p.trigger}</span>
                <span>Verified across {p.hits} instances</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
