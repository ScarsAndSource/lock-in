import React from 'react';
import { SupportPayload } from '../types';

interface SupportCardProps {
  support: SupportPayload;
  className?: string;
}

/** The one place crisis resources are drawn, so chat, check-in and tasks all show the same region-aware list. */
export const SupportCard: React.FC<SupportCardProps> = ({ support, className = '' }) => (
  <div
    role="alert"
    className={`p-4 bg-error-container text-on-error-container rounded-xl border border-error space-y-2 ${className}`}
  >
    <div className="flex items-center gap-2">
      <span className="material-symbols-outlined text-[20px]">favorite</span>
      <span className="font-body-strong font-bold">Support is available right now</span>
    </div>
    <p className="font-small text-small">{support.message}</p>
    <ul className="space-y-1.5 font-small-medium">
      {support.resources.map((r) => (
        <li key={`${r.name}-${r.contact}`}>
          <strong>{r.name}</strong>: <strong>{r.contact}</strong>
          <span className="block font-caption text-caption opacity-80">{r.detail}</span>
        </li>
      ))}
    </ul>
    {support.verified_on && (
      <p className="font-caption text-[11px] opacity-70">Numbers last verified {support.verified_on}.</p>
    )}
  </div>
);
