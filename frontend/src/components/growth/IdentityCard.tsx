import React, { useCallback, useEffect, useState } from 'react';
import { useApp } from '../../context/AppContext';
import { deleteIdentity, getIdentity, putIdentity } from '../../api/growth';
import type { GrowthIdentity } from '../../api/growth';
import { errorMessage } from '../../lib/format';
import { CLS } from './ui';

const SENTENCE_START = 'I’m someone who ';

interface WizardProps {
  initial: GrowthIdentity | null;
  onCancel: () => void;
  onSaved: (i: GrowthIdentity) => void;
}

const IdentityWizard: React.FC<WizardProps> = ({ initial, onCancel, onSaved }) => {
  const { showToast } = useApp();
  const [step, setStep] = useState(0);
  const [matters, setMatters] = useState(initial?.matters ?? '');
  const [whyNow, setWhyNow] = useState(initial?.why_now ?? '');
  const [importance, setImportance] = useState(initial?.importance ?? 7);
  const [confidence, setConfidence] = useState(initial?.confidence ?? 5);
  const [sentence, setSentence] = useState(initial?.sentence ?? SENTENCE_START);
  const [busy, setBusy] = useState(false);

  const canNext =
    step === 0 ? matters.trim().length > 0 : step === 1 ? whyNow.trim().length > 0 : step === 2 ? true : sentence.trim().length > SENTENCE_START.trim().length + 2;

  const save = async () => {
    setBusy(true);
    try {
      onSaved(await putIdentity({ matters, why_now: whyNow, importance, confidence, sentence }));
      showToast('Saved. Every check-in is a vote for this person.');
    } catch (err) {
      showToast(errorMessage(err, 'Could not save that'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-1.5" aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <span key={i} className={`h-1 flex-1 rounded-full ${i <= step ? 'bg-ink' : 'bg-surface-container'}`} />
        ))}
      </div>

      {step === 0 && (
        <label className="block space-y-1.5">
          <span className="font-body-strong text-body-strong text-ink">What matters to you right now?</span>
          <input className={CLS.input} value={matters} maxLength={200} onChange={(e) => setMatters(e.target.value)} placeholder="e.g. being rested in exam week" autoFocus />
        </label>
      )}
      {step === 1 && (
        <label className="block space-y-1.5">
          <span className="font-body-strong text-body-strong text-ink">Why now?</span>
          <textarea className={CLS.area} rows={3} value={whyNow} maxLength={300} onChange={(e) => setWhyNow(e.target.value)} placeholder="What makes this the moment?" autoFocus />
        </label>
      )}
      {step === 2 && (
        <div className="space-y-4">
          <label className="block space-y-1">
            <span className="font-body-strong text-body-strong text-ink">How important is it? {importance}/10</span>
            <input type="range" min={0} max={10} value={importance} onChange={(e) => setImportance(Number(e.target.value))} className="w-full accent-black" />
          </label>
          <label className="block space-y-1">
            <span className="font-body-strong text-body-strong text-ink">How confident are you? {confidence}/10</span>
            <input type="range" min={0} max={10} value={confidence} onChange={(e) => setConfidence(Number(e.target.value))} className="w-full accent-black" />
          </label>
        </div>
      )}
      {step === 3 && (
        <label className="block space-y-1.5">
          <span className="font-body-strong text-body-strong text-ink">Say it as one sentence</span>
          <textarea className={CLS.area} rows={3} value={sentence} maxLength={200} onChange={(e) => setSentence(e.target.value)} autoFocus />
          <span className={CLS.muted}>Like: I’m someone who shows up rested in exam week.</span>
        </label>
      )}

      <div className="flex items-center gap-2">
        <button type="button" className={CLS.ghost} onClick={step === 0 ? onCancel : () => setStep(step - 1)} disabled={busy}>
          {step === 0 ? 'Cancel' : 'Back'}
        </button>
        <button
          type="button"
          className={`${CLS.primary} flex-1`}
          disabled={!canNext || busy}
          onClick={step === 3 ? () => void save() : () => setStep(step + 1)}
        >
          {step === 3 ? (busy ? 'Saving…' : 'Save it') : 'Next'}
        </button>
      </div>
    </div>
  );
};

export const IdentityCard: React.FC = () => {
  const { showToast } = useApp();
  const [identity, setIdentity] = useState<GrowthIdentity | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [editing, setEditing] = useState(false);

  const load = useCallback(() => {
    getIdentity()
      .then(setIdentity)
      .catch(() => setIdentity(null))
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!loaded) return <p className={CLS.muted}>Loading…</p>;

  if (editing) {
    return (
      <IdentityWizard
        initial={identity}
        onCancel={() => setEditing(false)}
        onSaved={(i) => {
          setIdentity(i);
          setEditing(false);
        }}
      />
    );
  }

  if (!identity) {
    return (
      <div className="space-y-3">
        <p className={CLS.muted}>
          Four quick questions, then one sentence about who you’re becoming. It shows up in your weekly review.
        </p>
        <button type="button" className={`${CLS.primary} w-full`} onClick={() => setEditing(true)}>
          Set it up (about a minute)
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="font-section text-section text-ink leading-snug">“{identity.sentence}”</p>
      <p className={CLS.muted}>
        Importance {identity.importance}/10 · Confidence {identity.confidence}/10
      </p>
      <p className={CLS.muted}>Each check-in is a vote for that person.</p>
      <div className="flex gap-2">
        <button type="button" className={CLS.ghost} onClick={() => setEditing(true)}>
          Edit
        </button>
        <button
          type="button"
          className={CLS.ghost}
          onClick={() => {
            if (!window.confirm('Remove this sentence and your answers?')) return;
            deleteIdentity()
              .then(() => setIdentity(null))
              .catch((err: unknown) => showToast(errorMessage(err, 'Could not remove that')));
          }}
        >
          Remove
        </button>
      </div>
    </div>
  );
};
