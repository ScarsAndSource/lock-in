import React, { useRef, useState } from 'react';
import { useApp } from '../context/AppContext';
import {
  parseScreenshot,
  parseTypedCheckin,
  parseVoiceCheckin,
  type CheckinProposal,
  type ScreenshotProposal,
} from '../api/capture';
import { useVoiceRecorder } from '../hooks/useVoiceRecorder';
import { shrinkImageIfNeeded } from '../lib/image';
import { errorMessage } from '../lib/format';

interface CaptureBarProps {
  onProposal: (proposal: CheckinProposal) => void;
  onScreenshot: (proposal: ScreenshotProposal) => void;
}

/**
 * Three ways to fill the check-in without touching a slider: say it, type it, or hand over a Screen Time screenshot.
 * Every path ends in a PROPOSAL that pre-fills the check-in form; nothing is saved until the person locks it in.
 */
export const CaptureBar: React.FC<CaptureBarProps> = ({ onProposal, onScreenshot }) => {
  const { showToast } = useApp();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState<null | 'text' | 'voice' | 'image'>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const rec = useVoiceRecorder({
    onFinished: (blob) => {
      setBusy('voice');
      parseVoiceCheckin(blob)
        .then(onProposal)
        .catch((err: unknown) => showToast(errorMessage(err, 'Could not read that recording')))
        .finally(() => setBusy(null));
    },
    onError: showToast,
  });

  const submitText = async () => {
    const value = text.trim();
    if (!value || busy) return;
    setBusy('text');
    try {
      const proposal = await parseTypedCheckin(value);
      if (!proposal.support) setText(''); // a crisis reply keeps the words; nothing was parsed or saved
      onProposal(proposal);
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not read that'));
    } finally {
      setBusy(null);
    }
  };

  const onPickImage = async (file: File | undefined) => {
    if (fileRef.current) fileRef.current.value = ''; // picking the same file again must still fire
    if (!file || busy) return;
    setBusy('image');
    try {
      const ready = await shrinkImageIfNeeded(file);
      onScreenshot(await parseScreenshot(ready));
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not read that screenshot'));
    } finally {
      setBusy(null);
    }
  };

  const working = busy !== null;

  return (
    <div className="p-3 bg-surface-container-low rounded-xl border border-line space-y-2">
      <span className="font-caption text-caption text-muted-text uppercase tracking-wider block">Just tell me</span>
      <textarea
        rows={2}
        value={text}
        maxLength={2000}
        disabled={working || rec.recording}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void submitText();
        }}
        placeholder="Gym done, slept 12 to 7, about 3 hours on my phone…"
        className="w-full bg-surface border border-line rounded-lg px-3 py-2 font-small text-ink resize-none"
      />
      <div className="flex gap-2">
        {rec.supported && (
          <button
            type="button"
            disabled={working && !rec.recording}
            onClick={() => (rec.recording ? rec.stop() : void rec.start())}
            className={`h-10 px-3 rounded-xl border flex items-center gap-1.5 font-caption text-caption font-semibold disabled:opacity-40 ${
              rec.recording ? 'bg-error-container text-on-error-container border-error' : 'bg-surface text-ink border-line'
            }`}
          >
            <span className={`material-symbols-outlined text-[18px] ${rec.recording ? 'animate-pulse' : ''}`}>
              {rec.recording ? 'stop' : busy === 'voice' ? 'progress_activity' : 'mic'}
            </span>
            <span>{rec.recording ? `Stop · ${rec.seconds}s` : busy === 'voice' ? 'Listening…' : 'Speak'}</span>
          </button>
        )}
        <button
          type="button"
          disabled={working || rec.recording}
          onClick={() => fileRef.current?.click()}
          className="h-10 px-3 rounded-xl border border-line bg-surface text-ink flex items-center gap-1.5 font-caption text-caption font-semibold disabled:opacity-40"
        >
          <span className={`material-symbols-outlined text-[18px] ${busy === 'image' ? 'animate-spin' : ''}`}>
            {busy === 'image' ? 'progress_activity' : 'screenshot'}
          </span>
          <span>{busy === 'image' ? 'Reading…' : 'Screenshot'}</span>
        </button>
        <button
          type="button"
          disabled={working || rec.recording || !text.trim()}
          onClick={() => void submitText()}
          className="flex-1 h-10 rounded-xl bg-ink text-ground-chalk font-caption text-caption font-semibold disabled:opacity-40"
        >
          {busy === 'text' ? 'Reading…' : 'Fill it in'}
        </button>
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(e) => void onPickImage(e.target.files?.[0])}
      />
      <p className="font-caption text-[11px] text-muted-text leading-relaxed">
        For screen time: open Screen Time (iPhone) or Digital Wellbeing (Android), show today’s DAY view, take a screenshot,
        then tap Screenshot. You review everything before it is saved.
      </p>
    </div>
  );
};
