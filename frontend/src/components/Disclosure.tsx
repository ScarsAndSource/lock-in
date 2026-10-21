import React, { useState } from 'react';

interface DisclosureProps {
  title: string;
  /** Short value shown on the right while closed, e.g. "7h 15m" or "Optional". */
  summary?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

/** A closed-by-default row. Children are only mounted while open, so heavy content loads on demand. */
export const Disclosure: React.FC<DisclosureProps> = ({ title, summary, defaultOpen = false, children }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="bg-surface rounded-xl border border-line overflow-hidden">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="w-full min-h-[48px] px-4 py-2.5 flex items-center justify-between gap-3 text-left"
      >
        <span className="font-small-medium text-small-medium text-ink">{title}</span>
        <span className="flex items-center gap-1.5 min-w-0">
          {summary && !open && <span className="font-caption text-caption text-muted-text truncate">{summary}</span>}
          <span
            className={`material-symbols-outlined text-[20px] text-muted-text transition-transform ${open ? 'rotate-180' : ''}`}
          >
            expand_more
          </span>
        </span>
      </button>
      {open && <div className="px-4 pb-4 pt-1 border-t border-surface-container">{children}</div>}
    </div>
  );
};
