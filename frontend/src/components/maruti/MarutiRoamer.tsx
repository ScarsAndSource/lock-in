import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useApp } from '../../context/AppContext';
import type { Tab } from '../../context/AppContext';
import { useMaruti } from './MarutiContext';
import { MarutiSprite } from './MarutiSprite';
import type { MarutiMood } from './useMarutiBrain';
import { CLIMB_LINES, FLY_LINES, PEEK_LINES, POKES, SIDE_LINES, TAB_LINES, WALK_LINES, pick } from './lines';

const SIZE = 64;
const H = Math.round((SIZE * 227) / 177);
const TABS: Tab[] = ['now', 'companion', 'mirror', 'crew'];
const EASE = 'cubic-bezier(.45,.05,.55,.95)';
const POP = 'cubic-bezier(.2,1.35,.4,1)';

const rand = (a: number, b: number) => a + Math.random() * (b - a);
const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));
const prefersReducedMotion = (): boolean =>
  typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

interface Pose {
  x: number;
  y: number;
  rot: number;
  flip: boolean;
  dur: number;
  ease: string;
  shown: boolean;
}

const HIDDEN: Pose = { x: -300, y: -300, rot: 0, flip: false, dur: 0, ease: EASE, shown: false };

/**
 * Maruti living on every tab except his own: peeking over the nav bar and from under the header, hanging from the
 * top edge, flying across, climbing the side edges, strolling along the nav, napping when you are away.
 * He sits BELOW the header and nav (z-39), so he really does appear from behind them.
 */
export const MarutiRoamer: React.FC = () => {
  const { activeTab } = useApp();
  const brain = useMaruti();
  const brainRef = useRef(brain);
  brainRef.current = brain;
  const onCompanion = activeTab === 'companion';

  const [pose, setPose] = useState<Pose>(HIDDEN);
  const timers = useRef<number[]>([]);
  const scene = useRef<string | null>(null);
  const sceneMood = useRef<MarutiMood>('peek');
  const lastScene = useRef('');

  const api = useMemo(() => {
    const go = (p: Partial<Pose>) => setPose((prev) => ({ ...prev, ...p }));
    const later = (fn: () => void, ms: number) => {
      timers.current.push(window.setTimeout(fn, ms));
    };
    const clearAll = () => {
      timers.current.forEach((t) => window.clearTimeout(t));
      timers.current = [];
    };
    const geo = () => {
      const nav = document.querySelector('nav.fixed');
      const hdr = document.querySelector('header');
      return {
        W: window.innerWidth,
        navTop: nav ? nav.getBoundingClientRect().top : window.innerHeight - 64,
        hdrB: hdr ? hdr.getBoundingClientRect().bottom : 64,
      };
    };
    const setMood = (m: MarutiMood) => {
      sceneMood.current = m;
      brainRef.current.act(m, 0);
    };
    const sayIn = (text: string) =>
      brainRef.current.say(text, { mood: sceneMood.current, keep: true, speak: false, hold: 3000 });
    const start = (name: string, m: MarutiMood) => {
      clearAll();
      scene.current = name;
      lastScene.current = name;
      setMood(m);
    };
    const hide = () => {
      clearAll();
      scene.current = null;
      go({ shown: false, x: -300, y: -300, rot: 0, dur: 0 });
    };
    const finish = () => {
      hide();
      brainRef.current.act('idle', 0);
    };

    /** Half a face over the nav bar. cx = where to appear (e.g. above the tab you just tapped). */
    const peekBottom = (cx?: number, line?: string) => {
      const { W, navTop } = geo();
      const x = clamp((cx ?? rand(40, W - 40)) - SIZE / 2, 6, W - SIZE - 6);
      start('peekBottom', 'peek');
      go({ x, y: navTop + 6, rot: 0, flip: x > W / 2, dur: 0, shown: true });
      later(() => go({ y: navTop - H * 0.55, dur: 650, ease: POP }), 60);
      const text = line ?? (Math.random() < 0.7 ? pick(PEEK_LINES) : undefined);
      if (text) later(() => sayIn(text), 750);
      later(() => go({ y: navTop + 6, dur: 450, ease: EASE }), 4200);
      later(finish, 4800);
    };

    /** Hanging upside-down from under the header, face first. */
    const peekTop = () => {
      const { W, hdrB } = geo();
      const x = rand(30, Math.max(31, W - SIZE - 30));
      start('peekTop', 'peek');
      go({ x, y: hdrB - H - 4, rot: 180, flip: false, dur: 0, shown: true });
      later(() => go({ y: hdrB - H * 0.5, dur: 700, ease: POP }), 60);
      later(() => sayIn(pick(PEEK_LINES)), 800);
      later(() => go({ y: hdrB - H - 4, dur: 480, ease: EASE }), 4000);
      later(finish, 4600);
    };

    /** Half a face from the left or right edge. */
    const peekSide = () => {
      const { W, navTop, hdrB } = geo();
      const right = Math.random() < 0.5;
      const y = rand(hdrB + 30, Math.max(hdrB + 60, navTop - H - 30));
      const outX = right ? W + 6 : -SIZE - 6;
      const inX = right ? W - SIZE * 0.55 : -SIZE * 0.45;
      start('peekSide', 'peek');
      go({ x: outX, y, rot: 0, flip: right, dur: 0, shown: true });
      later(() => go({ x: inX, rot: right ? -10 : 10, dur: 700, ease: POP }), 60);
      later(() => sayIn(pick(SIDE_LINES)), 800);
      later(() => go({ x: outX, rot: 0, dur: 500, ease: EASE }), 4000);
      later(finish, 4600);
    };

    /** Across the screen on his cloud, with a swoop in the middle. */
    const fly = () => {
      const { W, navTop, hdrB } = geo();
      const dir = Math.random() < 0.5 ? 1 : -1;
      const startX = dir > 0 ? -SIZE - 10 : W + 10;
      const endX = dir > 0 ? W + 10 : -SIZE - 10;
      const y1 = rand(hdrB + 30, Math.max(hdrB + 60, navTop * 0.5));
      const y2 = clamp(y1 + rand(-70, 90), hdrB + 20, Math.max(hdrB + 40, navTop - H - 30));
      const lean = dir > 0 ? 6 : -6;
      start('fly', 'fly');
      go({ x: startX, y: y1, rot: lean, flip: dir < 0, dur: 0, shown: true });
      later(() => go({ x: W * rand(0.35, 0.65), y: y2, dur: 2500, ease: EASE }), 60);
      if (Math.random() < 0.6) later(() => sayIn(pick(FLY_LINES)), 1300);
      later(() => go({ x: endX, y: y1 + rand(-40, 40), dur: 2500, ease: EASE }), 2650);
      later(finish, 5300);
    };

    /** Up the side edge, a rest on the way, then off the top behind the header. */
    const climb = () => {
      const { W, navTop, hdrB } = geo();
      const right = Math.random() < 0.5;
      const inX = right ? W - SIZE * 0.55 : -SIZE * 0.45;
      const rot = right ? -8 : 8;
      const startY = navTop + 6;
      const targetY = rand(hdrB + 50, Math.max(hdrB + 90, navTop * 0.6));
      const exitY = hdrB - H - 6;
      const up = clamp((startY - targetY) * 9, 1800, 4000);
      const out = clamp((targetY - exitY) * 9, 1500, 3500);
      start('climb', 'climb');
      go({ x: inX, y: startY, rot, flip: right, dur: 0, shown: true });
      later(() => go({ y: targetY, dur: up, ease: 'ease-in-out' }), 60);
      later(() => {
        setMood('hang');
        sayIn(pick(CLIMB_LINES));
      }, up + 150);
      later(() => {
        setMood('climb');
        go({ y: exitY, dur: out, ease: 'ease-in-out' });
      }, up + 150 + 2800);
      later(finish, up + 150 + 2800 + out + 150);
    };

    /** Strolls in along the top of the nav bar, stops to chat, strolls out. */
    const walkNav = () => {
      const { W, navTop } = geo();
      const dir = Math.random() < 0.5 ? 1 : -1;
      const y = navTop - H + 8;
      const startX = dir > 0 ? -SIZE - 10 : W + 10;
      const endX = dir > 0 ? W + 10 : -SIZE - 10;
      const midX = rand(W * 0.25, Math.max(W * 0.26, W * 0.65));
      start('walkNav', 'walk');
      go({ x: startX, y, rot: 0, flip: dir < 0, dur: 0, shown: true });
      later(() => go({ x: midX, dur: 2400, ease: 'ease-out' }), 60);
      later(() => {
        setMood('wave');
        sayIn(pick(WALK_LINES));
      }, 2600);
      later(() => {
        setMood('walk');
        go({ x: endX, dur: 2400, ease: 'ease-in' });
      }, 4700);
      later(finish, 7200);
    };

    /** He fell asleep (no touch for a while): curl up on the nav bar until you come back. */
    const nap = () => {
      const { W, navTop } = geo();
      clearAll();
      scene.current = null;
      go({ x: rand(24, Math.max(25, W - SIZE - 24)), y: navTop + 6, rot: 0, flip: false, dur: 0, shown: true });
      later(() => go({ y: navTop - H + 8, dur: 700, ease: POP }), 60);
    };

    const wakeHide = () => {
      const { navTop } = geo();
      clearAll();
      later(() => go({ y: navTop + 6, dur: 500, ease: EASE }), 3500);
      later(() => go({ shown: false, x: -300, y: -300, dur: 0 }), 4100);
    };

    const cancel = () => {
      if (scene.current) finish();
      else hide();
    };

    const random = () => {
      const pool: [string, number, () => void][] = [
        ['peekBottom', 26, () => peekBottom()],
        ['peekSide', 22, peekSide],
        ['peekTop', 12, peekTop],
        ['fly', 14, fly],
        ['climb', 14, climb],
        ['walkNav', 16, walkNav],
      ];
      const options = pool.filter((p) => p[0] !== lastScene.current);
      let r = Math.random() * options.reduce((s, p) => s + p[1], 0);
      for (const [, w, run] of options) {
        r -= w;
        if (r <= 0) {
          run();
          return;
        }
      }
      options[0][2]();
    };

    return { peekBottom, nap, wakeHide, cancel, random, clearAll };
  }, []);

  // Tab switch: hide on his own tab, otherwise pop up above the tab you just tapped.
  const prevTab = useRef(activeTab);
  useEffect(() => {
    if (prevTab.current === activeTab) return;
    prevTab.current = activeTab;
    if (onCompanion) {
      api.cancel();
      return;
    }
    const b = brainRef.current;
    if (b.calm || b.quiet || prefersReducedMotion()) return;
    const btn = document.querySelectorAll('nav.fixed button')[TABS.indexOf(activeTab)];
    const rect = btn ? btn.getBoundingClientRect() : null;
    const lines = TAB_LINES[activeTab as keyof typeof TAB_LINES];
    api.peekBottom(rect ? rect.left + rect.width / 2 : undefined, lines ? pick(lines) : undefined);
  }, [activeTab, onCompanion, api]);

  // Random life while he is outside his own tab.
  useEffect(() => {
    if (onCompanion) return;
    let id: number;
    const tick = () => {
      id = window.setTimeout(() => {
        const b = brainRef.current;
        if (document.visibilityState === 'visible' && !b.calm && !b.quiet && !prefersReducedMotion() && !scene.current && b.mood === 'idle') {
          api.random();
        }
        tick();
      }, rand(7000, 13000));
    };
    tick();
    return () => window.clearTimeout(id);
  }, [onCompanion, api]);

  // Asleep on the nav bar while you are away; hides again when you wake him.
  const prevMood = useRef(brain.mood);
  useEffect(() => {
    const was = prevMood.current;
    prevMood.current = brain.mood;
    if (onCompanion || scene.current) return;
    if (brain.mood === 'sleep') api.nap();
    else if (was === 'sleep') api.wakeHide();
  }, [brain.mood, onCompanion, api]);

  useEffect(() => () => api.clearAll(), [api]);

  if (onCompanion) return null;

  const tap = () => {
    const b = brainRef.current;
    if (scene.current) b.say(pick(POKES), { mood: sceneMood.current, keep: true, speak: false, hold: 2500 });
    else b.poke();
  };

  const tr = pose.dur ? `transform ${pose.dur}ms ${pose.ease}` : 'none';
  const above = pose.y > 96;
  const bubbleLeft = clamp(pose.x + SIZE / 2 - 100, 8, Math.max(8, window.innerWidth - 208));
  const bubbleTop = above ? pose.y - 6 : pose.y + H + 6;

  return (
    <div className="fixed inset-0 z-[39] pointer-events-none overflow-hidden">
      <div
        style={{
          position: 'absolute', left: 0, top: 0, width: SIZE, height: H,
          transform: `translate3d(${pose.x}px, ${pose.y}px, 0)`,
          transition: tr, visibility: pose.shown ? 'visible' : 'hidden', willChange: 'transform',
        }}
      >
        <div
          className="pointer-events-auto"
          style={{ width: '100%', height: '100%', transform: `rotate(${pose.rot}deg)`, transition: tr }}
        >
          <MarutiSprite mood={brain.mood} flip={pose.flip} onTap={tap} />
        </div>
      </div>
      {pose.shown && brain.bubble && (
        <div
          role="status"
          aria-live="polite"
          className="absolute left-0 top-0 bg-surface text-ink border border-line rounded-2xl px-3 py-2 font-small text-small shadow-sm"
          style={{
            width: 'max-content', maxWidth: 200,
            transform: `translate3d(${bubbleLeft}px, ${bubbleTop}px, 0)${above ? ' translateY(-100%)' : ''}`,
            transition: tr,
          }}
        >
          {brain.bubble}
        </div>
      )}
    </div>
  );
};
