import React from 'react';
import type { Bounce } from '../types';

interface BounceCardProps {
  bounce?: Bounce;
  className?: string;
}

/** Shown on the day after a slip: today's proposals are already at the floor, and this says why. */
export const BounceCard: React.FC<BounceCardProps> = ({ bounce, className = '' }) => {
  if (!bounce?.active || !bounce.title || !bounce.message) return null;
  return (
    <div className={`p-3 bg-surface-container rounded-lg flex items-start gap-2.5 ${className}`}>
      <span className="material-symbols-outlined text-ink text-[20px]">flag</span>
      <div className="min-w-0">
        <p className="font-small-medium text-small-medium text-ink">{bounce.title}</p>
        <p className="font-small text-small text-ink">{bounce.message}</p>
      </div>
    </div>
  );
};
