import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useApp } from '../../context/AppContext';
import { useVoiceRecorder } from '../../hooks/useVoiceRecorder';
import {
  blobToBase64, createFutureNote, deleteFutureNote, getFutureNote, listFutureNotes, setFutureNoteActive,
} from '../../api/growth';
import type { FutureNote } from '../../api/growth';
import { errorMessage } from '../../lib/format';
import { CLS } from './ui';

const VOICE_SECONDS = 20;

export const FutureSelfCard: React.FC = () => {
  const { showToast } = useApp();
  const [notes, setNotes] = useState<FutureNote[]>([]);
  const [adding, setAdding] = useState(false);
  const [text, setText] = useState('');
  const [blob, setBlob] = useState<Blob | null>(null);
  const [dur, setDur] = useState(0);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [whenMode, setWhenMode] = useState<'slip' | 'at'>('slip');
  const [at, setAt] = useState('23:00');
  const [busy, setBusy] = useState(false);
  const secRef = useRef(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const rec = useVoiceRecorder({
    onFinished: (b) => {
      setBlob(b);
      setDur(Math.max(1, secRef.current));
    },
    onError: showToast,
  });
  if (rec.recording) secRef.current = rec.seconds;

  useEffect(() => {
    if (rec.recording && rec.seconds >= VOICE_SECONDS) rec.stop();
  }, [rec.recording, rec.seconds, rec.stop]);

  useEffect(() => {
    if (!blob) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(blob);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [blob]);

  useEffect(() => () => audioRef.current?.pause(), []);

  const load = useCallback(() => {
    listFutureNotes()
      .then(setNotes)
      .catch(() => setNotes([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const reset = () => {
    setAdding(false);
    setText('');
    setBlob(null);
    setDur(0);
    setWhenMode('slip');
    setAt('23:00');
  };

  const save = async () => {
    setBusy(true);
    try {
      await createFutureNote({
        text: text.trim() || null,
        audio_b64: blob ? await blobToBase64(blob) : null,
        audio_mime: blob ? blob.type || 'audio/webm' : null,
        duration_s: blob ? dur : null,
        send_at: whenMode === 'at' ? at : null,
      });
      showToast('Saved. It will find you at the right time.');
      reset();
      load();
    } catch (err) {
      showToast(errorMessage(err, 'Could not save that'));
    } finally {
      setBusy(false);
    }
  };

  const play = async (id: string) => {
    try {
      const n = await getFutureNote(id);
      if (!n.audio_b64 || !n.audio_mime) return;
      audioRef.current?.pause();
      const a = new Audio(`data:${n.audio_mime};base64,${n.audio_b64}`);
      audioRef.current = a;
      await a.play();
    } catch (err) {
      showToast(errorMessage(err, 'Could not play that'));
    }
  };

  const toggle = (n: FutureNote) =>
    setFutureNoteActive(n.id, !n.active)
      .then(load)
      .catch((err: unknown) => showToast(errorMessage(err, 'Could not change that')));

  const remove = (n: FutureNote) => {
    if (!window.confirm('Delete this note?')) return;
    deleteFutureNote(n.id)
      .then(load)
      .catch((err: unknown) => showToast(errorMessage(err, 'Could not delete that')));
  };

  const hasContent = text.trim().length > 0 || blob !== null;

  return (
    <div className="space-y-3">
      <p className={CLS.muted}>
        Record 20 seconds or write a line to the you who usually slips. It arrives at that exact time, and you tap to open it.
      </p>

      {notes.length > 0 && (
        <ul className="space-y-2">
          {notes.map((n) => (
            <li key={n.id} className={`px-3 py-2.5 border border-line rounded-xl bg-surface ${n.active ? '' : 'opacity-60'}`}>
              <p className="font-small text-small text-ink break-words">
                {n.text ?? `Voice note · ${n.duration_s ?? '?'}s`}
              </p>
              <p className={`${CLS.muted} mt-0.5`}>
                {n.send_at ? `at ${n.send_at}` : 'at my usual slip time'}
                {n.text && n.has_audio ? ` · plus a ${n.duration_s ?? '?'}s voice note` : ''}
                {n.active ? '' : ' · paused'}
              </p>
              <div className="flex gap-2 mt-2">
                {n.has_audio && (
                  <button type="button" className={CLS.ghost} onClick={() => void play(n.id)}>
                    Play
                  </button>
                )}
                <button type="button" className={CLS.ghost} onClick={() => void toggle(n)}>
                  {n.active ? 'Pause' : 'Resume'}
                </button>
                <button type="button" className={CLS.ghost} onClick={() => remove(n)}>
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {!adding ? (
        <button type="button" className={`${CLS.primary} w-full`} onClick={() => setAdding(true)}>
          Write a note to future me
        </button>
      ) : (
        <div className="space-y-3 pt-1">
          <textarea
            className={CLS.area}
            rows={2}
            maxLength={280}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="bro, you’ll regret this at 8am"
          />

          {rec.supported && (
            <div className="flex items-center gap-3">
              <button
                type="button"
                className={`${CLS.ghost} flex items-center gap-1.5`}
                onClick={() => (rec.recording ? rec.stop() : void rec.start())}
                disabled={busy}
              >
                <span className={`material-symbols-outlined text-[18px] ${rec.recording ? 'animate-pulse' : ''}`}>
                  {rec.recording ? 'stop' : 'mic'}
                </span>
                {rec.recording ? `Stop (${rec.seconds}/${VOICE_SECONDS}s)` : blob ? 'Record again' : 'Record voice'}
              </button>
              {blob && previewUrl && !rec.recording && <audio controls src={previewUrl} className="h-9 min-w-0 flex-1" />}
            </div>
          )}

          <fieldset className="space-y-1.5">
            <legend className={CLS.label}>When should it play?</legend>
            <label className="flex items-center gap-2 font-small text-small text-ink">
              <input type="radio" name="when" checked={whenMode === 'slip'} onChange={() => setWhenMode('slip')} className="accent-black" />
              When I usually slip (learned from my urges, else 11 pm)
            </label>
            <label className="flex items-center gap-2 font-small text-small text-ink">
              <input type="radio" name="when" checked={whenMode === 'at'} onChange={() => setWhenMode('at')} className="accent-black" />
              At
              <input type="time" value={at} onChange={(e) => setAt(e.target.value)} disabled={whenMode !== 'at'} className="h-9 px-2 bg-surface border border-line rounded-lg" />
            </label>
          </fieldset>

          <div className="flex gap-2">
            <button type="button" className={CLS.ghost} onClick={reset} disabled={busy || rec.recording}>
              Cancel
            </button>
            <button type="button" className={`${CLS.primary} flex-1`} onClick={() => void save()} disabled={busy || rec.recording || !hasContent}>
              {busy ? 'Saving…' : 'Save note'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
