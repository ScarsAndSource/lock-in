import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useApp } from '../../context/AppContext';
import type { Tab } from '../../context/AppContext';
import { useMaruti } from './MarutiContext';
import { MarutiSprite } from './MarutiSprite';
import { shownMood } from './useMarutiBrain';
import type { MarutiMood } from './useMarutiBrain';
import { CLIMB_LINES, FLY_LINES, PEEK_LINES, POKES, SIDE_LINES, TAB_LINES, WALK_LINES, pick } from './lines';
import { GUARD_LINES, SELF_LAUGH } from './banter';

const SIZE = 64;
const H = Math.round((SIZE * 227) / 177);
const GUARD_SCALE = 1.7;
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
  scale: number;
  flip: boolean;
  dur: number;
  ease: string;
  shown: boolean;
}

const HIDDEN: Pose = { x: -300, y: -300, rot: 0, scale: 1, flip: false, dur: 0, ease: EASE, shown: false };

/**
 * Maruti outside his page: flying across the whole screen (from his own tab too), peeking over the nav and from under
 * the header, climbing the edges, rolling with laughter, leaning in on your input box while you type, and standing
 * guard, larger, when you are sad. He sits BELOW the header and nav (z-39), so he really does appear from behind them.
 */
export const MarutiRoamer: React.FC = () => {
  const { activeTab } = useApp();
  const brain = useMaruti();
  const brainRef = useRef(brain);
  brainRef.current = brain;
  const onCompanion = activeTab === 'companion';

  const [pose, setPose] = useState<Pose>(HIDDEN);
  const poseRef = useRef(pose);
  poseRef.current = pose;
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
    /** Where his in-page sprite (hero or strip) is, so he can lift off from it and land back on it. */
    const homePose = () => {
      const el = document.querySelector('[data-maruti-home]');
      if (!el) return null;
      const r = el.getBoundingClientRect();
      if (r.width < 8) return null;
      return { x: r.left + r.width / 2 - SIZE / 2, y: r.bottom - H, scale: clamp(r.width / SIZE, 0.6, 2.4) };
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
      brainRef.current.setAway(false);
      setMood(m);
    };
    /** Gone: hidden, and the in-page sprite is him again. Leaves his mood alone. */
    const hide = () => {
      clearAll();
      scene.current = null;
      brainRef.current.setAway(false);
      go({ shown: false, x: -300, y: -300, rot: 0, scale: 1, dur: 0 });
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
      go({ x, y: navTop + 6, rot: 0, scale: 1, flip: x > W / 2, dur: 0, shown: true });
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
      go({ x, y: hdrB - H - 4, rot: 180, scale: 1, flip: false, dur: 0, shown: true });
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
      go({ x: outX, y, rot: 0, scale: 1, flip: right, dur: 0, shown: true });
      later(() => go({ x: inX, rot: right ? -10 : 10, dur: 700, ease: POP }), 60);
      later(() => sayIn(pick(SIDE_LINES)), 800);
      later(() => go({ x: outX, rot: 0, dur: 500, ease: EASE }), 4000);
      later(finish, 4600);
    };

    /**
     * A real flight over the whole screen, with a swoop and sometimes a loop-the-loop.
     * fromHome: lift off from his in-page sprite and land back on it (his own tab). Otherwise edge to edge.
     */
    const flyTour = (fromHome: boolean) => {
      const { W, navTop, hdrB } = geo();
      const home = fromHome ? homePose() : null;
      if (fromHome && !home) return;
      const minY = hdrB + 20;
      const maxY = Math.max(minY + 40, navTop - H - 20);
      const pt = () => ({ x: rand(8, Math.max(9, W - SIZE - 8)), y: rand(minY, maxY) });
      const lean = (dx: number) => clamp(dx / 40, -10, 10);

      start('fly', 'fly');
      let cur: { x: number; y: number };
      if (home) {
        brainRef.current.setAway(true);
        cur = { x: home.x, y: home.y };
        go({ x: home.x, y: home.y, scale: home.scale, rot: 0, flip: false, dur: 0, shown: true });
      } else {
        const dir = Math.random() < 0.5 ? 1 : -1;
        cur = { x: dir > 0 ? -SIZE - 10 : W + 10, y: rand(minY, maxY) };
        go({ x: cur.x, y: cur.y, scale: 1, rot: 0, flip: dir < 0, dur: 0, shown: true });
      }

      const a = pt();
      const c = pt();
      let t = 60;
      const leg = (to: { x: number; y: number }, loop: boolean) => {
        const dx = to.x - cur.x;
        const ms = clamp(Math.hypot(dx, to.y - cur.y) * 3.2, 1100, 2300);
        const l = lean(dx);
        const from = cur;
        later(() => go({ x: to.x, y: to.y, scale: 1, rot: l, flip: to.x < from.x, dur: ms, ease: EASE }), t);
        t += ms + 30;
        if (loop) {
          later(() => go({ rot: l + 360, dur: 800, ease: 'ease-in-out' }), t);
          t += 830;
          later(() => go({ rot: l, dur: 0 }), t); // 360 degrees later it looks identical, so reset without animating
          t += 40;
        }
        cur = to;
      };
      leg(a, false);
      leg(c, Math.random() < 0.4);
      if (Math.random() < 0.6) later(() => sayIn(pick(FLY_LINES)), 1300);

      if (home) {
        const ms = 1300;
        later(() => {
          const h = homePose() ?? home;
          go({ x: h.x, y: h.y, scale: h.scale, rot: 0, flip: false, dur: ms, ease: EASE });
        }, t);
        later(finish, t + ms + 120);
      } else {
        const ms = 1500;
        const exitX = c.x > W / 2 ? W + 10 : -SIZE - 10;
        later(() => go({ x: exitX, y: c.y + rand(-40, 40), rot: 0, flip: exitX < c.x, dur: ms, ease: EASE }), t);
        later(finish, t + ms + 120);
      }
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
      go({ x: inX, y: startY, rot, scale: 1, flip: right, dur: 0, shown: true });
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
      go({ x: startX, y, rot: 0, scale: 1, flip: dir < 0, dur: 0, shown: true });
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

    /** Rolls along the nav bar laughing his head off, then slips back behind it. */
    const rollNav = () => {
      const { W, navTop } = geo();
      const dir = Math.random() < 0.5 ? 1 : -1;
      const y = navTop - H + 8;
      const inX = dir > 0 ? 12 : W - SIZE - 12;
      const toX = dir > 0 ? W - SIZE - 12 : 12;
      start('rollNav', 'laugh');
      go({ x: dir > 0 ? -SIZE - 10 : W + 10, y, rot: 0, scale: 1, flip: dir < 0, dur: 0, shown: true });
      later(() => go({ x: inX, dur: 900, ease: EASE }), 60);
      later(() => {
        sayIn(pick(SELF_LAUGH));
        go({ x: toX, rot: dir * 720, dur: 2400, ease: 'ease-in-out' });
      }, 1000);
      later(() => go({ rot: 0, dur: 0 }), 3500); // two full turns later it looks identical
      later(() => go({ y: navTop + 6, dur: 500, ease: EASE }), 4300);
      later(finish, 4900);
    };

    /** He fell asleep (no touch for a while): curl up on the nav bar until you come back. */
    const nap = () => {
      const { W, navTop } = geo();
      clearAll();
      scene.current = null;
      go({ x: rand(24, Math.max(25, W - SIZE - 24)), y: navTop + 6, rot: 0, scale: 1, flip: false, dur: 0, shown: true });
      later(() => go({ y: navTop - H + 8, dur: 700, ease: POP }), 60);
    };

    const wakeHide = () => {
      const { navTop } = geo();
      clearAll();
      later(() => go({ y: navTop + 6, dur: 500, ease: EASE }), 3500);
      later(() => go({ shown: false, x: -300, y: -300, dur: 0 }), 4100);
    };

    /** You are typing on his tab: he flies over to lean in on the input box, hand cupped to his ear. */
    const eavesStart = () => {
      const input = document.querySelector('main form input[type="text"]');
      if (!input) return;
      const r = input.getBoundingClientRect();
      const { W } = geo();
      const tx = clamp(r.right - SIZE - 18, 6, W - SIZE - 6);
      const ty = r.top - H + 12;
      const target = { x: tx, y: ty, scale: 1, rot: -10, flip: false };
      if (scene.current === 'eaves') {
        clearAll();
        go({ ...target, dur: 700, ease: EASE, shown: true });
        return;
      }
      const wasShown = poseRef.current.shown;
      clearAll();
      scene.current = 'eaves';
      const b = brainRef.current;
      if (['fly', 'walk', 'peek', 'climb', 'hang', 'wave', 'laugh', 'rofl'].includes(b.mood)) b.act('idle', 0);
      b.setAway(true);
      if (!wasShown) {
        const h = homePose();
        if (h) go({ x: h.x, y: h.y, scale: h.scale, rot: 0, flip: false, dur: 0, shown: true });
        else go({ x: tx, y: ty + 90, scale: 1, rot: 0, flip: false, dur: 0, shown: true });
      }
      later(() => go({ ...target, dur: 900, ease: POP, shown: true }), 60);
    };

    const eavesStop = () => {
      if (scene.current !== 'eaves') return;
      clearAll();
      const h = homePose();
      if (!h) {
        hide();
        return;
      }
      go({ x: h.x, y: h.y, scale: h.scale, rot: 0, flip: false, dur: 800, ease: EASE });
      later(hide, 900);
    };

    /** You are sad: he grows and stands guard, bottom-left, steady, with you. */
    const guard = (onHomeTab: boolean) => {
      const place = (dur: number) => {
        const { navTop } = geo();
        const form = onHomeTab ? document.querySelector('main form') : null;
        const base = (form ? form.getBoundingClientRect().top : navTop) + 6;
        go({
          x: 8 + (SIZE * GUARD_SCALE) / 2 - SIZE / 2, y: base - H, scale: GUARD_SCALE,
          rot: 0, flip: false, dur, ease: EASE, shown: true,
        });
      };
      if (scene.current === 'guard') {
        clearAll();
        place(700);
        later(() => place(600), 1500); // once the new tab's input box exists
        return;
      }
      const wasShown = poseRef.current.shown;
      clearAll();
      scene.current = 'guard';
      lastScene.current = 'guard';
      brainRef.current.setAway(true);
      if (!wasShown) {
        const h = onHomeTab ? homePose() : null;
        if (h) go({ x: h.x, y: h.y, scale: h.scale, rot: 0, flip: false, dur: 0, shown: true });
        else go({ x: 8 + (SIZE * GUARD_SCALE) / 2 - SIZE / 2, y: geo().navTop + 6, scale: 1, rot: 0, flip: false, dur: 0, shown: true });
      }
      later(() => place(1100), 60);
      later(() => place(600), 2500);
    };

    const unguard = (onHomeTab: boolean) => {
      if (scene.current !== 'guard') return;
      clearAll();
      const h = onHomeTab ? homePose() : null;
      if (h) {
        go({ x: h.x, y: h.y, scale: h.scale, rot: 0, dur: 900, ease: EASE });
        later(hide, 1000);
      } else {
        go({ y: geo().navTop + 6, scale: 1, dur: 600, ease: EASE });
        later(hide, 700);
      }
    };

    const cancel = () => {
      if (scene.current === 'eaves') {
        eavesStop();
        return;
      }
      if (scene.current) finish();
      else hide();
    };

    const pickScene = (pool: [string, number, () => void][]) => {
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
    /** Other tabs: the full repertoire. */
    const random = () =>
      pickScene([
        ['peekBottom', 22, () => peekBottom()],
        ['peekSide', 18, peekSide],
        ['peekTop', 10, peekTop],
        ['fly', 16, () => flyTour(false)],
        ['climb', 12, climb],
        ['walkNav', 12, walkNav],
        ['rollNav', 10, rollNav],
      ]);
    /** His own tab: he lifts off from the hero and tours the screen. */
    const randomHome = () => flyTour(true);

    return {
      peekBottom, nap, wakeHide, eavesStart, eavesStop, guard, unguard, cancel, random, randomHome, clearAll, hide,
    };
  }, []);

  // Tab switch: pop up above the tab you just tapped (his guard post and input-box lean follow you separately).
  const prevTab = useRef(activeTab);
  useEffect(() => {
    if (prevTab.current === activeTab) return;
    prevTab.current = activeTab;
    if (scene.current === 'guard') return;
    api.cancel();
    if (onCompanion) return;
    const b = brainRef.current;
    if (b.calm || b.quiet || b.comfort || prefersReducedMotion()) return;
    const btn = document.querySelectorAll('nav.fixed button')[TABS.indexOf(activeTab)];
    const rect = btn ? btn.getBoundingClientRect() : null;
    const lines = TAB_LINES[activeTab as keyof typeof TAB_LINES];
    api.peekBottom(rect ? rect.left + rect.width / 2 : undefined, lines ? pick(lines) : undefined);
  }, [activeTab, onCompanion, api]);

  // You are sad: he stands guard with you, larger. Back to normal size when it passes or you send him away.
  useEffect(() => {
    if (brain.comfort) api.guard(onCompanion);
    else api.unguard(onCompanion);
  }, [brain.comfort, onCompanion, api]);

  // You are typing on his tab: he leans in on the input box.
  useEffect(() => {
    if (brain.eavesdrop && onCompanion) api.eavesStart();
    else api.eavesStop();
  }, [brain.eavesdrop, onCompanion, api]);

  // Random life: tours of the screen from his own tab, the full repertoire on the others.
  useEffect(() => {
    let id: number;
    const tick = () => {
      id = window.setTimeout(
        () => {
          const b = brainRef.current;
          if (
            document.visibilityState === 'visible' && !b.calm && !b.quiet && !b.comfort && !b.eavesdrop &&
            !prefersReducedMotion() && !scene.current && b.mood === 'idle'
          ) {
            if (onCompanion) api.randomHome();
            else api.random();
          }
          tick();
        },
        onCompanion ? rand(14000, 24000) : rand(7000, 13000),
      );
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

  const guarding = brain.comfort && pose.shown;

  const tap = () => {
    const b = brainRef.current;
    if (scene.current === 'guard') b.say(pick(GUARD_LINES, b.bubble), { speak: false, hold: 4000 });
    else if (scene.current === 'eaves') b.say(pick(POKES), { speak: false, hold: 2500 });
    else if (scene.current) b.say(pick(POKES), { mood: sceneMood.current, keep: true, speak: false, hold: 2500 });
    else b.poke();
  };

  // What he shows: the leaning-in pose while he listens at your input, otherwise whatever his mood is.
  const base = shownMood(brain);
  const spriteMood: MarutiMood =
    brain.away && brain.eavesdrop && base !== 'thinking' && base !== 'talking' ? 'eavesdrop' : base;

  const tr = pose.dur ? `transform ${pose.dur}ms ${pose.ease}` : 'none';
  const topEdge = pose.y + H - H * pose.scale;
  const above = topEdge > 96;
  const bubbleLeft = clamp(pose.x + SIZE / 2 - 100, 8, Math.max(8, window.innerWidth - 208));
  const bubbleTop = above ? topEdge - 6 : pose.y + H + 6;

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
          style={{ width: '100%', height: '100%', transform: `scale(${pose.scale})`, transformOrigin: '50% 100%', transition: tr }}
        >
          <div
            className="pointer-events-auto"
            style={{ width: '100%', height: '100%', transform: `rotate(${pose.rot}deg)`, transition: tr }}
          >
            <MarutiSprite mood={spriteMood} flip={pose.flip} onTap={tap} />
          </div>
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
      {guarding && (
        <button
          type="button"
          aria-label="Let Maruti step back"
          onClick={() => brain.setComfort(false)}
          className="pointer-events-auto absolute left-0 top-0 w-7 h-7 rounded-full bg-surface border border-line text-ink flex items-center justify-center shadow-sm"
          style={{
            transform: `translate3d(${pose.x + SIZE / 2 + (SIZE * pose.scale) / 2 - 18}px, ${topEdge + 2}px, 0)`,
            transition: tr,
          }}
        >
          <span className="material-symbols-outlined text-[16px]">close</span>
        </button>
      )}
    </div>
  );
};
