import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { parseCheckinText, parseCheckinVoice } from '../api/checkins';
import { errorMessage } from '../lib/format';
import { useVoiceRecorder } from '../lib/useVoiceRecorder';
import type { CheckinParse } from '../types';

interface VoiceCheckinCardProps {
  onProposal: (proposal: CheckinParse) => void;
}

/**
 * Say (or type) the day; the result only FILLS the check-in below. Nothing is saved until the person confirms.
 * Typing works everywhere, including with a phone keyboard's own dictation button.
 */
export const VoiceCheckinCard: React.FC<VoiceCheckinCardProps> = ({ onProposal }) => {
  const { showToast } = useApp();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [heard, setHeard] = useState<string | null>(null);

  const run = async (job: () => Promise<CheckinParse>) => {
    setBusy(true);
    try {
      const proposal = await job();
      if (proposal.support) {
        onProposal(proposal);
        return;
      }
      setHeard(proposal.transcript);
      if (proposal.empty) {
        showToast("Heard you, but couldn't find anything to log. Try again or fill it in below.");
      } else {
        onProposal(proposal);
        setText('');
      }
    } catch (err) {
      showToast(errorMessage(err, 'Could not read that'));
    } finally {
      setBusy(false);
    }
  };

  const recorder = useVoiceRecorder((audio) => void run(() => parseCheckinVoice(audio)));

  const toggleMic = async () => {
    if (recorder.recording) {
      recorder.stop();
      return;
    }
    try {
      await recorder.start();
    } catch {
      showToast('Microphone is blocked. Allow it in your browser, or type it instead.');
    }
  };

  return (
    <div className="p-3 bg-surface rounded-xl border border-line space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-small-medium text-small-medium text-ink uppercase tracking-wider">Say your day</h3>
        {recorder.supported && (
          <button
            type="button"
            disabled={busy}
            onClick={toggleMic}
            aria-label={recorder.recording ? 'Stop recording' : 'Start recording'}
            className={`h-9 px-3 rounded-full flex items-center gap-1.5 font-small-medium transition-colors disabled:opacity-50 ${
              recorder.recording ? 'bg-error text-white' : 'bg-ink text-ground-chalk'
            }`}
          >
            <span className="material-symbols-outlined text-[18px]">{recorder.recording ? 'stop' : 'mic'}</span>
            <span>{recorder.recording ? `${recorder.seconds}s` : 'Talk'}</span>
          </button>
        )}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={text}
          maxLength={2000}
          disabled={busy || recorder.recording}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && text.trim() && !busy) void run(() => parseCheckinText(text.trim()));
          }}
          placeholder="gym done, slept 11 to 7, 2h on my phone, felt ok"
          className="flex-1 min-w-0 bg-surface-container-low border border-line rounded-lg px-3 py-2 font-small text-ink"
        />
        <button
          type="button"
          disabled={busy || recorder.recording || !text.trim()}
          onClick={() => void run(() => parseCheckinText(text.trim()))}
          className="px-3 rounded-lg bg-surface-container text-ink font-small-medium disabled:opacity-50"
        >
          {busy ? '...' : 'Fill'}
        </button>
      </div>
      {heard && (
        <p className="font-caption text-caption text-muted-text">
          Heard: "{heard}". Check the fields below, then confirm.
        </p>
      )}
    </div>
  );
};
