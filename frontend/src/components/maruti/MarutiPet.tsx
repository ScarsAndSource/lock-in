import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useApp } from '../../context/AppContext';
import { BUDDY_NAME } from '../Buddy';
import { useMaruti } from './MarutiContext';
import { MarutiSprite } from './MarutiSprite';
import { shownMood } from './useMarutiBrain';
import type { MarutiBrain } from './useMarutiBrain';
import { POSES, poseSrc } from './poses';
import type { PoseName } from './poses';
import { GUARD_LINES } from './banter';
import { TAB_LINES, pick } from './lines';
import { prefersReducedMotion, usePrefersReducedMotion } from './motion';
import {
  ACTIVITIES, DO_EVENT, EASE, GRIP, GUARD_SCALE, H, HOME_X, IDLE_HOME, SIZE, VINE_SCALE, WEIGHTS,
  clamp, homePlace, lay, pose as poseVis,
} from './activities';
import type { ActivityName, Builder, ChipRun, Geo, Place, Script, Vis } from './activities';

interface Actor extends Place {
  dur: number;
  ease: string;
  vis: Vis;
  om: boolean;
  shown: boolean;
}
interface VineState {
  id: number;
  x: number;
  top: number;
  len: number;
}
interface SaplingState {
  x: number;
  y: number;
  g: number;
}

const START: Actor = { x: HOME_X, y: 0, rot: 0, scale: 1, flip: false, dur: 0, ease: EASE, vis: IDLE_HOME, om: false, shown: false };
const PLACE_KEYS: (keyof Place)[] = ['x', 'y', 'rot', 'scale', 'flip'];

/** His garden and the vine swing carry on between visits. */
let plantGrowth = 0;
let vineRuns = 0;

/** He is busy with the chat, asleep, being comforted, or you asked for stillness: no activities. */
const blocked = (b: MarutiBrain): boolean =>
  b.mood !== 'idle' || b.calm || b.quiet || b.comfort || prefersReducedMotion();

/** The screen right now. His feet stand on the nav bar, or on top of the chat input when you are talking to him. */
const geo = (): Geo => {
  const nav = document.querySelector('[data-maruti-nav]');
  const hdr = document.querySelector('header');
  const gnd = document.querySelector('[data-maruti-ground]');
  const W = window.innerWidth;
  const navTop = nav ? nav.getBoundingClientRect().top : window.innerHeight - 64;
  const hdrB = hdr ? hdr.getBoundingClientRect().bottom : 64;
  const raw = gnd ? Math.min(navTop, gnd.getBoundingClientRect().top + 6) : navTop;
  return { W, navTop, hdrB, ground: Math.max(raw, hdrB + H + 40) };
};

/** Where he rests when no activity is running: home, standing guard, or leaning in on your input box. */
const restPlace = (b: MarutiBrain, onChat: boolean): Place => {
  const g = geo();
  if (b.comfort) return { ...homePlace(g), x: HOME_X + (SIZE * (GUARD_SCALE - 1)) / 2, scale: GUARD_SCALE };
  if (b.eavesdrop && onChat) {
    const input = document.querySelector('[data-maruti-input]');
    if (input) {
      const r = input.getBoundingClientRect();
      return { x: clamp(r.right - SIZE - 18, 6, g.W - SIZE - 6), y: r.top - H + 12, rot: -10, scale: 1, flip: false };
    }
  }
  return homePlace(g);
};

/**
 * Maruti lives on the screen itself: no stage, no backdrop, just him. He walks along the nav bar (or your chat input),
 * flies across the whole app, climbs the screen edges, swings on a vine from under the header, prays, meditates, waters
 * a sapling, lifts a mountain, peeks from behind the bars and more. Anything the chat needs (he talks, thinks, laughs,
 * you type, he sleeps, you are sad) cancels what he is doing and he comes straight back, so chat reactions always win.
 */
export const MarutiPet: React.FC = () => {
  const { activeTab } = useApp();
  const brain = useMaruti();
  const brainRef = useRef(brain);
  brainRef.current = brain;
  const tabRef = useRef(activeTab);
  tabRef.current = activeTab;
  const reduced = usePrefersReducedMotion();

  const [actor, setActor] = useState<Actor>(START);
  const [vine, setVine] = useState<VineState | null>(null);
  const [sapling, setSapling] = useState<SaplingState | null>(null);
  const [vw, setVw] = useState<number>(() => window.innerWidth);

  const cur = useRef<Place>(START);
  const busy = useRef<string | null>(null);
  const lastAct = useRef('');
  const timers = useRef<number[]>([]);
  const pokes = useRef({ count: 0, last: 0 });
  const placed = useRef(false);

  const canMove = !brain.calm && !brain.quiet && !brain.comfort && !reduced;
  const moodBusy = brain.mood !== 'idle';

  /** Merge into his state. Does nothing (no re-render) when nothing actually changes. */
  const patch = useCallback((p: Partial<Actor>) => {
    for (const k of PLACE_KEYS) {
      const v = p[k];
      if (v !== undefined) (cur.current as unknown as Record<string, number | boolean>)[k] = v;
    }
    setActor((a) => {
      for (const k of Object.keys(p) as (keyof Actor)[]) if (a[k] !== p[k]) return { ...a, ...p };
      return a;
    });
  }, []);

  const clearTimers = useCallback(() => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  }, []);

  /** Go to where he should be right now. animate=false jumps there. */
  const rest = useCallback(
    (animate: boolean) => {
      const p = restPlace(brainRef.current, tabRef.current === 'companion');
      const c = cur.current;
      const dist = Math.hypot(p.x - c.x, p.y - c.y);
      const ms = animate && placed.current && dist > 1 ? clamp(dist * 1.6, 450, 1500) : 0;
      placed.current = true;
      patch({ ...p, dur: ms, ease: EASE, vis: IDLE_HOME, om: false, shown: true });
    },
    [patch],
  );

  /** Drop whatever he is doing and come back. */
  const restNow = useCallback(
    (animate = true) => {
      clearTimers();
      busy.current = null;
      setVine(null);
      setSapling(null);
      rest(animate);
    },
    [clearTimers, rest],
  );

  const play = useCallback(
    (name: string, script: Script) => {
      clearTimers();
      busy.current = name;
      lastAct.current = name;
      const g = geo();
      const home = homePlace(g);
      const steps: [number, () => void][] = [];
      let t = 0;
      let px = cur.current.x;
      let py = cur.current.y;
      let pf = cur.current.flip;
      const at = (fn: () => void) => {
        steps.push([t, fn]);
      };
      const track = (p: Partial<Place>) => {
        if (p.x !== undefined) px = p.x;
        if (p.y !== undefined) py = p.y;
        if (p.flip !== undefined) pf = p.flip;
      };
      const face = (x: number): boolean => {
        if (x < px - 0.5) pf = true;
        else if (x > px + 0.5) pf = false;
        return pf;
      };

      const b: Builder = {
        g,
        say: (text) => at(() => brainRef.current.say(text, { mood: 'idle', speak: false, hold: 3600 })),
        wait: (ms) => {
          t += ms;
        },
        jump: (place, vis) => {
          at(() => patch({ ...place, dur: 0, shown: true, om: false, ...(vis ? { vis } : {}) }));
          track(place);
        },
        to: (place, ms, ease = EASE, vis) => {
          at(() => patch({ ...place, dur: ms, ease, ...(vis ? { vis } : {}) }));
          t += ms;
          track(place);
        },
        walk: (x, free = false) => {
          const nx = free ? x : clamp(x, 6, g.W - SIZE - 6);
          const y = home.y;
          const dist = Math.abs(nx - px) + Math.abs(y - py);
          const flip = face(nx);
          if (dist < 2) {
            at(() => patch({ x: nx, y, scale: 1, rot: 0, flip, vis: lay('idle', false) }));
            px = nx;
            py = y;
            return nx;
          }
          const ms = clamp(dist / 0.09, 500, 5000);
          at(() => patch({ x: nx, y, scale: 1, rot: 0, flip, dur: ms, ease: 'linear', vis: lay('walk', false) }));
          t += ms;
          at(() => patch({ vis: lay('idle', false) }));
          px = nx;
          py = y;
          return nx;
        },
        fly: (x, y, p: PoseName = 'fly-small', scale = 0.8) => {
          const ms = clamp(Math.hypot(x - px, y - py) / 0.22, 700, 2600);
          const flip = face(x);
          at(() => patch({ x, y, scale, rot: flip ? -7 : 7, flip, dur: ms, ease: EASE, vis: poseVis(p) }));
          t += ms;
          px = x;
          py = y;
        },
        glide: (x, y, scale = 0.75) => {
          const ms = clamp(Math.hypot(x - px, y - py) / 0.2, 800, 2800);
          const flip = face(x);
          at(() => patch({ x, y, scale, rot: flip ? -4 : 4, flip, dur: ms, ease: EASE, vis: lay('fly', true) }));
          t += ms;
          px = x;
          py = y;
        },
        climb: (x, y, scale, rot, flip) => {
          const ms = clamp(Math.abs(y - py) * 9, 1200, 4200);
          pf = flip;
          at(() => patch({ x, y, scale, rot, flip, dur: ms, ease: 'ease-in-out', vis: lay('climb', false) }));
          t += ms;
          px = x;
          py = y;
        },
        look: (vis, ms, opts = {}) => {
          const flip = opts.flip ?? pf;
          pf = flip;
          at(() => patch({ vis, rot: opts.rot ?? 0, flip, om: opts.om ?? false }));
          t += ms;
          if (opts.om) at(() => patch({ om: false }));
        },
        vine: (on, x = 0, len = 0) =>
          at(() => {
            if (on) {
              vineRuns += 1;
              setVine({ id: vineRuns, x, top: g.hdrB, len });
              patch({ shown: false });
            } else {
              setVine(null);
              patch({ shown: true });
            }
          }),
        sapling: (x) => {
          if (x === null) {
            at(() => setSapling(null));
            return;
          }
          const prev = plantGrowth;
          plantGrowth = prev === 0 ? 0.35 : Math.min(1, prev + 0.2);
          const grown = plantGrowth;
          at(() => setSapling({ x, y: g.ground, g: Math.max(0.2, prev) }));
          steps.push([t + 500, () => setSapling((s) => (s ? { ...s, g: grown } : s))]);
        },
        home: () => {
          at(() => setSapling(null));
          if (Math.abs(py - home.y) > 6) b.glide(home.x, home.y, 1);
          else b.walk(home.x);
        },
        popHome: () => {
          b.jump({ x: home.x, y: g.navTop + 6, rot: 0, scale: 1, flip: false }, IDLE_HOME);
          b.wait(60);
          b.to({ y: home.y }, 600, 'cubic-bezier(.2,1.35,.4,1)');
        },
      };

      script(b);
      if (Math.abs(px - home.x) > 2 || Math.abs(py - home.y) > 2) b.home();

      for (const [ms, fn] of steps) timers.current.push(window.setTimeout(fn, ms));
      timers.current.push(
        window.setTimeout(() => {
          busy.current = null;
          setVine(null);
          setSapling(null);
          patch({ vis: IDLE_HOME, om: false, rot: 0, scale: 1, shown: true, dur: 300, ease: EASE });
        }, t + 50),
      );
    },
    [clearTimers, patch],
  );

  const start = useCallback(
    (what: ChipRun) => {
      if (blocked(brainRef.current)) return;
      const name: ActivityName = what === 'climb' ? (Math.random() < 0.5 ? 'climbR' : 'climbL') : what;
      play(name, ACTIVITIES[name]);
    },
    [play],
  );

  const randomActivity = useCallback(() => {
    const options = WEIGHTS.filter(([n]) => n !== lastAct.current);
    let r = Math.random() * options.reduce((s, o) => s + o[1], 0);
    let chosen = options[0][0];
    for (const [n, w] of options) {
      r -= w;
      if (r <= 0) {
        chosen = n;
        break;
      }
    }
    play(chosen, ACTIVITIES[chosen]);
  }, [play]);

  /** You tapped him: he does something. Poke him over and over and he finally breaks into laughter. */
  const poke = useCallback(() => {
    const b = brainRef.current;
    const now = Date.now();
    pokes.current.count = now - pokes.current.last < 4000 ? pokes.current.count + 1 : 1;
    pokes.current.last = now;
    if (blocked(b)) {
      b.poke();
      return;
    }
    if (pokes.current.count >= 5) {
      pokes.current.count = 0;
      b.poke();
      return;
    }
    randomActivity();
  }, [randomActivity]);

  // The chat (typing, thinking, laughing, sleep, comfort, calm mode) needs him: drop the script and come back.
  useEffect(() => {
    restNow(placed.current);
  }, [moodBusy, brain.comfort, brain.quiet, brain.eavesdrop, canMove, restNow]);

  // New tab: he settles at that tab's spot and says something about it.
  const prevTab = useRef(activeTab);
  useEffect(() => {
    if (prevTab.current === activeTab) return;
    prevTab.current = activeTab;
    restNow();
    const lines = activeTab === 'companion' ? undefined : TAB_LINES[activeTab];
    if (!lines || blocked(brainRef.current) || Math.random() > 0.7) return;
    timers.current.push(
      window.setTimeout(() => {
        if (!blocked(brainRef.current)) brainRef.current.say(pick(lines), { mood: 'idle', speak: false, hold: 3200 });
      }, 600),
    );
  }, [activeTab, restNow]);

  // The screen changed under him (rotated, keyboard, a tab finished loading): stand on the right spot again.
  useEffect(() => {
    let id = 0;
    const settle = () => {
      window.clearTimeout(id);
      id = window.setTimeout(() => {
        setVw(window.innerWidth);
        if (busy.current) restNow(false);
        else rest(true);
      }, 150);
    };
    window.addEventListener('resize', settle);
    const main = document.querySelector('main');
    const mo = main ? new MutationObserver(() => {
      window.clearTimeout(id);
      id = window.setTimeout(() => {
        if (!busy.current) rest(true);
      }, 150);
    }) : null;
    if (main && mo) mo.observe(main, { childList: true, subtree: true });
    return () => {
      window.clearTimeout(id);
      window.removeEventListener('resize', settle);
      mo?.disconnect();
    };
  }, [rest, restNow]);

  // Buttons elsewhere in the app can ask him to do something.
  useEffect(() => {
    const onAsk = (e: Event) => start((e as CustomEvent<ChipRun>).detail);
    window.addEventListener(DO_EVENT, onAsk);
    return () => window.removeEventListener(DO_EVENT, onAsk);
  }, [start]);

  // Left alone, he gets on with his day every so often.
  useEffect(() => {
    if (!canMove) return;
    let id = 0;
    const tick = () => {
      id = window.setTimeout(() => {
        if (document.visibilityState === 'visible' && !busy.current && !blocked(brainRef.current)) randomActivity();
        tick();
      }, 7000 + Math.random() * 5000);
    };
    tick();
    return () => window.clearTimeout(id);
  }, [canMove, randomActivity]);

  // Never leave a timer running behind a screen that is gone.
  useEffect(() => () => clearTimers(), [clearTimers]);

  // What he shows: chat reactions win (thinking, talking, sleeping, guarding); otherwise whatever his script says.
  const onChat = activeTab === 'companion';
  const base = shownMood(brain);
  const spriteMood = brain.eavesdrop && onChat && base !== 'thinking' && base !== 'talking' ? 'eavesdrop' : base;
  const forced = brain.mood !== 'idle' || brain.comfort || brain.quiet;
  const chatPose: PoseName | null =
    brain.comfort || brain.quiet ? null : brain.mood === 'thinking' ? 'scroll-write' : brain.mood === 'cheer' ? 'lift-mountain' : null;
  const vis: Vis = forced ? (chatPose ? poseVis(chatPose) : lay(spriteMood, true)) : actor.vis;
  const dropped = vis.kind === 'layered' && !vis.cloud;

  const tr = actor.dur ? `transform ${actor.dur}ms ${actor.ease}` : 'none';
  const topEdge = actor.y + H - H * actor.scale;
  const above = topEdge > 96;
  const bubbleLeft = clamp(actor.x + SIZE / 2 - 100, 8, Math.max(8, vw - 208));
  const bubbleTop = above ? topEdge - 6 : actor.y + H + 6;
  const guarding = brain.comfort && actor.shown;

  const tap = () => {
    const b = brainRef.current;
    if (b.comfort) b.say(pick(GUARD_LINES, b.bubble), { speak: false, hold: 4000 });
    else poke();
  };

  return (
    <div className="fixed inset-0 z-[39] pointer-events-none overflow-hidden">
      {sapling && (
        <svg
          viewBox="0 0 12 14"
          shapeRendering="crispEdges"
          aria-hidden="true"
          className="absolute pointer-events-none"
          style={{
            left: sapling.x, top: sapling.y, width: 26, aspectRatio: '12 / 14',
            transform: `translate(-50%, -100%) scale(${sapling.g})`, transformOrigin: '50% 100%', transition: 'transform 4500ms linear',
          }}
        >
          <rect x="2" y="12" width="8" height="2" fill="#6b4423" />
          <rect x="3" y="11" width="6" height="1" fill="#8a5a2b" />
          <rect x="5" y="5" width="2" height="7" fill="#3c8a38" />
          <rect x="2" y="3" width="3" height="2" fill="#5cb85c" />
          <rect x="1" y="4" width="2" height="1" fill="#2d6a2d" />
          <rect x="7" y="2" width="3" height="2" fill="#5cb85c" />
          <rect x="9" y="3" width="2" height="1" fill="#2d6a2d" />
          <rect x="4" y="1" width="4" height="2" fill="#7bd36b" />
        </svg>
      )}

      {vine && (
        <div key={vine.id} className="mv" aria-hidden="true" style={{ left: vine.x, top: vine.top - 2, height: vine.len + 2 }}>
          <div className="mv-line" />
          {[14, 34, 54, 74].map((p, i) => (
            <span key={p} className={`mv-leaf ${i % 2 ? 'mv-leaf-r' : 'mv-leaf-l'}`} style={{ top: `${p}%` }} />
          ))}
          <div className="mv-hand" style={{ width: SIZE * VINE_SCALE, height: H * VINE_SCALE, transform: `translate(-50%, -${GRIP * 100}%)` }}>
            <MarutiSprite mood="hang" ground />
          </div>
        </div>
      )}

      <div
        style={{
          position: 'absolute', left: 0, top: 0, width: SIZE, height: H,
          transform: `translate3d(${actor.x}px, ${actor.y}px, 0)`,
          transition: tr, visibility: actor.shown ? 'visible' : 'hidden', willChange: 'transform',
        }}
      >
        <div style={{ width: '100%', height: '100%', transform: `scale(${actor.scale})`, transformOrigin: '50% 100%', transition: tr }}>
          <div
            className="pointer-events-auto"
            style={{ position: 'relative', width: '100%', height: '100%', transform: `rotate(${actor.rot}deg)`, transition: tr }}
          >
            {vis.kind === 'layered' ? (
              <div style={{ width: '100%', height: '100%', transform: dropped ? 'translateY(8%)' : undefined }}>
                <MarutiSprite mood={vis.mood} flip={actor.flip} ground={!vis.cloud} onTap={tap} />
              </div>
            ) : (
              <button
                type="button"
                onClick={tap}
                aria-label={`${BUDDY_NAME}. Tap to say hi`}
                className="mp"
                style={{ position: 'absolute', left: '50%', bottom: 0, width: (POSES[vis.pose].w / 177) * SIZE, transform: 'translateX(-50%)' }}
              >
                <span className={`mp-flip ${actor.flip ? 'mp-flipped' : ''}`}>
                  <img
                    src={poseSrc(vis.pose)}
                    alt=""
                    draggable={false}
                    className={`mp-img mp-${vis.pose}`}
                    style={{ aspectRatio: `${POSES[vis.pose].w} / ${POSES[vis.pose].h}` }}
                  />
                </span>
                {vis.pose === 'water-sapling' && (
                  <>
                    <span className="mp-drop" style={{ left: '6%', top: '82%' }} />
                    <span className="mp-drop" style={{ left: '12%', top: '84%', animationDelay: '0.27s' }} />
                    <span className="mp-drop" style={{ left: '18%', top: '82%', animationDelay: '0.54s' }} />
                  </>
                )}
              </button>
            )}
            {actor.om && !forced && (
              <>
                <span className="mp-om" aria-hidden="true" style={{ left: '58%' }}>ॐ</span>
                <span className="mp-om" aria-hidden="true" style={{ left: '30%', animationDelay: '1.3s' }}>ॐ</span>
              </>
            )}
          </div>
        </div>
      </div>

      {brain.bubble && (
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
          aria-label={`Let ${BUDDY_NAME} step back`}
          onClick={() => brain.setComfort(false)}
          className="pointer-events-auto absolute left-0 top-0 w-7 h-7 rounded-full bg-surface border border-line text-ink flex items-center justify-center shadow-sm"
          style={{
            transform: `translate3d(${actor.x + SIZE / 2 + (SIZE * actor.scale) / 2 - 18}px, ${topEdge + 2}px, 0)`,
            transition: tr,
          }}
        >
          <span className="material-symbols-outlined text-[16px]">close</span>
        </button>
      )}
    </div>
  );
};
