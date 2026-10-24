import { useCallback, useEffect, useRef, useState } from 'react';
import { IDLE_CHATTER, LISTENING, POKES, POKES_MANY, THINKING, pick } from './lines';

export type MarutiMood = 'idle' | 'talking' | 'thinking' | 'listening' | 'cheer' | 'twirl' | 'walk';

const VOICE_KEY = 'lockin.maruti.voice';
const CALM_KEY = 'lockin.maruti.calm';
const TYPE_MS = 28;
const WALK_MS = 1400;
const MAX_X = 0.45; // how far he strolls, as a fraction of his own width

const readFlag = (key: string): boolean => {
  try {
    return localStorage.getItem(key) === '1';
  } catch {
    return false;
  }
};
const writeFlag = (key: string, on: boolean): void => {
  try {
    localStorage.setItem(key, on ? '1' : '0');
  } catch {
    /* preferences are a convenience */
  }
};
const prefersReducedMotion = (): boolean =>
  typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export interface SayOptions {
  mood?: MarutiMood;
  speak?: boolean;
  hold?: number;
}

export interface MarutiBrain {
  mood: MarutiMood;
  bubble: string;
  x: number;
  flip: boolean;
  walkMs: number;
  calm: boolean;
  voice: boolean;
  say: (text: string, opts?: SayOptions) => void;
  listening: () => void;
  thinking: () => void;
  talkReply: (text: string, speak?: boolean) => void;
  finishTalk: () => void;
  poke: () => void;
  settle: () => void;
  sober: (on: boolean) => void;
  toggleCalm: () => void;
  toggleVoice: () => void;
}

/**
 * Maruti's behaviour: what he does while you type, wait, read and tap. One small state machine.
 * He strolls and twirls the gada on his own only when idle, never in calm mode, never with reduced motion,
 * and never during a support reply (sober).
 */
export function useMarutiBrain(): MarutiBrain {
  const [mood, setMoodState] = useState<MarutiMood>('idle');
  const [bubble, setBubble] = useState('');
  const [x, setX] = useState(0);
  const [flip, setFlip] = useState(false);
  const [calm, setCalm] = useState<boolean>(() => readFlag(CALM_KEY));
  const [voice, setVoice] = useState<boolean>(() => readFlag(VOICE_KEY));

  const moodRef = useRef<MarutiMood>('idle');
  const xRef = useRef(0);
  const calmRef = useRef(calm);
  const voiceRef = useRef(voice);
  const soberRef = useRef(false);
  const speakingRef = useRef(false);
  const typedDoneRef = useRef(true);
  const typeTimer = useRef<number | null>(null);
  const holdTimer = useRef<number | null>(null);
  const moodTimer = useRef<number | null>(null);
  const listenTimer = useRef<number | null>(null);
  const safetyTimer = useRef<number | null>(null);
  const pokes = useRef({ count: 0, last: 0 });
  const lastLine = useRef<string | undefined>(undefined);

  calmRef.current = calm;
  voiceRef.current = voice;

  const setMood = useCallback((m: MarutiMood) => {
    moodRef.current = m;
    setMoodState(m);
  }, []);

  const clearTimer = (ref: { current: number | null }) => {
    if (ref.current !== null) {
      window.clearTimeout(ref.current);
      ref.current = null;
    }
  };

  const cancelSpeech = useCallback(() => {
    speakingRef.current = false;
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel();
  }, []);

  const stopTalk = useCallback(() => {
    clearTimer(typeTimer);
    clearTimer(holdTimer);
    clearTimer(moodTimer);
    clearTimer(listenTimer);
    clearTimer(safetyTimer);
    cancelSpeech();
  }, [cancelSpeech]);

  const speak = useCallback((text: string, onEnd?: () => void) => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      onEnd?.();
      return;
    }
    const synth = window.speechSynthesis;
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text.replace(/\s+/g, ' ').slice(0, 600));
    const voices = synth.getVoices();
    const v = voices.find((c) => /en[-_]IN/i.test(c.lang)) ?? voices.find((c) => /hi[-_]IN/i.test(c.lang));
    if (v) {
      u.voice = v;
      u.lang = v.lang;
    } else {
      u.lang = 'en-IN';
    }
    u.rate = 1;
    u.pitch = 0.85;
    speakingRef.current = true;
    const done = () => {
      speakingRef.current = false;
      onEnd?.();
    };
    u.onend = done;
    u.onerror = done;
    synth.speak(u);
  }, []);

  const toIdle = useCallback(
    (afterMs = 0) => {
      clearTimer(moodTimer);
      moodTimer.current = window.setTimeout(() => setMood('idle'), afterMs);
    },
    [setMood],
  );

  /** A line in his speech bubble, typed out, with the mouth moving. */
  const say = useCallback(
    (text: string, opts: SayOptions = {}) => {
      stopTalk();
      lastLine.current = text;
      setMood(opts.mood ?? 'talking');
      setBubble('');
      let i = 0;
      const step = Math.max(1, Math.ceil(text.length / 90));
      typeTimer.current = window.setInterval(() => {
        i = Math.min(text.length, i + step);
        setBubble(text.slice(0, i));
        if (i >= text.length) {
          clearTimer(typeTimer);
          toIdle(500);
          holdTimer.current = window.setTimeout(() => setBubble(''), opts.hold ?? 4500);
        }
      }, TYPE_MS);
      if (voiceRef.current && opts.speak !== false) speak(text);
    },
    [setMood, speak, stopTalk, toIdle],
  );

  const endTalkIfDone = useCallback(() => {
    if (moodRef.current === 'talking' && typedDoneRef.current && !speakingRef.current) toIdle(150);
  }, [toIdle]);

  /** The chat reply is being typed into its bubble: move the mouth (and read it aloud if voice is on). */
  const talkReply = useCallback(
    (text: string, speakIt = true) => {
      stopTalk();
      setBubble('');
      setMood('talking');
      typedDoneRef.current = false;
      safetyTimer.current = window.setTimeout(() => {
        typedDoneRef.current = true;
        cancelSpeech();
        toIdle(0);
      }, 14000);
      if (voiceRef.current && speakIt) speak(text, endTalkIfDone);
    },
    [cancelSpeech, endTalkIfDone, setMood, speak, stopTalk, toIdle],
  );

  const finishTalk = useCallback(() => {
    typedDoneRef.current = true;
    endTalkIfDone();
  }, [endTalkIfDone]);

  const thinking = useCallback(() => {
    stopTalk();
    typedDoneRef.current = true;
    setMood('thinking');
    setBubble(pick(THINKING, lastLine.current));
    holdTimer.current = window.setTimeout(() => setBubble(''), 6000);
  }, [setMood, stopTalk]);

  const listening = useCallback(() => {
    if (moodRef.current === 'thinking' || moodRef.current === 'talking') return;
    if (moodRef.current !== 'listening') {
      clearTimer(moodTimer);
      setMood('listening');
      if (!soberRef.current) {
        const line = pick(LISTENING, lastLine.current);
        lastLine.current = line;
        setBubble(line);
        clearTimer(holdTimer);
        holdTimer.current = window.setTimeout(() => setBubble(''), 2200);
      }
    }
    clearTimer(listenTimer);
    listenTimer.current = window.setTimeout(() => {
      if (moodRef.current === 'listening') setMood('idle');
    }, 2500);
  }, [setMood]);

  const poke = useCallback(() => {
    const now = Date.now();
    pokes.current.count = now - pokes.current.last < 4000 ? pokes.current.count + 1 : 1;
    pokes.current.last = now;
    const n = pokes.current.count;
    if (n >= 6) {
      pokes.current.count = 0;
      say(pick(POKES_MANY, lastLine.current), { mood: 'cheer', hold: 5000 });
    } else if (n === 3) {
      say('Arre wah, ab hanste hain.', { mood: 'cheer', speak: false });
    } else {
      say(pick(POKES, lastLine.current), { mood: 'twirl', speak: false });
    }
  }, [say]);

  const settle = useCallback(() => {
    stopTalk();
    typedDoneRef.current = true;
    setBubble('');
    setMood('idle');
  }, [setMood, stopTalk]);

  const sober = useCallback((on: boolean) => {
    soberRef.current = on;
    if (on) {
      stopTalk();
      typedDoneRef.current = true;
      setMood('idle');
    }
  }, [setMood, stopTalk]);

  const toggleCalm = useCallback(() => {
    setCalm((c) => {
      writeFlag(CALM_KEY, !c);
      return !c;
    });
  }, []);

  const toggleVoice = useCallback(() => {
    setVoice((v) => {
      writeFlag(VOICE_KEY, !v);
      if (v) cancelSpeech();
      return !v;
    });
  }, [cancelSpeech]);

  // Wandering: only when idle, visible, and the person hasn't asked for calm.
  useEffect(() => {
    if (calm || prefersReducedMotion()) return;
    let id: number;
    const tick = () => {
      id = window.setTimeout(() => {
        if (document.visibilityState === 'visible' && moodRef.current === 'idle' && !soberRef.current) {
          const r = Math.random();
          if (r < 0.6) {
            let nx = (Math.random() * 2 - 1) * MAX_X;
            if (Math.abs(nx - xRef.current) < 0.2) nx = xRef.current > 0 ? -MAX_X * 0.8 : MAX_X * 0.8;
            setFlip(nx < xRef.current);
            xRef.current = nx;
            setX(nx);
            setMood('walk');
            clearTimer(moodTimer);
            moodTimer.current = window.setTimeout(() => setMood('idle'), WALK_MS);
          } else if (r < 0.85) {
            setMood('twirl');
            clearTimer(moodTimer);
            moodTimer.current = window.setTimeout(() => setMood('idle'), 1200);
          } else {
            say(pick(IDLE_CHATTER, lastLine.current), { speak: false });
          }
        }
        tick();
      }, 6500 + Math.random() * 5500);
    };
    tick();
    return () => window.clearTimeout(id);
  }, [calm, say, setMood]);

  // Never leave a timer or a voice running behind a screen that is gone.
  useEffect(
    () => () => {
      stopTalk();
    },
    [stopTalk],
  );

  return {
    mood, bubble, x, flip, walkMs: WALK_MS, calm, voice,
    say, listening, thinking, talkReply, finishTalk, poke, settle, sober, toggleCalm, toggleVoice,
  };
}
