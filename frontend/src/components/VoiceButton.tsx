import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { transcribeRecording } from '../api/capture';
import { useVoiceRecorder } from '../hooks/useVoiceRecorder';
import { errorMessage } from '../lib/format';

interface VoiceButtonProps {
  /** Gets the words. The caller puts them in its text box; nothing is sent or saved from here. */
  onTranscript: (text: string) => void;
  disabled?: boolean;
  className?: string;
}

/** Mic for a text input: tap, speak, tap again. The transcript lands in the box for the person to read and send. */
export const VoiceButton: React.FC<VoiceButtonProps> = ({ onTranscript, disabled = false, className = 'w-12 h-12' }) => {
  const { showToast } = useApp();
  const [busy, setBusy] = useState(false);

  const rec = useVoiceRecorder({
    onFinished: (blob) => {
      setBusy(true);
      transcribeRecording(blob)
        .then(onTranscript)
        .catch((err: unknown) => showToast(errorMessage(err, 'Could not read that recording')))
        .finally(() => setBusy(false));
    },
    onError: showToast,
  });

  if (!rec.supported) return null;

  const icon = busy ? 'progress_activity' : rec.recording ? 'stop' : 'mic';
  const label = busy ? 'Reading your recording' : rec.recording ? 'Stop recording' : 'Speak instead of typing';

  return (
    <button
      type="button"
      aria-label={label}
      title={rec.recording ? `Recording ${rec.seconds}s. Tap to stop` : label}
      disabled={disabled || busy}
      onClick={() => (rec.recording ? rec.stop() : void rec.start())}
      className={`${className} shrink-0 rounded-xl border flex items-center justify-center transition-colors disabled:opacity-40 ${
        rec.recording ? 'bg-error-container text-on-error-container border-error' : 'bg-surface text-ink border-line'
      }`}
    >
      <span className={`material-symbols-outlined text-[20px] ${busy ? 'animate-spin' : rec.recording ? 'animate-pulse' : ''}`}>
        {icon}
      </span>
    </button>
  );
};
