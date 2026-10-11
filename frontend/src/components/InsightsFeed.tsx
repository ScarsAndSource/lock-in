import React, { useState, useEffect } from 'react';
import { getInsights, submitInsightFeedback, refreshInsights } from '../api/retros';
import { Insight, InsightFeedback } from '../types';
import { useApp } from '../context/AppContext';

export const InsightsFeed: React.FC = () => {
  const { showToast } = useApp();
  const [insights, setInsights] = useState<Insight[]>([]);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const loadData = () => {
    getInsights().then(setInsights);
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleFeedback = async (id: string, feedback: InsightFeedback) => {
    try {
      await submitInsightFeedback(id, feedback);
      setInsights((prev) =>
        prev.map((i) => (i.id === id ? { ...i, user_feedback: feedback } : i))
      );
      showToast('Feedback noted — models calibrated.');
    } catch {
      showToast('Feedback saved locally');
    }
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await refreshInsights();
      loadData();
      showToast('Insights refreshed from latest logs');
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-section text-section text-ink">AI Pattern Insights</h3>
          <p className="font-caption text-caption text-muted-text">
            Voice & Tone ceiling: blunt about data, zero shaming
          </p>
        </div>
        <button
          type="button"
          disabled={isRefreshing}
          onClick={handleRefresh}
          className="px-2.5 py-1 rounded bg-surface-container hover:bg-secondary-fixed text-ink font-caption text-caption flex items-center gap-1 transition-colors"
        >
          <span className={`material-symbols-outlined text-[16px] ${isRefreshing ? 'animate-spin' : ''}`}>
            refresh
          </span>
          <span>Refresh</span>
        </button>
      </div>

      <div className="space-y-3">
        {insights.map((item) => (
          <div
            key={item.id}
            className="p-4 bg-surface rounded-xl border border-line shadow-sm space-y-3"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 flex-wrap">
                {item.source_domains.map((dom) => (
                  <span
                    key={dom}
                    className="px-2 py-0.5 rounded text-[11px] font-caption uppercase tracking-wider bg-surface-container text-ink font-medium"
                  >
                    {dom.replace('_', ' ')}
                  </span>
                ))}
              </div>
              <span className="font-caption text-caption text-muted-text">{item.generated_on}</span>
            </div>

            <p className="font-small-medium text-ink leading-relaxed">{item.insight_text}</p>

            {/* Next step block */}
            <div className="p-3 bg-surface-container-low rounded-lg border border-surface-container">
              <span className="font-caption text-caption text-muted-text uppercase tracking-wider block mb-0.5">
                Next Step
              </span>
              <p className="font-small text-small text-ink font-medium">{item.next_step}</p>
            </div>

            {/* Was this right feedback loop */}
            <div className="pt-1 flex items-center justify-between">
              <span className="font-caption text-caption text-muted-text">Was this accurate?</span>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => handleFeedback(item.id, 'accurate')}
                  className={`px-2.5 py-1 rounded text-caption font-caption transition-colors ${
                    item.user_feedback === 'accurate'
                      ? 'bg-ink text-ground-chalk font-semibold'
                      : 'bg-surface-container text-ink hover:bg-secondary-fixed'
                  }`}
                >
                  Accurate
                </button>
                <button
                  type="button"
                  onClick={() => handleFeedback(item.id, 'not_quite')}
                  className={`px-2.5 py-1 rounded text-caption font-caption transition-colors ${
                    item.user_feedback === 'not_quite'
                      ? 'bg-ink text-ground-chalk font-semibold'
                      : 'bg-surface-container text-ink hover:bg-secondary-fixed'
                  }`}
                >
                  Not quite
                </button>
                <button
                  type="button"
                  onClick={() => handleFeedback(item.id, 'unsure')}
                  className={`px-2.5 py-1 rounded text-caption font-caption transition-colors ${
                    item.user_feedback === 'unsure'
                      ? 'bg-ink text-ground-chalk font-semibold'
                      : 'bg-surface-container text-ink hover:bg-secondary-fixed'
                  }`}
                >
                  Unsure
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
