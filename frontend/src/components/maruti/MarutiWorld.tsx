import React, { useCallback, useEffect, useRef, useState } from 'react';
import { BUDDY_NAME } from '../Buddy';
import { MarutiSprite } from './MarutiSprite';
import { shownMood } from './useMarutiBrain';
import type { MarutiBrain, MarutiMood } from './useMarutiBrain';
import { POSES, poseSrc } from './poses';
import type { PoseName } from './poses';
import { pick } from './lines';
import { JOKES } from './banter';

/** Layered Maruti width as a % of the stage width, and his height as a % of the stage height (stage 1024:559, sprite 177:227). */
const SPR = 24;
const SPR_H = SPR * ((1024 / 559) * (227 / 177));
const HOME = { x: 52, y: 91 };
const SAPLING = { x: 57.5, y: 90 };
const VINE_X = 74;
const VINE_END = 36;
const GRIP = 0.62; // how far down his body the hands are (0 = top, 1 = feet)
const EASE = 'cubic-bezier(.45,.05,.55,.95)';

const rand = (a: number, b: number) => a + Math.random() * (b - a);
const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));
/** Further up the hillside means further away means smaller. */
const depth = (y: number) => clamp(0.56 + (y - 64) * 0.0157, 0.56, 1);
const prefersReducedMotion = (): boolean =>
  typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** His little garden and the vine swing carry on between visits to his tab. */
let plantGrowth = 0;
let vineRuns = 0;

export type ActivityName =
  | 'stroll' | 'temple' | 'meditate' | 'snack' | 'garden' | 'write' | 'mountain' | 'bridge' | 'baby'
  | 'flight' | 'cloud' | 'climbR' | 'climbL' | 'swing' | 'joke';

export type WorldVis = { kind: 'layered'; mood: MarutiMood; cloud: boolean } | { kind: 'pose'; pose: PoseName };

export interface World {
  x: number;
  y: number;
  scale: number;
  rot: number;
  flip: boolean;
  dur: number;
  ease: string;
  vis: WorldVis;
  om: boolean;
  sapling: number;
  vine: number;
  hidden: boolean;
}

const lay = (mood: MarutiMood, cloud: boolean): WorldVis => ({ kind: 'layered', mood, cloud });

const initialWorld = (): World => ({
  x: HOME.x, y: HOME.y, scale: 1, rot: 0, flip: false, dur: 0, ease: EASE,
  vis: lay('idle', true), om: false, sapling: plantGrowth, vine: 0, hidden: false,
});

const LINES = {
  stroll: ['Chalo, thoda tehal ke aate hain.', 'Pair khol lete hain, phir kaam.', 'Ek chakkar, phir wapas.'],
  temple: ['Mandir tak ho aata hoon.', 'Ek pranam kar leta hoon.'],
  pray: ['Jai Shri Ram.', 'Ram naam mein sab hai.'],
  meditate: ['Ek minute. Saans andar, saans bahar.', 'Shaant. Bas saans pe dhyaan.'],
  snack: ['Phal khaa le, energy aayegi.', 'Kuch khaya? Phal le le.'],
  garden: ['Paudha roz ka paani maangta hai. Aadat bhi.', 'Thoda paani, thoda sabr.'],
  write: ['Aaj ka hisaab likh raha hoon.', 'Likhne se sab saaf dikhta hai.'],
  mountain: ['Sanjeevani laani hai. Bhaari hai!', 'Poora pahaad utha laya. Tu ek kaam utha le.'],
  bridge: ['Ek ek patthar, setu ban jaata hai. Kaam bhi.', 'Patthar pe Ram likho, sab tair jaayenge.'],
  baby: ['Chhota dost mil gaya.', 'Isko bhi saath le chalta hoon.'],
  flight: ['Uddd!', 'Upar se sab chhota dikhta hai.', 'Ek chakkar aasmaan ka.'],
  cloud: ['Baadal pe sawaar!', 'Apna baadal, apni raftaar.'],
  climbUp: ['Ped pe chadh raha hoon.', 'Pakad mazboot, chadhai aasaan.'],
  climbTop: ['Upar se sab saaf dikhta hai.', 'Yahan se tera din bhi dikhta hai.'],
  swing: ['Bel pakad li. Jhoola!', 'Jai Bajrang Bali!'],
  come: ['Aaya, aaya!', 'Yahin hoon.', 'Chalo!'],
} as const;

type Step = number | (() => void);

interface Builder {
  say: (text: string) => void;
  wait: (ms: number) => void;
  walk: (x: number, y: number) => void;
  fly: (x: number, y: number, pose?: PoseName, scale?: number) => void;
  glide: (x: number, y: number, scale?: number) => void;
  climb: (x: number, y: number, scale: number, rot: number, flip: boolean) => void;
  layered: (mood: MarutiMood, ms: number) => void;
  hold: (pose: PoseName, ms: number, opts?: { om?: boolean; flip?: boolean }) => void;
  show: (pose: PoseName) => void;
  vine: (on: boolean) => void;
  plant: () => void;
  cloud: (on: boolean) => void;
}

const ACTIVITIES: Record<ActivityName, (b: Builder) => void> = {
  stroll: (b) => {
    if (Math.random() < 0.6) b.say(pick(LINES.stroll));
    b.walk(rand(30, 72), rand(89, 93));
    b.wait(700);
    b.walk(rand(30, 72), rand(89, 93));
  },
  temple: (b) => {
    b.say(pick(LINES.temple));
    b.walk(44, 86);
    b.walk(40, 75);
    b.walk(36, 68);
    b.say(pick(LINES.pray));
    b.hold('namaste-om', 4500, { om: true });
    b.walk(40, 75);
    b.walk(46, 87);
    b.walk(HOME.x, HOME.y);
  },
  meditate: (b) => {
    b.walk(32, 87);
    b.say(pick(LINES.meditate));
    b.hold('meditate-rock', 7000, { om: true });
  },
  snack: (b) => {
    b.walk(60, 90);
    b.say(pick(LINES.snack));
    b.hold('fruit-basket', 4500);
  },
  garden: (b) => {
    b.walk(68, 89);
    b.say(pick(LINES.garden));
    b.plant();
    b.hold('water-sapling', 5200, { flip: false });
  },
  write: (b) => {
    b.walk(44, 91);
    b.say(pick(LINES.write));
    b.hold('scroll-write', 5500);
  },
  mountain: (b) => {
    b.walk(56, 91);
    b.say(pick(LINES.mountain));
    b.hold('lift-mountain', 3200);
    b.hold('hold-mountain', 3800, { flip: false });
  },
  bridge: (b) => {
    b.walk(50, 93);
    b.say(pick(LINES.bridge));
    b.hold('build-bridge', 5000);
  },
  baby: (b) => {
    b.walk(40, 90);
    b.say(pick(LINES.baby));
    b.hold('hold-baby', 4500);
  },
  flight: (b) => {
    b.say(pick(LINES.flight));
    b.fly(rand(24, 40), rand(42, 55), 'fly-small');
    b.fly(rand(55, 75), rand(40, 56), 'fly-gada-rock');
    b.fly(rand(30, 70), rand(48, 62), 'fly-small');
    b.fly(rand(40, 64), 91, 'fly-gada-rock', 1);
    b.wait(200);
  },
  cloud: (b) => {
    b.say(pick(LINES.cloud));
    b.glide(rand(24, 40), rand(48, 60), 0.75);
    b.glide(rand(60, 76), rand(46, 58), 0.75);
    b.glide(HOME.x, HOME.y, 1);
    b.wait(300);
  },
  climbR: (b) => {
    b.walk(86, 88);
    b.say(pick(LINES.climbUp));
    b.climb(93, 58, 0.62, 6, false);
    b.say(pick(LINES.climbTop));
    b.layered('hang', 3600);
    b.climb(93, 84, 0.78, 6, false);
    b.walk(80, 90);
  },
  climbL: (b) => {
    b.walk(14, 84);
    b.say(pick(LINES.climbUp));
    b.climb(9, 54, 0.62, -6, true);
    b.say(pick(LINES.climbTop));
    b.layered('hang', 3600);
    b.climb(9, 78, 0.78, -6, true);
    b.walk(22, 90);
  },
  swing: (b) => {
    const sw = 0.8;
    b.say(pick(LINES.swing));
    b.fly(VINE_X, VINE_END + (1 - GRIP) * SPR_H * sw, 'fly-small', sw);
    b.vine(true);
    b.wait(7000);
    b.vine(false);
    b.show('fly-small');
    b.fly(rand(58, 70), 90, 'fly-gada-rock', 1);
    b.wait(200);
  },
  joke: (b) => {
    const text = pick(JOKES);
    b.say(text);
    b.wait(Math.min(text.length, 90) * 28 + 500);
    const rofl = Math.random() < 0.45;
    b.layered(rofl ? 'rofl' : 'laugh', rofl ? 2200 : 1800);
  },
};

const WEIGHTS: [ActivityName, number][] = [
  ['stroll', 14], ['temple', 6], ['meditate', 7], ['snack', 6], ['garden', 6], ['write', 6], ['mountain', 5],
  ['bridge', 5], ['baby', 4], ['flight', 10], ['cloud', 6], ['climbR', 8], ['climbL', 6], ['swing', 7], ['joke', 4],
];

/** The buttons under the stage. Each one is just an activity he can do on request. */
export const WORLD_CHIPS: { label: string; run: ActivityName | 'climb' }[] = [
  { label: 'Fly', run: 'flight' },
  { label: 'Cloud', run: 'cloud' },
  { label: 'Climb', run: 'climb' },
  { label: 'Swing', run: 'swing' },
  { label: 'Temple', run: 'temple' },
  { label: 'Meditate', run: 'meditate' },
  { label: 'Snack', run: 'snack' },
  { label: 'Water', run: 'garden' },
  { label: 'Write', run: 'write' },
  { label: 'Lift', run: 'mountain' },
  { label: 'Bridge', run: 'bridge' },
  { label: 'Friend', run: 'baby' },
];

export interface MarutiWorldApi {
  world: World;
  canMove: boolean;
  start: (name: ActivityName | 'climb') => void;
  tapStage: (px: number, py: number) => void;
}

/**
 * Maruti's life on the hillside. The director plays small scripts (walk, climb, fly, swing, pray, garden...) by moving
 * one actor around the stage in stage-percent coordinates. Anything the chat needs (he talks, thinks, laughs, you type,
 * he sleeps, the roaming overlay takes him) cancels the script and he comes straight home, so chat reactions always win.
 */
export function useMarutiWorld(brain: MarutiBrain): MarutiWorldApi {
  const [world, setWorld] = useState<World>(initialWorld);
  const brainRef = useRef(brain);
  brainRef.current = brain;
  const cur = useRef({ x: HOME.x, y: HOME.y, flip: false });
  const cloudRef = useRef(true);
  const busy = useRef<string | null>(null);
  const lastAct = useRef('');
  const timers = useRef<number[]>([]);
  const canMove = !brain.calm && !brain.quiet && !brain.comfort && !prefersReducedMotion();
  const interrupted = brain.mood !== 'idle' || brain.comfort || brain.quiet || brain.away || !canMove;

  const patch = useCallback((p: Partial<World>) => {
    if (p.x !== undefined) cur.current.x = p.x;
    if (p.y !== undefined) cur.current.y = p.y;
    if (p.flip !== undefined) cur.current.flip = p.flip;
    setWorld((w) => ({ ...w, ...p }));
  }, []);

  const clearTimers = useCallback(() => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  }, []);

  const settle = useCallback(() => {
    busy.current = null;
    patch({ vis: lay('idle', cloudRef.current), om: false, vine: 0, hidden: false, rot: 0, dur: 300 });
  }, [patch]);

  const goHome = useCallback(() => {
    clearTimers();
    busy.current = null;
    cloudRef.current = true;
    const ms = clamp(Math.hypot(HOME.x - cur.current.x, (HOME.y - cur.current.y) * 1.6) * 28, 500, 1500);
    patch({
      x: HOME.x, y: HOME.y, scale: 1, rot: 0, flip: false, dur: ms, ease: EASE,
      vis: lay('idle', true), om: false, vine: 0, hidden: false,
    });
  }, [clearTimers, patch]);

  const play = useCallback(
    (name: string, script: (b: Builder) => void) => {
      clearTimers();
      busy.current = name;
      lastAct.current = name;
      const steps: Step[] = [];
      let px = cur.current.x;
      let py = cur.current.y;
      let pf = cur.current.flip;
      const face = (x: number) => {
        if (x < px - 0.5) pf = true;
        else if (x > px + 0.5) pf = false;
        return pf;
      };
      const b: Builder = {
        say: (text) => {
          steps.push(() => brainRef.current.say(text, { mood: 'idle', speak: false, hold: 3600 }));
        },
        wait: (ms) => {
          steps.push(ms);
        },
        walk: (x, y) => {
          const ms = clamp(Math.hypot(x - px, (y - py) * 1.6) * 55, 500, 4200);
          const flip = face(x);
          const scale = depth(y);
          steps.push(() => {
            cloudRef.current = false;
            patch({ x, y, scale, rot: 0, flip, dur: ms, ease: 'linear', vis: lay('walk', false) });
          });
          steps.push(ms);
          steps.push(() => patch({ vis: lay('idle', false) }));
          px = x;
          py = y;
        },
        fly: (x, y, pose = 'fly-small', scale = 0.8) => {
          const ms = clamp(Math.hypot(x - px, (y - py) * 1.6) * 38, 700, 2600);
          const flip = face(x);
          steps.push(() => {
            cloudRef.current = false;
            patch({ x, y, scale, rot: flip ? -7 : 7, flip, dur: ms, ease: EASE, vis: { kind: 'pose', pose } });
          });
          steps.push(ms);
          px = x;
          py = y;
        },
        glide: (x, y, scale = 0.75) => {
          const ms = clamp(Math.hypot(x - px, (y - py) * 1.6) * 42, 800, 2800);
          const flip = face(x);
          steps.push(() => {
            cloudRef.current = true;
            patch({ x, y, scale, rot: flip ? -4 : 4, flip, dur: ms, ease: EASE, vis: lay('fly', true) });
          });
          steps.push(ms);
          px = x;
          py = y;
        },
        climb: (x, y, scale, rot, flip) => {
          const ms = clamp(Math.abs(y - py) * 85, 1200, 4200);
          pf = flip;
          steps.push(() => {
            cloudRef.current = false;
            patch({ x, y, scale, rot, flip, dur: ms, ease: 'ease-in-out', vis: lay('climb', false) });
          });
          steps.push(ms);
          px = x;
          py = y;
        },
        layered: (mood, ms) => {
          steps.push(() => patch({ vis: lay(mood, cloudRef.current) }));
          steps.push(ms);
        },
        hold: (pose, ms, opts = {}) => {
          const flip = opts.flip ?? pf;
          pf = flip;
          steps.push(() => patch({ vis: { kind: 'pose', pose }, rot: 0, flip, om: opts.om ?? false }));
          steps.push(ms);
          if (opts.om) steps.push(() => patch({ om: false }));
        },
        show: (pose) => {
          steps.push(() => patch({ vis: { kind: 'pose', pose } }));
        },
        vine: (on) => {
          steps.push(() => {
            if (on) {
              vineRuns += 1;
              patch({ vine: vineRuns, hidden: true });
            } else {
              patch({ vine: 0, hidden: false });
            }
          });
        },
        plant: () => {
          steps.push(() => {
            plantGrowth = plantGrowth === 0 ? 0.35 : Math.min(1, plantGrowth + 0.2);
            patch({ sapling: plantGrowth });
          });
        },
        cloud: (on) => {
          steps.push(() => {
            cloudRef.current = on;
          });
        },
      };
      script(b);
      let t = 0;
      for (const s of steps) {
        if (typeof s === 'number') t += s;
        else timers.current.push(window.setTimeout(s, t));
      }
      timers.current.push(window.setTimeout(settle, t + 50));
    },
    [clearTimers, patch, settle],
  );

  const start = useCallback(
    (name: ActivityName | 'climb') => {
      const b = brainRef.current;
      if (b.mood !== 'idle' || b.away || b.calm || b.quiet || b.comfort || prefersReducedMotion()) return;
      const act: ActivityName = name === 'climb' ? (Math.random() < 0.6 ? 'climbR' : 'climbL') : name;
      play(act, ACTIVITIES[act]);
    },
    [play],
  );

  /** Tap the scenery: a tree he climbs, the sky he flies to, the ground he walks to. */
  const tapStage = useCallback(
    (px: number, py: number) => {
      const b = brainRef.current;
      if (b.mood !== 'idle' || b.away || b.calm || b.quiet || b.comfort || prefersReducedMotion()) return;
      if (px > 84 && py > 38) start('climbR');
      else if (px < 14 && py > 34) start('climbL');
      else if (py < 60) {
        const tx = clamp(px, 18, 82);
        play('goto', (s) => {
          s.say(pick(LINES.come));
          s.fly(tx, clamp(py + 16, 42, 72), 'fly-small');
          s.wait(2200);
          s.fly(tx, 90, 'fly-small', 1);
          s.wait(200);
        });
      } else {
        play('goto', (s) => {
          s.say(pick(LINES.come));
          s.walk(clamp(px, 24, 76), clamp(py, 87, 93));
          s.wait(400);
        });
      }
    },
    [play, start],
  );

  // Chat, typing, sleep, calm mode or the roaming overlay needs him: drop the script and come home.
  useEffect(() => {
    if (!interrupted) return;
    const far = Math.hypot(HOME.x - cur.current.x, HOME.y - cur.current.y) > 1;
    if (busy.current || far) goHome();
  }, [interrupted, goHome]);

  // Left alone, he gets on with his day every so often.
  useEffect(() => {
    if (!canMove) return;
    let id: number;
    const tick = () => {
      id = window.setTimeout(() => {
        const b = brainRef.current;
        if (document.visibilityState === 'visible' && !busy.current && b.mood === 'idle' && !b.away && !b.comfort && !b.quiet) {
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
        }
        tick();
      }, rand(5500, 9500));
    };
    tick();
    return () => window.clearTimeout(id);
  }, [canMove, play]);

  // Never leave a timer running behind a screen that is gone.
  useEffect(() => () => clearTimers(), [clearTimers]);

  return { world, canMove, start, tapStage };
}

/** His own little pixel sapling. It keeps growing every time he waters it. */
const Sapling: React.FC<{ g: number }> = ({ g }) => (
  <svg
    viewBox="0 0 12 14"
    shapeRendering="crispEdges"
    aria-hidden="true"
    className="absolute pointer-events-none"
    style={{
      left: `${SAPLING.x}%`, top: `${SAPLING.y}%`, width: '5%', aspectRatio: '12 / 14',
      transform: `translate(-50%, -100%) scale(${g})`, transformOrigin: '50% 100%', transition: 'transform 4500ms linear',
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
);

/** A vine from above the stage. He hangs on it and swings, slowing to a stop (the swing is a 7s CSS animation). */
const Vine: React.FC = () => (
  <div
    className="mv"
    aria-hidden="true"
    style={{ height: `${VINE_END + 1}%`, transformOrigin: `${VINE_X}% 0` }}
  >
    <div className="mv-line" style={{ left: `${VINE_X}%` }} />
    {[14, 34, 54, 74].map((t, i) => (
      <span key={t} className={`mv-leaf ${i % 2 ? 'mv-leaf-r' : 'mv-leaf-l'}`} style={{ left: `${VINE_X}%`, top: `${t}%` }} />
    ))}
    <div className="absolute" style={{ left: `${VINE_X}%`, top: '100%', width: `${SPR * 0.8}%`, transform: `translate(-50%, -${GRIP * 100}%)` }}>
      <MarutiSprite mood="hang" ground />
    </div>
  </div>
);

/** The one Maruti on the stage: layered when he walks, climbs or reacts to chat, a full-body pose when he does something. */
export const MarutiActor: React.FC<{ brain: MarutiBrain; world: World; onTap: () => void }> = ({ brain, world, onTap }) => {
  const forced = brain.mood !== 'idle' || brain.comfort || brain.quiet;
  const vis: WorldVis = forced ? lay(shownMood(brain), true) : world.vis;
  const hidden = brain.away || world.hidden;
  const widthPct = vis.kind === 'pose' ? (POSES[vis.pose].w / 177) * SPR : SPR;
  const drop = vis.kind === 'layered' && !vis.cloud ? 8 : 0;
  const tr = world.dur ? `left ${world.dur}ms ${world.ease}, top ${world.dur}ms ${world.ease}, transform ${world.dur}ms ${world.ease}` : 'none';

  return (
    <div
      className="absolute"
      style={{
        left: `${world.x}%`, top: `${world.y}%`, width: `${widthPct}%`,
        transform: `translate(-50%, ${-100 + drop}%) scale(${world.scale}) rotate(${world.rot}deg)`,
        transformOrigin: '50% 100%', transition: tr, visibility: hidden ? 'hidden' : 'visible', zIndex: 5,
      }}
    >
      {vis.kind === 'layered' ? (
        <MarutiSprite home mood={vis.mood} flip={world.flip} ground={!vis.cloud} onTap={onTap} />
      ) : (
        <button
          type="button"
          onClick={onTap}
          aria-label={`${BUDDY_NAME}. Tap to say hi`}
          data-maruti-home=""
          className="mp"
        >
          <span className={`mp-flip ${world.flip ? 'mp-flipped' : ''}`}>
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
      {world.om && !forced && (
        <>
          <span className="mp-om" aria-hidden="true" style={{ left: '58%' }}>ॐ</span>
          <span className="mp-om" aria-hidden="true" style={{ left: '30%', animationDelay: '1.3s' }}>ॐ</span>
        </>
      )}
    </div>
  );
};

/** Everything that lives on the stage besides Maruti himself. */
export const MarutiProps: React.FC<{ world: World }> = ({ world }) => (
  <>
    {world.sapling > 0 && <Sapling g={world.sapling} />}
    {world.vine > 0 && <Vine key={world.vine} />}
  </>
);
