import React from 'react';
import { WeeklyRetro } from '../components/WeeklyRetro';
import { ChainVisualizer } from '../components/ChainVisualizer';
import { PatternsFeed } from '../components/PatternsFeed';
import { InsightsFeed } from '../components/InsightsFeed';

export const ReviewView: React.FC = () => {
  return (
    <div className="flex flex-col w-full pb-8 max-w-md mx-auto space-y-6 animate-fadeIn">
      {/* Weekly Retrospective Component */}
      <WeeklyRetro />

      {/* 7-14 Day Chain Visualization Component */}
      <ChainVisualizer />

      {/* Discovered Patterns & Triggers */}
      <PatternsFeed />

      {/* Pattern Insights & Feedback */}
      <InsightsFeed />
    </div>
  );
};
