import React from 'react';
import { SupportPayload } from '../types';

interface SupportCardProps {
  /** The resources to show. `payload` is accepted as an alias so both call styles compile. */
  support?: SupportPayload;
  payload?: SupportPayload;
  /** When given, a small close button is shown (used by the urge modal). */
  onDismiss?: () => void;
  className?: string;
}

/** The one place crisis resources are drawn, so chat, check-in and tasks all show the same region-aware list. */
export const SupportCard: React.FC<SupportCardProps> = ({ support, payload, onDismiss, className = '' }) => {
  const data = support ?? payload;
  if (!data) return null;
  return (
    <div
      role="alert"
      className={`p-4 bg-error-container text-on-error-container rounded-xl border border-error space-y-2 ${className}`}
    >
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-[20px]">favorite</span>
        <span className="font-body-strong font-bold flex-1">Support is available right now</span>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Close"
            className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-black/5"
          >
            <span className="material-symbols-outlined text-[18px]">close</span>
          </button>
        )}
      </div>
      <p className="font-small text-small">{data.message}</p>
      <ul className="space-y-1.5 font-small-medium">
        {data.resources.map((r) => (
          <li key={`${r.name}-${r.contact}`}>
            <strong>{r.name}</strong>: <strong>{r.contact}</strong>
            <span className="block font-caption text-caption opacity-80">{r.detail}</span>
          </li>
        ))}
      </ul>
      {data.verified_on && (
        <p className="font-caption text-[11px] opacity-70">Numbers last verified {data.verified_on}.</p>
      )}
    </div>
  );
};