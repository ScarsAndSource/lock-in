import React, { useEffect, useState } from 'react';
import { useApp } from '../context/AppContext';
import { parseScreenshot, type ScreenshotProposal } from '../api/capture';
import { captureTasks } from '../api/tasks';
import { logScreenTime } from '../api/tracking';
import { clearPendingShare, readPendingShare, type PendingShare } from '../lib/share';
import { shrinkImageIfNeeded } from '../lib/image';
import { errorMessage, formatMinutes } from '../lib/format';
import type { SupportPayload } from '../types';
import { Sheet } from './Sheet';
import { SchedulePhoto } from './SchedulePhoto';
import { SupportCard } from './SupportCard';

interface ShareSheetProps {
  onClose: () => void;
}

type Step = 'loading' | 'empty' | 'choose' | 'screen' | 'timetable' | 'support';

const ACTION_BTN =
  'w-full min-h-12 px-4 py-3 rounded-xl bg-surface-container text-ink text-left font-body-strong flex items-center gap-3 hover:bg-secondary-fixed disabled:opacity-40';

/**
 * Landing screen for something shared into Lock'in from Android's share sheet (the service worker stored it and opened /?a=share).
 * It reuses the existing endpoints: a picture goes to /screen-time/parse-screenshot or /calendar/parse-image, text goes to
 * /tasks/capture. The person says which one it is; nothing is sent until they do, and the AI only proposes (screen time is
 * shown before it is saved; the timetable review sheet is the same one the camera button uses).
 */
export const ShareSheet: React.FC<ShareSheetProps> = ({ onClose }) => {
  const { activeDate, showToast, bumpData } = useApp();
  const [step, setStep] = useState<Step>('loading');
  const [share, setShare] = useState<PendingShare | null>(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [proposal, setProposal] = useState<ScreenshotProposal | null>(null);
  const [support, setSupport] = useState<SupportPayload | null>(null);

  useEffect(() => {
    let alive = true;
    void readPendingShare().then((s) => {
      if (!alive) return;
      setShare(s);
      setText((s?.text ?? '').slice(0, 1000)); // /tasks/capture accepts up to 1000 characters
      setStep(s ? 'choose' : 'empty');
    });
    return () => {
      alive = false;
    };
  }, []);

  const finish = async () => {
    await clearPendingShare();
    onClose();
  };

  const readScreenTime = async () => {
    if (!share?.file || busy) return;
    setBusy(true);
    try {
      const blob = await shrinkImageIfNeeded(share.file);
      setProposal(await parseScreenshot(blob));
      setStep('screen');
    } catch (err) {
      showToast(errorMessage(err, 'Could not read that screenshot'));
    } finally {
      setBusy(false);
    }
  };

  const saveScreenTime = async () => {
    if (!proposal || busy) return;
    setBusy(true);
    try {
      await logScreenTime({
        log_date: activeDate,
        total_minutes: proposal.total_minutes,
        source: 'screenshot',
        category_breakdown: proposal.category_breakdown,
      });
      showToast(`Screen time saved: ${formatMinutes(proposal.total_minutes)}`);
      bumpData();
      await finish();
    } catch (err) {
      showToast(errorMessage(err, 'Could not save screen time'));
    } finally {
      setBusy(false);
    }
  };

  const addTasks = async () => {
    const body = text.trim();
    if (!body || busy) return;
    setBusy(true);
    try {
      const res = await captureTasks(body);
      bumpData();
      if (res.support) {
        // The text tripped the crisis screen. Show the resources instead of closing over them.
        await clearPendingShare();
        setSupport(res.support);
        setStep('support');
        return;
      }
      const n = res.tasks.length;
      showToast(
        n > 0
          ? `Added ${n} task${n === 1 ? '' : 's'}`
          : res.skipped_duplicates > 0
            ? 'Those were already in your list'
            : 'Nothing to add from that'
      );
      await finish();
    } catch (err) {
      showToast(errorMessage(err, 'Could not add tasks'));
    } finally {
      setBusy(false);
    }
  };

  if (step === 'loading') return null;

  // The timetable flow brings its own review sheet; this one stays out of its way.
  if (step === 'timetable' && share?.file) {
    return (
      <SchedulePhoto
        hideButton
        autoFile={share.file}
        onAdded={() => undefined}
        onAutoDone={() => void finish()}
      />
    );
  }

  const title =
    step === 'screen' ? 'Save this screen time?' : step === 'support' ? 'Support' : step === 'empty' ? 'Nothing to import' : 'Shared with Lock’in';

  return (
    <Sheet
      open
      onClose={() => void finish()}
      title={title}
      eyebrow={step === 'choose' ? 'What is this?' : undefined}
      footer={
        step === 'screen' ? (
          <div className="space-y-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => void saveScreenTime()}
              className="w-full h-12 rounded-xl bg-ink text-ground-chalk font-body-strong disabled:opacity-40"
            >
              {busy ? 'Saving…' : 'Save for today'}
            </button>
            <button
              type="button"
              onClick={() => void finish()}
              className="w-full py-1.5 text-center font-caption text-caption text-muted-text hover:text-ink"
            >
              Cancel
            </button>
          </div>
        ) : step === 'support' || step === 'empty' ? (
          <button type="button" onClick={() => void finish()} className="w-full h-12 rounded-xl bg-ink text-ground-chalk font-body-strong">
            Close
          </button>
        ) : undefined
      }
    >
      {step === 'empty' && (
        <p className="font-small text-small text-muted-text">
          Nothing came through. Share a screenshot, a timetable photo or some text from another app and choose Lock’in.
        </p>
      )}

      {step === 'support' && support && (
        <div className="space-y-3">
          <p className="font-small text-small text-muted-text">Your text was saved.</p>
          <SupportCard support={support} />
        </div>
      )}

      {step === 'screen' && proposal && (
        <div className="space-y-2">
          <p className="font-title text-title text-ink text-2xl">{formatMinutes(proposal.total_minutes)}</p>
          <p className="font-caption text-caption text-muted-text">
            Read from your screenshot ({proposal.confidence} confidence). It will be saved for {activeDate}.
          </p>
          {Object.keys(proposal.category_breakdown).length > 0 && (
            <ul className="font-small text-small text-ink space-y-0.5">
              {Object.entries(proposal.category_breakdown)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 4)
                .map(([cat, mins]) => (
                  <li key={cat}>
                    {cat}: {formatMinutes(mins)}
                  </li>
                ))}
            </ul>
          )}
        </div>
      )}

      {step === 'choose' && share && (
        <div className="space-y-3">
          {share.file && (
            <div className="space-y-2">
              <button type="button" disabled={busy} onClick={() => void readScreenTime()} className={ACTION_BTN}>
                <span className="material-symbols-outlined text-[22px]">{busy ? 'hourglass_top' : 'phone_android'}</span>
                <span>Screen time screenshot</span>
              </button>
              <button type="button" disabled={busy} onClick={() => setStep('timetable')} className={ACTION_BTN}>
                <span className="material-symbols-outlined text-[22px]">calendar_month</span>
                <span>Timetable or notice</span>
              </button>
            </div>
          )}
          {(share.text || !share.file) && (
            <div className="space-y-2">
              <label className="font-caption text-caption text-muted-text block" htmlFor="share-text">
                {share.file ? 'Or add the text as tasks' : 'Add as tasks'}
              </label>
              <textarea
                id="share-text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={4}
                maxLength={1000}
                className="w-full bg-surface border border-line rounded-lg px-3 py-2 font-small text-ink"
              />
              <button
                type="button"
                disabled={busy || !text.trim()}
                onClick={() => void addTasks()}
                className="w-full h-12 rounded-xl bg-ink text-ground-chalk font-body-strong disabled:opacity-40"
              >
                {busy ? 'Adding…' : 'Add as tasks'}
              </button>
            </div>
          )}
        </div>
      )}
    </Sheet>
  );
};
