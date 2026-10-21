import React, { useEffect, useRef } from 'react';

interface SheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  eyebrow?: string;
  footer?: React.ReactNode;
  /** Fixed 92% height instead of fitting the content. Use for screens that scroll a lot. */
  tall?: boolean;
  children: React.ReactNode;
}

// Several sheets can be open at once (a domain sheet, then the urge sheet on top of it): count the locks so
// closing them in any order always restores page scrolling.
let scrollLocks = 0;

/** The one bottom-sheet shell: backdrop tap and Esc close it, page scroll is locked while it is open. */
export const Sheet: React.FC<SheetProps> = ({ open, onClose, title, eyebrow, footer, tall = false, children }) => {
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeRef.current();
    };
    document.addEventListener('keydown', onKey);
    scrollLocks += 1;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      scrollLocks -= 1;
      if (scrollLocks <= 0) {
        scrollLocks = 0;
        document.body.style.overflow = '';
      }
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-black/50 sm:p-4 animate-fadeIn"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`w-full max-w-md bg-ground-chalk rounded-t-2xl sm:rounded-2xl flex flex-col overflow-hidden shadow-2xl border border-line animate-slideUp ${
          tall ? 'h-[92dvh]' : 'max-h-[92dvh]'
        }`}
      >
        <div className="px-4 py-3 bg-surface border-b border-surface-container flex items-center justify-between shrink-0">
          <div className="min-w-0">
            {eyebrow && (
              <span className="font-caption text-caption text-muted-text uppercase tracking-wider block">{eyebrow}</span>
            )}
            <h2 className="font-section text-section text-ink truncate">{title}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="w-9 h-9 shrink-0 rounded-full bg-surface-container flex items-center justify-center text-ink hover:bg-secondary-fixed transition-colors"
          >
            <span className="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
        {footer && <div className="p-4 bg-surface border-t border-surface-container shrink-0 pb-safe">{footer}</div>}
      </div>
    </div>
  );
};
