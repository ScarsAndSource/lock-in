import { useCallback, useEffect, useRef, useState } from 'react';

export const MAX_RECORD_SECONDS = 60; // the backend rejects ~4 MB; 60 s of opus at 32 kbps is ~240 KB

// Backend accepts webm, ogg, mp4/m4a, wav, mp3. Chrome/Android -> webm, Safari/iOS -> mp4, Firefox -> ogg.
const MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/ogg'];

export function recorderSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof MediaRecorder !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia
  );
}

function pickMime(): string | undefined {
  return MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m));
}

function micErrorMessage(err: unknown): string {
  const name = err instanceof DOMException ? err.name : '';
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'Microphone is blocked. Allow it for this site in your browser settings.';
  }
  if (name === 'NotFoundError') return 'No microphone found on this device.';
  return 'Could not start the microphone.';
}

interface Options {
  /** Called with the recording when it stops (tap, or the time cap). Not called after cancel(). */
  onFinished: (blob: Blob) => void;
  onError: (message: string) => void;
}

/** Tap to start, tap to stop. Mic tracks are always released, including on unmount. */
export function useVoiceRecorder({ onFinished, onError }: Options) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const discardRef = useRef(false);
  const cb = useRef({ onFinished, onError });
  cb.current = { onFinished, onError };

  const release = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    recorderRef.current = null;
    setRecording(false);
    setSeconds(0);
  }, []);

  const stop = useCallback(() => {
    const rec = recorderRef.current;
    if (rec && rec.state !== 'inactive') rec.stop();
  }, []);

  const cancel = useCallback(() => {
    discardRef.current = true;
    const rec = recorderRef.current;
    if (rec && rec.state !== 'inactive') rec.stop();
    else release();
  }, [release]);

  const start = useCallback(async () => {
    if (recorderRef.current) return;
    if (!recorderSupported()) {
      cb.current.onError('Voice input is not supported in this browser.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mimeType = pickMime();
      const rec = new MediaRecorder(stream, { ...(mimeType ? { mimeType } : {}), audioBitsPerSecond: 32000 });
      chunksRef.current = [];
      discardRef.current = false;
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = () => {
        const type = rec.mimeType || mimeType || 'audio/webm';
        const blob = new Blob(chunksRef.current, { type });
        const discard = discardRef.current;
        release();
        if (discard) return;
        if (blob.size === 0) cb.current.onError('The recording was empty. Try again.');
        else cb.current.onFinished(blob);
      };
      recorderRef.current = rec;
      rec.start();
      setRecording(true);
      setSeconds(0);
      timerRef.current = window.setInterval(() => {
        setSeconds((s) => {
          if (s + 1 >= MAX_RECORD_SECONDS) {
            // Auto-stop at the cap. Deferred so we never call stop() inside a state updater.
            window.setTimeout(() => stop(), 0);
          }
          return s + 1;
        });
      }, 1000);
    } catch (err: unknown) {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      recorderRef.current = null;
      cb.current.onError(micErrorMessage(err));
    }
  }, [release, stop]);

  // Leaving the screen mid-recording drops the audio and frees the microphone.
  useEffect(() => cancel, [cancel]);

  return { supported: recorderSupported(), recording, seconds, start, stop, cancel };
}
