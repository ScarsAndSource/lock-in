import React, { useEffect, useRef, useState } from 'react';
import { getFutureNote, markFutureNotePlayed } from '../../api/growth';
import type { FutureNote } from '../../api/growth';
import { CLS } from './ui';

interface Props {
  id: string;
  onClose: () => void;
}

/** Opened by the future-self push (/?a=future&id=...). Audio needs a tap on iOS anyway, so Play is a button. */
export const FutureSelfPlayer: React.FC<Props> = ({ id, onClose }) => {
  const [note, setNote] = useState<FutureNote | null>(null);
  const [missing, setMissing] = useState(false);
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    getFutureNote(id)
      .then((n) => {
        if (!cancelled) setNote(n);
      })
      .catch(() => {
        if (!cancelled) setMissing(true);
      });
    return () => {
      cancelled = true;
      audioRef.current?.pause();
    };
  }, [id]);

  const play = () => {
    if (!note?.audio_b64 || !note.audio_mime) return;
    audioRef.current?.pause();
    const a = new Audio(`data:${note.audio_mime};base64,${note.audio_b64}`);
    audioRef.current = a;
    a.onended = () => setPlaying(false);
    setPlaying(true);
    a.play().catch(() => setPlaying(false));
  };

  const done = () => {
    audioRef.current?.pause();
    if (note) markFutureNotePlayed(id).catch(() => undefined);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[70] bg-ground-chalk flex flex-col items-center justify-center px-6 text-center space-y-6 animate-fadeIn">
      <span className={CLS.label}>From you, earlier</span>
      {missing ? (
        <p className="font-section text-section text-ink">That note is gone.</p>
      ) : !note ? (
        <p className={CLS.muted}>Opening…</p>
      ) : (
        <>
          {note.text && <p className="font-title text-title text-ink text-xl leading-snug max-w-sm break-words">{note.text}</p>}
          {note.has_audio && (
            <button type="button" className={`${CLS.primary} px-8 flex items-center gap-2`} onClick={play} disabled={playing}>
              <span className="material-symbols-outlined text-[20px]">{playing ? 'graphic_eq' : 'play_arrow'}</span>
              {playing ? 'Playing…' : 'Play my note'}
            </button>
          )}
        </>
      )}
      <button type="button" className={CLS.ghost} onClick={done}>
        {missing ? 'Close' : 'I heard me'}
      </button>
    </div>
  );
};
