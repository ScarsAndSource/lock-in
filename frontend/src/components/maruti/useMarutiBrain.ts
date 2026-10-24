import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AFTER_REPLY, IDLE_CHATTER, IDLE_THOUGHTS, NUDGES, POKES, POKES_MANY, PONDER, THINKING, WAKE, WAVES, pick,
} from './lines';
import {
  ANGRY_BACK, BORED_BACK, COMFORT_END, EAVES, GREET_BACK, GUARD_LINES, JOKES, LAUGH_BACK, SAD_BACK, THANKS_BACK, TIRED_BACK, WIN_BACK,
} from './banter';
import type { Reaction } from './banter';

export type MarutiMood =
  | 'idle' | 'talking' | 'thinking' | 'ponder' | 'listening' | 'cheer' | 'twirl'
  | 'walk' | 'fly' | 'climb' | 'hang' | 'peek' | 'wave' | 'sleep'
  | 'laugh' | 'rofl' | 'sad' | 'strong' | 'serious' | 'eavesdrop';

const VOICE_KEY = 'lockin.maruti.voice';
const CALM_KEY = 'lockin.maruti.calm';
const TYPE_MS = 28;
const MAX_X = 0.45; // how far he strolls, as a fraction of his own width
const SLEEP_AFTER_MS = 75000;
const SOBER_MS = 30 * 60 * 1000;
const COMFORT_MS = 5 * 60 * 1000;
const EAVES_START_MS = 1100;
const EAVES_END_MS = 7000;
/** Moods a quick reaction leaves him in; when the reply is still pending he goes back to "thinking". */
const REACTION_MOODS: MarutiMood[] = ['laugh', 'rofl', 'wave', 'cheer', 'twirl', 'serious', 'sad', 'ponder'];

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

const clearTimer = (ref: { current: number | null }) => {
  if (ref.current !== null) {
    window.clearTimeout(ref.current);
    ref.current = null;
  }
};

export interface SayOptions {
  mood?: MarutiMood;
  speak?: boolean;
  hold?: number;
  /** Keep the given mood after the line is typed (used while he is mid-move). */
  keep?: boolean;
}

export interface MarutiBrain {
  mood: MarutiMood;
  bubble: string;
  x: number;
  y: number;
  flip: boolean;
  walkMs: number;
  calm: boolean;
  voice: boolean;
  /** True after a support reply: he stays still and serious everywhere. */
  quiet: boolean;
  /** You are sad: he grows and stands guard next to you. */
  comfort: boolean;
  /** The roaming overlay is him right now; the in-page sprite hides. */
  away: boolean;
  /** You are typing and he has gone to lean in on the input box. */
  eavesdrop: boolean;
  say: (text: string, opts?: SayOptions) => void;
  act: (mood: MarutiMood, ms?: number) => void;
  setAway: (on: boolean) => void;
  setComfort: (on: boolean, silent?: boolean) => void;
  react: (kind: Exclude<Reaction, 'crisis'>) => void;
  listening: () => void;
  stopListening: () => void;
  thinking: () => void;
  talkReply: (text: string, speak?: boolean) => void;
  finishTalk: () => void;
  poke: () => void;
  settle: () => void;
  sober: (on: boolean) => void;
  toggleCalm: () => void;
  toggleVoice: () => void;
}

/** What the sprite should actually show: serious after a support reply, standing tall while comforting. */
export function shownMood(b: Pick<MarutiBrain, 'mood' | 'comfort' | 'quiet'>): MarutiMood {
  if (b.mood === 'idle') {
    if (b.comfort) return 'strong';
    if (b.quiet) return 'serious';
  }
  return b.mood;
}

/**
 * Maruti's behaviour, one shared instance for the whole app. `wander` is true only while his own tab is open:
 * then he strolls, hovers, waves, jokes and rolls inside the hero. Everywhere else the roamer overlay drives him
 * through `act`/`say`. Wandering needs: idle, visible, not calm mode, not reduced motion, not sober, not comforting.
 */
export function useMarutiBrain(wander = true): MarutiBrain {
  const [mood, setMoodState] = useState<MarutiMood>('idle');
  const [bubble, setBubble] = useState('');
  const [x, setX] = useState(0);
  const [y, setY] = useState(0);
  const [flip, setFlip] = useState(false);
  const [walkMs, setWalkMs] = useState(1400);
  const [quiet, setQuiet] = useState(false);
  const [comfort, setComfortState] = useState(false);
  const [away, setAwayState] = useState(false);
  const [eavesdrop, setEavesdrop] = useState(false);
  const [calm, setCalm] = useState<boolean>(() => readFlag(CALM_KEY));
  const [voice, setVoice] = useState<boolean>(() => readFlag(VOICE_KEY));

  const moodRef = useRef<MarutiMood>('idle');
  const xRef = useRef(0);
  const wanderRef = useRef(wander);
  const calmRef = useRef(calm);
  const voiceRef = useRef(voice);
  const soberRef = useRef(false);
  const comfortRef = useRef(false);
  const eavesRef = useRef(false);
  const speakingRef = useRef(false);
  const typedDoneRef = useRef(true);
  const typeTimer = useRef<number | null>(null);
  const holdTimer = useRef<number | null>(null);
  const moodTimer = useRef<number | null>(null);
  const listenTimer = useRef<number | null>(null);
  const nudgeTimer = useRef<number | null>(null);
  const followTimer = useRef<number | null>(null);
  const safetyTimer = useRef<number | null>(null);
  const soberTimer = useRef<number | null>(null);
  const comfortTimer = useRef<number | null>(null);
  const resumeTimer = useRef<number | null>(null);
  const jokeTimer = useRef<number | null>(null);
  const eavesStartTimer = useRef<number | null>(null);
  const eavesEndTimer = useRef<number | null>(null);
  const pokes = useRef({ count: 0, last: 0 });
  const lastLine = useRef<string | undefined>(undefined);
  const lastThought = useRef(0);
  const lastActive = useRef(Date.now());

  wanderRef.current = wander;
  calmRef.current = calm;
  voiceRef.current = voice;

  const setMood = useCallback((m: MarutiMood) => {
    moodRef.current = m;
    setMoodState(m);
  }, []);

  const setAway = useCallback((on: boolean) => setAwayState(on), []);

  const cancelSpeech = useCallback(() => {
    speakingRef.current = false;
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel();
  }, []);

  const stopTalk = useCallback(() => {
    clearTimer(typeTimer);
    clearTimer(holdTimer);
    clearTimer(moodTimer);
    clearTimer(listenTimer);
    clearTimer(nudgeTimer);
    clearTimer(followTimer);
    clearTimer(safetyTimer);
    clearTimer(resumeTimer);
    clearTimer(jokeTimer);
    cancelSpeech();
  }, [cancelSpeech]);

  /** He stops leaning in on the input box. */
  const stopEaves = useCallback(() => {
    clearTimer(eavesStartTimer);
    clearTimer(eavesEndTimer);
    if (eavesRef.current) {
      eavesRef.current = false;
      setEavesdrop(false);
    }
  }, []);

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

  /** Set a mood directly (the roamer uses this). ms > 0 returns to idle afterwards; 0 stays until changed. */
  const act = useCallback(
    (m: MarutiMood, ms = 0) => {
      clearTimer(moodTimer);
      setMood(m);
      if (ms > 0) moodTimer.current = window.setTimeout(() => setMood('idle'), ms);
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
          if (!opts.keep) toIdle(500);
          holdTimer.current = window.setTimeout(() => setBubble(''), opts.hold ?? 4500);
        }
      }, TYPE_MS);
      if (voiceRef.current && opts.speak !== false) speak(text);
    },
    [setMood, speak, stopTalk, toIdle],
  );

  /** Turn comfort mode (he grows and stands guard) on or off. It also expires by itself. */
  const setComfort = useCallback(
    (on: boolean, silent = false) => {
      const was = comfortRef.current;
      comfortRef.current = on;
      setComfortState(on);
      clearTimer(comfortTimer);
      if (on) {
        stopEaves();
        comfortTimer.current = window.setTimeout(() => {
          comfortRef.current = false;
          setComfortState(false);
        }, COMFORT_MS);
      } else if (was && !silent && !soberRef.current) {
        say(pick(COMFORT_END, lastLine.current), { speak: false });
      }
    },
    [say, stopEaves],
  );

  const endTalkIfDone = useCallback(() => {
    if (moodRef.current === 'talking' && typedDoneRef.current && !speakingRef.current) toIdle(150);
  }, [toIdle]);

  /** The chat reply is being typed into its bubble: move the mouth (and read it aloud if voice is on). */
  const talkReply = useCallback(
    (text: string, speakIt = true) => {
      stopTalk();
      stopEaves();
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
    [cancelSpeech, endTalkIfDone, setMood, speak, stopEaves, stopTalk, toIdle],
  );

  const finishTalk = useCallback(() => {
    typedDoneRef.current = true;
    endTalkIfDone();
    // Now and then he adds a little something after a reply, never in a serious moment.
    if (!soberRef.current && !comfortRef.current && Math.random() < 0.3) {
      clearTimer(followTimer);
      followTimer.current = window.setTimeout(() => {
        if (!soberRef.current && !comfortRef.current && moodRef.current === 'idle') {
          say(pick(AFTER_REPLY, lastLine.current), { mood: 'cheer', speak: false, hold: 4000 });
        }
      }, 1400);
    }
  }, [endTalkIfDone, say]);

  const thinking = useCallback(() => {
    stopTalk();
    stopEaves();
    typedDoneRef.current = true;
    lastThought.current = 0;
    setMood('thinking');
    setBubble(pick(THINKING, lastLine.current));
    holdTimer.current = window.setTimeout(() => setBubble(''), 6000);
  }, [setMood, stopEaves, stopTalk]);

  /** You just sent a message and he reacts to what it says; he goes back to thinking while the reply loads. */
  const react = useCallback(
    (kind: Exclude<Reaction, 'crisis'>) => {
      if (soberRef.current) {
        thinking();
        return;
      }
      const last = lastLine.current;
      let ms = 1500;
      const line = (pool: readonly string[], m: MarutiMood, hold = 3200) =>
        say(pick(pool, last), { mood: m, keep: true, speak: false, hold });
      switch (kind) {
        case 'laugh':
          ms = 2300;
          line(LAUGH_BACK, Math.random() < 0.45 ? 'rofl' : 'laugh');
          break;
        case 'greet':
          line(GREET_BACK, 'wave');
          break;
        case 'thanks':
          line(THANKS_BACK, 'cheer');
          break;
        case 'win':
          ms = 1800;
          line(WIN_BACK, 'cheer');
          break;
        case 'tired':
          ms = 1800;
          line(TIRED_BACK, 'ponder', 4000);
          break;
        case 'bored':
          line(BORED_BACK, 'twirl');
          break;
        case 'angry':
          line(ANGRY_BACK, 'serious', 4000);
          break;
        case 'sad':
          ms = 2600;
          line(SAD_BACK, 'sad', 7000);
          setComfort(true);
          break;
      }
      clearTimer(resumeTimer);
      resumeTimer.current = window.setTimeout(() => {
        if (REACTION_MOODS.includes(moodRef.current)) thinking();
      }, ms);
    },
    [say, setComfort, thinking],
  );

  /** You are typing: he thinks, offers a "hmm", leans in on the input box, and nudges if you stall. */
  const listening = useCallback(() => {
    const m = moodRef.current;
    if (m === 'thinking' || m === 'talking' || m === 'sleep') return;
    if (m !== 'ponder') {
      clearTimer(moodTimer);
      setMood('ponder');
    }
    const now = Date.now();
    if (!soberRef.current && now - lastThought.current > 5500) {
      lastThought.current = now;
      const pool = comfortRef.current ? GUARD_LINES : eavesRef.current ? EAVES : PONDER;
      const line = pick(pool, lastLine.current);
      lastLine.current = line;
      setBubble(line);
      clearTimer(holdTimer);
      holdTimer.current = window.setTimeout(() => setBubble(''), 2600);
    }
    clearTimer(listenTimer);
    listenTimer.current = window.setTimeout(() => {
      if (moodRef.current === 'ponder') setMood('idle');
    }, 2600);
    clearTimer(nudgeTimer);
    if (!comfortRef.current) {
      nudgeTimer.current = window.setTimeout(() => {
        if (!soberRef.current && moodRef.current === 'idle') say(pick(NUDGES, lastLine.current), { speak: false });
      }, 8000);
    }
    if (!soberRef.current && !comfortRef.current && !calmRef.current && !prefersReducedMotion()) {
      if (!eavesRef.current && eavesStartTimer.current === null) {
        eavesStartTimer.current = window.setTimeout(() => {
          eavesStartTimer.current = null;
          eavesRef.current = true;
          setEavesdrop(true);
        }, EAVES_START_MS);
      }
      clearTimer(eavesEndTimer);
      eavesEndTimer.current = window.setTimeout(() => stopEaves(), EAVES_END_MS);
    }
  }, [say, setMood, stopEaves]);

  /** The input was cleared: stop thinking, stop nudging, come back from the input box. */
  const stopListening = useCallback(() => {
    clearTimer(listenTimer);
    clearTimer(nudgeTimer);
    stopEaves();
    if (moodRef.current === 'ponder') setMood('idle');
  }, [setMood, stopEaves]);

  const poke = useCallback(() => {
    const now = Date.now();
    pokes.current.count = now - pokes.current.last < 4000 ? pokes.current.count + 1 : 1;
    pokes.current.last = now;
    const n = pokes.current.count;
    if (comfortRef.current || soberRef.current) {
      say(pick(GUARD_LINES, lastLine.current), { speak: false, hold: 4000 });
    } else if (n >= 6) {
      pokes.current.count = 0;
      say(pick(POKES_MANY, lastLine.current), { mood: 'rofl', hold: 5000 });
    } else if (n === 3) {
      say('Arre wah, ab hanste hain. Haha!', { mood: 'laugh', speak: false });
    } else {
      say(pick(POKES, lastLine.current), { mood: 'twirl', speak: false });
    }
  }, [say]);

  const settle = useCallback(() => {
    stopTalk();
    stopEaves();
    typedDoneRef.current = true;
    lastThought.current = 0;
    setBubble('');
    setMood('idle');
  }, [setMood, stopEaves, stopTalk]);

  const sober = useCallback(
    (on: boolean) => {
      soberRef.current = on;
      setQuiet(on);
      clearTimer(soberTimer);
      if (on) {
        setComfort(false, true);
        stopTalk();
        stopEaves();
        typedDoneRef.current = true;
        setMood('idle');
        soberTimer.current = window.setTimeout(() => {
          soberRef.current = false;
          setQuiet(false);
        }, SOBER_MS);
      }
    },
    [setComfort, setMood, stopEaves, stopTalk],
  );

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

  // Leaving his own tab: park him back at the centre of the hero for next time.
  useEffect(() => {
    if (!wander) {
      xRef.current = 0;
      setX(0);
      setY(0);
      stopEaves();
    }
  }, [wander, stopEaves]);

  // Wandering inside the hero: strolls, hovers, waves, tells jokes and laughs at them, now and then rolls.
  useEffect(() => {
    if (calm || prefersReducedMotion()) return;
    let id: number;
    const pickX = (range: number) => {
      let nx = (Math.random() * 2 - 1) * range;
      if (Math.abs(nx - xRef.current) < 0.2) nx = xRef.current > 0 ? -range * 0.8 : range * 0.8;
      return nx;
    };
    const move = (nx: number, m: MarutiMood, ms: number, ny: number) => {
      setFlip(nx < xRef.current);
      xRef.current = nx;
      setX(nx);
      setY(ny);
      setWalkMs(ms);
      setMood(m);
      clearTimer(moodTimer);
      moodTimer.current = window.setTimeout(() => {
        setWalkMs(700);
        setY(0);
        setMood('idle');
      }, ms + 100);
    };
    const joke = () => {
      const text = pick(JOKES, lastLine.current);
      say(text, { mood: 'talking', keep: true, speak: false, hold: 4500 });
      jokeTimer.current = window.setTimeout(() => {
        if (soberRef.current || comfortRef.current || !wanderRef.current) return;
        if (Math.random() < 0.45) move(pickX(0.6), 'rofl', 2200, 0);
        else act('laugh', 1800);
      }, Math.min(text.length, 90) * TYPE_MS + 400);
    };
    const tick = () => {
      id = window.setTimeout(() => {
        if (
          wanderRef.current && document.visibilityState === 'visible' && moodRef.current === 'idle' &&
          !soberRef.current && !comfortRef.current
        ) {
          const r = Math.random();
          if (r < 0.28) move(pickX(MAX_X), 'walk', 1400, 0);
          else if (r < 0.4) {
            setMood('twirl');
            clearTimer(moodTimer);
            moodTimer.current = window.setTimeout(() => setMood('idle'), 1200);
          } else if (r < 0.55) move(pickX(0.85), 'fly', 1900, -0.09);
          else if (r < 0.66) say(pick(WAVES, lastLine.current), { mood: 'wave', speak: false });
          else if (r < 0.78) say(pick(IDLE_CHATTER, lastLine.current), { speak: false });
          else if (r < 0.88) say(pick(IDLE_THOUGHTS, lastLine.current), { mood: 'ponder', speak: false, hold: 3500 });
          else joke();
        }
        tick();
      }, 5000 + Math.random() * 4500);
    };
    tick();
    return () => window.clearTimeout(id);
  }, [calm, say, act, setMood]);

  // While he stands guard next to you, a steady word now and then.
  useEffect(() => {
    const id = window.setInterval(() => {
      if (!comfortRef.current || soberRef.current || document.visibilityState !== 'visible' || moodRef.current !== 'idle') return;
      say(pick(GUARD_LINES, lastLine.current), { speak: false, hold: 5000 });
    }, 30000);
    return () => window.clearInterval(id);
  }, [say]);

  // No touch or key for a while: he dozes off. Any touch, tap or key wakes him.
  useEffect(() => {
    const bump = () => {
      lastActive.current = Date.now();
      if (moodRef.current === 'sleep') {
        setMood('idle');
        say(pick(WAKE), { speak: false });
      }
    };
    const events = ['pointerdown', 'keydown', 'touchstart'] as const;
    events.forEach((e) => window.addEventListener(e, bump, { passive: true }));
    const id = window.setInterval(() => {
      if (document.visibilityState !== 'visible' || moodRef.current !== 'idle' || soberRef.current || comfortRef.current) return;
      if (Date.now() - lastActive.current < SLEEP_AFTER_MS) return;
      stopTalk();
      setBubble('Zzz…');
      setMood('sleep');
    }, 5000);
    return () => {
      events.forEach((e) => window.removeEventListener(e, bump));
      window.clearInterval(id);
    };
  }, [say, setMood, stopTalk]);

  // Never leave a timer or a voice running behind a screen that is gone.
  useEffect(
    () => () => {
      stopTalk();
      stopEaves();
      clearTimer(soberTimer);
      clearTimer(comfortTimer);
    },
    [stopEaves, stopTalk],
  );

  return {
    mood, bubble, x, y, flip, walkMs, calm, voice, quiet, comfort, away, eavesdrop,
    say, act, setAway, setComfort, react, listening, stopListening, thinking, talkReply, finishTalk,
    poke, settle, sober, toggleCalm, toggleVoice,
  };
}
