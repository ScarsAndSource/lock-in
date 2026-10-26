import React, { useEffect, useState } from 'react';
import { useApp } from '../context/AppContext';
import { captureUrge } from '../api/tracking';
import { getDueIntentions } from '../api/profile';
import { DueIntention, SupportPayload, UrgeOutcome } from '../types';
import { errorMessage } from '../lib/format';
import { SupportCard } from './SupportCard';

interface UrgeQuickModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const UrgeQuickModal: React.FC<UrgeQuickModalProps> = ({ isOpen, onClose }) => {
  const { showToast, bumpData } = useApp();
  const [intensity, setIntensity] = useState(6);
  const [triggerContext, setTriggerContext] = useState('');
  const [copingStrategy, setCopingStrategy] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [due, setDue] = useState<DueIntention[]>([]);
  const [support, setSupport] = useState<SupportPayload | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setIntensity(6);
    setTriggerContext('');
    setCopingStrategy('');
    setSupport(null);
    getDueIntentions('urge')
      .then(setDue)
      .catch(() => setDue([]));
  }, [isOpen]);

  if (!isOpen) return null;

  const handleQuickLog = async (selectedOutcome: UrgeOutcome) => {
    setIsSubmitting(true);
    try {
      const hasDetail = Boolean(triggerContext.trim() || copingStrategy.trim());
      const saved = await captureUrge({
        outcome: selectedOutcome,
        intensity: hasDetail ? intensity : null,
        trigger_context: triggerContext.trim() || null,
        coping_strategy: copingStrategy.trim() || null,
      });
      if (saved.queued) { showToast('Urge queued � will sync when back online.'); return; }
      if (saved.support) { setSupport(saved.support); return; }
      bumpData();
      showToast(`Urge logged: ${selectedOutcome}`);
      onClose();
    } catch (err) {
      showToast(errorMessage(err, 'Could not log urge'));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (support) {
    return (
      <div className="fixed inset-0 z-[70] flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4">
        <div className="w-full max-w-md bg-ground-chalk rounded-t-2xl sm:rounded-2xl p-5 shadow-2xl border border-line animate-slideUp space-y-4">
          <SupportCard payload={support} onDismiss={() => { setSupport(null); onClose(); }} />
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4">
      <div className="w-full max-w-md bg-ground-chalk rounded-t-2xl sm:rounded-2xl p-5 shadow-2xl border border-line animate-slideUp space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <span className="font-caption text-caption text-domain-urges-fill uppercase tracking-wider font-semibold block">
              Urge Quick-Capture
            </span>
            <h2 className="font-title text-title text-ink text-xl">2-Tap Urgent Log</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center text-ink hover:bg-secondary-fixed transition-colors"
          >
            <span className="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>

        <p className="font-small text-small text-muted-text leading-relaxed">
          In the moment, don't fill a form. Tap once. An imperfect log beats no log.
        </p>

        {due[0] && (
          <div className="p-3 bg-surface-container rounded-lg">
            <span className="font-caption text-caption text-muted-text uppercase tracking-wider block mb-1">
              If-then cue
            </span>
            <p className="font-small text-ink">
              IF {due[0].intention.cue} THEN {due[0].intention.action}
            </p>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 pt-2">
          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => handleQuickLog('resisted')}
            className="h-16 rounded-xl bg-ink text-ground-chalk flex flex-col items-center justify-center font-body-strong text-body-strong hover:bg-secondary active:scale-[0.98] transition-all disabled:opacity-50"
          >
            <span className="flex items-center gap-1.5">
              <span className="material-symbols-outlined text-[20px] text-domain-study-tint">shield</span>
              <span>Resisted</span>
            </span>
            <span className="text-[11px] font-caption text-surface-dim font-normal">Held the line</span>
          </button>

          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => handleQuickLog('relapsed')}
            className="h-16 rounded-xl bg-surface-container text-ink border border-line flex flex-col items-center justify-center font-body-strong text-body-strong hover:bg-secondary-fixed active:scale-[0.98] transition-all disabled:opacity-50"
          >
            <span className="flex items-center gap-1.5">
              <span className="material-symbols-outlined text-[20px] text-domain-urges-fill">refresh</span>
              <span>Relapsed</span>
            </span>
            <span className="text-[11px] font-caption text-muted-text font-normal">Data, not verdict</span>
          </button>
        </div>

        <details className="group pt-2">
          <summary className="font-caption text-caption text-muted-text cursor-pointer hover:text-ink list-none flex items-center justify-between py-1 select-none">
            <span>Optional: add context or coping note</span>
            <span className="material-symbols-outlined text-[16px] group-open:rotate-180 transition-transform">
              expand_more
            </span>
          </summary>
          <div className="space-y-3 pt-3">
            <div>
              <label className="font-caption text-caption text-muted-text block mb-1">
                Intensity (1-10): <strong className="text-ink">{intensity}</strong>
              </label>
              <input
                type="range"
                min="1"
                max="10"
                value={intensity}
                onChange={(e) => setIntensity(parseInt(e.target.value, 10))}
                className="w-full accent-domain-urges-fill"
              />
            </div>
            <div>
              <label className="font-caption text-caption text-muted-text block mb-1">Trigger Context</label>
              <input
                type="text"
                placeholder="e.g. Tired after study session, scrolling phone..."
                value={triggerContext}
                onChange={(e) => setTriggerContext(e.target.value)}
                className="w-full bg-surface border border-line rounded-lg px-3 py-2 font-small text-ink"
              />
            </div>
            <div>
              <label className="font-caption text-caption text-muted-text block mb-1">Coping Strategy Tried</label>
              <input
                type="text"
                placeholder="e.g. 10 pushups, cold shower, walk outside..."
                value={copingStrategy}
                onChange={(e) => setCopingStrategy(e.target.value)}
                className="w-full bg-surface border border-line rounded-lg px-3 py-2 font-small text-ink"
              />
            </div>
          </div>
        </details>
      </div>
    </div>
  );
};
