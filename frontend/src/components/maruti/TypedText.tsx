import React, { useEffect, useRef, useState } from 'react';

interface TypedTextProps {
  text: string;
  /** Typing always finishes within this many ms, however long the reply is. */
  capMs?: number;
  onDone?: () => void;
  onProgress?: () => void;
}

const TICK_MS = 28;

/** Types a fresh reply out so Maruti's mouth has something to match. Tap the text to skip. Screen readers get it whole. */
export const TypedText: React.FC<TypedTextProps> = ({ text, capMs = 3000, onDone, onProgress }) => {
  const [n, setN] = useState(0);
  const doneRef = useRef(onDone);
  const progressRef = useRef(onProgress);
  doneRef.current = onDone;
  progressRef.current = onProgress;

  useEffect(() => {
    setN(0);
    const step = Math.max(1, Math.ceil(text.length / (capMs / TICK_MS)));
    const id = window.setInterval(() => {
      setN((prev) => {
        const next = Math.min(text.length, prev + step);
        if (next >= text.length) window.clearInterval(id);
        return next;
      });
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, [text, capMs]);

  const finished = n >= text.length;
  useEffect(() => {
    progressRef.current?.();
    if (finished) doneRef.current?.();
  }, [n, finished]);

  return (
    <p onClick={() => setN(text.length)}>
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">{text.slice(0, n)}</span>
    </p>
  );
};
