import type { MarutiMood } from './useMarutiBrain';
import type { PoseName } from './poses';
import {
  CLIMB_LINES, FLY_LINES, IDLE_CHATTER, IDLE_THOUGHTS, PEEK_LINES, SIDE_LINES, WALK_LINES, WAVES, pick,
} from './lines';
import { JOKES, SELF_LAUGH } from './banter';

/**
 * Everything Maruti can do on the screen, as small scripts. A script only describes what happens (walk here, hold
 * this pose, say this); MarutiCompanion plays it. All coordinates are CSS pixels. A sprite's (x, y) is the top-left of his
 * SIZE x H box, so his feet are at y + H.
 */

/** Layered Maruti width in px, and his height (the artwork is 177 x 227). */
export const SIZE = 64;
export const H = Math.round((SIZE * 227) / 177);
export const HOME_X = 8;
export const GUARD_SCALE = 1.7;
export const EASE = 'cubic-bezier(.45,.05,.55,.95)';
export const POP = 'cubic-bezier(.2,1.35,.4,1)';
/** Where the hands sit on his body when he hangs on the vine (0 = top, 1 = feet). */
export const GRIP = 0.62;
export const VINE_SCALE = 0.8;

export const rand = (a: number, b: number): number => a + Math.random() * (b - a);
export const clamp = (v: number, a: number, b: number): number => Math.min(b, Math.max(a, v));

export type Vis = { kind: 'layered'; mood: MarutiMood; cloud: boolean } | { kind: 'pose'; pose: PoseName };
export const lay = (mood: MarutiMood, cloud: boolean): Vis => ({ kind: 'layered', mood, cloud });
export const pose = (name: PoseName): Vis => ({ kind: 'pose', pose: name });
/** One shared object so "he is already resting" can be told apart from "he needs to change" by reference. */
export const IDLE_HOME: Vis = lay('idle', true);

export interface Place {
  x: number;
  y: number;
  rot: number;
  scale: number;
  flip: boolean;
}

/** The screen as it is right now. `ground` is where his feet stand (the nav bar, or the chat input on his own tab). */
export interface Geo {
  W: number;
  navTop: number;
  hdrB: number;
  ground: number;
}

export const homePlace = (g: Geo): Place => ({ x: HOME_X, y: g.ground - H, rot: 0, scale: 1, flip: false });

export interface Builder {
  g: Geo;
  /** Lines about the tab he is visiting (empty on his own tab). Peeks borrow them so he comments on where he is. */
  tabLines: readonly string[];
  say: (text: string) => void;
  wait: (ms: number) => void;
  /** Appear instantly. Follow with wait(60) before animating so the browser paints the start first. */
  jump: (place: Partial<Place>, vis?: Vis) => void;
  /** Animate to `place` and wait for it to finish. */
  to: (place: Partial<Place>, ms: number, ease?: string, vis?: Vis) => void;
  /** Walk along the ground to x. Returns the x he actually walks to. */
  walk: (x: number, free?: boolean) => number;
  fly: (x: number, y: number, p?: PoseName, scale?: number) => void;
  glide: (x: number, y: number, scale?: number) => void;
  climb: (x: number, y: number, scale: number, rot: number, flip: boolean) => void;
  /** Show something and stay on it for ms. */
  look: (vis: Vis, ms: number, opts?: { om?: boolean; flip?: boolean; rot?: number }) => void;
  vine: (on: boolean, x?: number, len?: number) => void;
  /** Plants (or removes, with null) his sapling and makes it grow a little. x is its centre. */
  sapling: (x: number | null) => void;
  /** Back to his spot, on foot or on the cloud. Called for you when a script ends away from home. */
  home: () => void;
  /** Slip out from behind the nav bar at his spot. Does nothing when he is only visiting another tab: he just leaves. */
  popHome: () => void;
}

export type Script = (b: Builder) => void;

export type ActivityName =
  | 'stroll' | 'pray' | 'meditate' | 'snack' | 'garden' | 'write' | 'mountain' | 'bridge' | 'baby'
  | 'flight' | 'cloud' | 'climbR' | 'climbL' | 'swing' | 'joke' | 'wave' | 'chatter' | 'thought'
  | 'peekBottom' | 'peekSide' | 'peekTop' | 'rollNav' | 'walkIn' | 'flyBy';

const LINES = {
  stroll: ['Chalo, thoda tehal ke aate hain.', 'Pair khol lete hain, phir kaam.', 'Ek chakkar, phir wapas.'],
  pray: ['Jai Shri Ram.', 'Ram naam mein sab hai.', 'Ek pranam kar leta hoon.'],
  meditate: ['Ek minute. Saans andar, saans bahar.', 'Shaant. Bas saans pe dhyaan.'],
  snack: ['Phal khaa le, energy aayegi.', 'Kuch khaya? Phal le le.'],
  garden: ['Paudha roz ka paani maangta hai. Aadat bhi.', 'Thoda paani, thoda sabr.'],
  write: ['Aaj ka hisaab likh raha hoon.', 'Likhne se sab saaf dikhta hai.'],
  mountain: ['Sanjeevani laani hai. Bhaari hai!', 'Poora pahaad utha laya. Tu ek kaam utha le.'],
  bridge: ['Ek ek patthar, setu ban jaata hai. Kaam bhi.', 'Patthar pe Ram likho, sab tair jaayenge.'],
  baby: ['Chhota dost mil gaya.', 'Isko bhi saath le chalta hoon.'],
  flight: ['Uddd!', 'Upar se sab chhota dikhta hai.', 'Ek chakkar aasmaan ka.'],
  cloud: ['Baadal pe sawaar!', 'Apna baadal, apni raftaar.'],
  climbUp: ['Kinaare pe chadh raha hoon.', 'Pakad mazboot, chadhai aasaan.'],
  climbTop: ['Upar se sab saaf dikhta hai.', 'Yahan se tera din bhi dikhta hai.'],
  swing: ['Bel pakad li. Jhoola!', 'Jai Bajrang Bali!'],
} as const;

/** What he says when he peeks: often something about the tab he is on, otherwise a generic peek line. */
const peekLine = (b: Builder, pool: readonly string[] = PEEK_LINES): string =>
  pick(b.tabLines.length > 0 && Math.random() < 0.6 ? b.tabLines : pool);

/** A random x along the ground, kept off the very edges. */
const spot = (g: Geo): number => rand(24, Math.max(25, g.W - SIZE - 24));

/** Walk somewhere, say a line, then hold a full-body pose. */
const doing = (lines: readonly string[], poseName: PoseName, ms: number, opts?: { om?: boolean }): Script => (b) => {
  b.walk(spot(b.g));
  b.say(pick(lines));
  b.look(pose(poseName), ms, opts);
};

const climbEdge = (right: boolean): Script => (b) => {
  const { g } = b;
  const floor = g.ground - H;
  const edgeX = right ? g.W - SIZE * 0.55 : -SIZE * 0.45;
  const rot = right ? -8 : 8;
  const top = clamp(rand(g.hdrB + 50, g.navTop * 0.6), g.hdrB + 20, floor - 60);
  b.walk(edgeX, true);
  b.say(pick(LINES.climbUp));
  b.climb(edgeX, top, 1, rot, right);
  b.say(pick([...LINES.climbTop, ...CLIMB_LINES]));
  b.look(lay('hang', false), 3600, { flip: right, rot });
  b.climb(edgeX, floor, 1, rot, right);
};

export const ACTIVITIES: Record<ActivityName, Script> = {
  stroll: (b) => {
    if (Math.random() < 0.6) b.say(pick(LINES.stroll));
    b.walk(spot(b.g));
    b.wait(700);
    b.walk(spot(b.g));
  },
  pray: doing(LINES.pray, 'namaste-om', 4500, { om: true }),
  meditate: doing(LINES.meditate, 'meditate-rock', 7000, { om: true }),
  snack: doing(LINES.snack, 'fruit-basket', 4500),
  write: doing(LINES.write, 'scroll-write', 5500),
  bridge: doing(LINES.bridge, 'build-bridge', 5000),
  baby: doing(LINES.baby, 'hold-baby', 4500),
  garden: (b) => {
    const x = b.walk(rand(70, Math.max(71, b.g.W - SIZE - 24)));
    b.say(pick(LINES.garden));
    b.sapling(x + SIZE / 2 - 34); // the can is on his left, so the sapling goes there
    b.look(pose('water-sapling'), 5200, { flip: false });
  },
  mountain: (b) => {
    b.walk(spot(b.g));
    b.say(pick(LINES.mountain));
    b.look(pose('lift-mountain'), 3200);
    b.look(pose('hold-mountain'), 3800, { flip: false });
  },
  flight: (b) => {
    const { g } = b;
    const minY = g.hdrB + 20;
    const maxY = Math.max(minY + 40, g.ground - H - 20);
    const fx = () => rand(8, Math.max(9, g.W - SIZE - 8));
    const fy = () => rand(minY, maxY);
    const h = homePlace(g);
    b.say(pick([...LINES.flight, ...FLY_LINES]));
    b.fly(fx(), fy(), 'fly-small');
    b.fly(fx(), fy(), 'fly-gada-rock');
    b.fly(fx(), fy(), 'fly-small');
    b.fly(h.x, h.y, 'fly-gada-rock', 1);
    b.wait(200);
  },
  cloud: (b) => {
    const { g } = b;
    const minY = g.hdrB + 30;
    const maxY = Math.max(minY + 40, g.ground - H - 30);
    b.say(pick(LINES.cloud));
    b.glide(rand(8, g.W / 2), rand(minY, maxY), 0.75);
    b.glide(rand(g.W / 2, Math.max(g.W / 2 + 1, g.W - SIZE - 8)), rand(minY, maxY), 0.75);
  },
  climbR: climbEdge(true),
  climbL: climbEdge(false),
  swing: (b) => {
    const { g } = b;
    const vx = rand(60, Math.max(61, g.W - 60));
    const len = clamp((g.ground - g.hdrB) * 0.45, 110, 260);
    const handsY = g.hdrB + len;
    const h = homePlace(g);
    b.say(pick(LINES.swing));
    // Feet end up (1 - GRIP) of his scaled height below his hands: that is where the hanging sprite's feet are.
    b.fly(vx - SIZE / 2, handsY + (1 - GRIP) * H * VINE_SCALE - H, 'fly-small', VINE_SCALE);
    b.vine(true, vx, len);
    b.wait(7000);
    b.vine(false);
    b.look(pose('fly-small'), 0);
    b.fly(h.x, h.y, 'fly-gada-rock', 1);
    b.wait(200);
  },
  joke: (b) => {
    const text = pick(JOKES);
    b.say(text);
    b.wait(Math.min(text.length, 90) * 28 + 500);
    const rofl = Math.random() < 0.45;
    b.look(lay(rofl ? 'rofl' : 'laugh', true), rofl ? 2200 : 1800);
  },
  wave: (b) => {
    b.say(pick(WAVES));
    b.look(lay('wave', true), 1900);
  },
  chatter: (b) => {
    b.say(pick(IDLE_CHATTER));
    b.look(lay('talking', true), 2400);
    b.wait(900);
  },
  thought: (b) => {
    b.say(pick(IDLE_THOUGHTS));
    b.look(lay('ponder', true), 3600);
  },
  peekBottom: (b) => {
    const { g } = b;
    const x = clamp(rand(40, g.W - 40) - SIZE / 2, 6, g.W - SIZE - 6);
    b.jump({ x, y: g.navTop + 6, rot: 0, scale: 1, flip: x > g.W / 2 }, lay('peek', true));
    b.wait(60);
    b.to({ y: g.navTop - H * 0.55 }, 650, POP);
    b.wait(100);
    if (Math.random() < 0.7) b.say(peekLine(b));
    b.wait(3400);
    b.to({ y: g.navTop + 6 }, 450);
    b.popHome();
  },
  peekSide: (b) => {
    const { g } = b;
    const right = Math.random() < 0.5;
    const y = rand(g.hdrB + 30, Math.max(g.hdrB + 60, g.ground - H - 30));
    const outX = right ? g.W + 6 : -SIZE - 6;
    const inX = right ? g.W - SIZE * 0.55 : -SIZE * 0.45;
    b.jump({ x: outX, y, rot: 0, scale: 1, flip: right }, lay('peek', true));
    b.wait(60);
    b.to({ x: inX, rot: right ? -10 : 10 }, 700, POP);
    b.wait(100);
    b.say(peekLine(b, SIDE_LINES));
    b.wait(3100);
    b.to({ x: outX, rot: 0 }, 500);
    b.popHome();
  },
  peekTop: (b) => {
    const { g } = b;
    const x = rand(30, Math.max(31, g.W - SIZE - 30));
    b.jump({ x, y: g.hdrB - H - 4, rot: 180, scale: 1, flip: false }, lay('peek', true));
    b.wait(60);
    b.to({ y: g.hdrB - H * 0.5 }, 700, POP);
    b.wait(100);
    b.say(peekLine(b));
    b.wait(3100);
    b.to({ y: g.hdrB - H - 4 }, 480);
    b.popHome();
  },
  rollNav: (b) => {
    const { g } = b;
    const dir = Math.random() < 0.5 ? 1 : -1;
    const y = g.ground - H;
    const inX = dir > 0 ? 12 : g.W - SIZE - 12;
    const toX = dir > 0 ? g.W - SIZE - 12 : 12;
    b.jump({ x: dir > 0 ? -SIZE - 10 : g.W + 10, y, rot: 0, scale: 1, flip: dir < 0 }, lay('laugh', false));
    b.wait(60);
    b.to({ x: inX }, 900);
    b.say(pick(SELF_LAUGH));
    b.to({ x: toX, rot: dir * 720 }, 2400, 'ease-in-out');
    b.jump({ rot: 0 }); // two full turns later he looks the same, so reset without animating
    b.wait(60);
    b.to({ y: g.navTop + 6 }, 500);
    b.popHome();
  },
  /** The visitor's fly-through: in from one side, one swoop across the upper screen, out the other. He does not stop. */
  flyBy: (b) => {
    const { g } = b;
    const dir = Math.random() < 0.5 ? 1 : -1;
    const minY = g.hdrB + 40;
    const maxY = Math.max(minY + 40, g.navTop * 0.6);
    const startX = dir > 0 ? -SIZE - 20 : g.W + 20;
    const endX = dir > 0 ? g.W + 20 : -SIZE - 20;
    b.jump({ x: startX, y: rand(minY, maxY), rot: 0, scale: 0.8, flip: dir < 0 }, pose('fly-small'));
    b.wait(60);
    b.fly(g.W / 2 - SIZE / 2, rand(minY, maxY), 'fly-gada-rock');
    if (Math.random() < 0.6) b.say(pick(FLY_LINES));
    b.fly(endX, rand(minY, maxY), 'fly-small');
  },
  walkIn: (b) => {
    const { g } = b;
    const dir = Math.random() < 0.5 ? 1 : -1;
    const y = g.ground - H;
    const midX = rand(g.W * 0.25, Math.max(g.W * 0.26, g.W * 0.65));
    b.jump({ x: dir > 0 ? -SIZE - 10 : g.W + 10, y, rot: 0, scale: 1, flip: dir < 0 }, lay('walk', false));
    b.wait(60);
    b.to({ x: midX }, 2400, 'ease-out');
    b.say(pick(WALK_LINES));
    b.look(lay('wave', false), 2100);
    b.to({ x: dir > 0 ? g.W + 10 : -SIZE - 10 }, 2400, 'ease-in', lay('walk', false));
    b.popHome();
  },
};

export const WEIGHTS: [ActivityName, number][] = [
  ['stroll', 14], ['pray', 6], ['meditate', 7], ['snack', 6], ['garden', 6], ['write', 6], ['mountain', 5],
  ['bridge', 5], ['baby', 4], ['flight', 10], ['cloud', 6], ['climbR', 8], ['climbL', 6], ['swing', 7], ['joke', 4],
  ['wave', 3], ['chatter', 4], ['thought', 3], ['peekBottom', 5], ['peekSide', 4], ['peekTop', 3], ['rollNav', 4],
  ['walkIn', 4],
];

/** On other tabs he only peeks (and, now and then, flies through). */
export const VISITOR_PEEKS: ActivityName[] = ['peekBottom', 'peekSide', 'peekTop'];

export type ChipRun = ActivityName | 'climb';

/** The buttons in his chat. Each one is just an activity he can do on request. */
export const WORLD_CHIPS: { label: string; run: ChipRun }[] = [
  { label: 'Fly', run: 'flight' },
  { label: 'Cloud', run: 'cloud' },
  { label: 'Climb', run: 'climb' },
  { label: 'Swing', run: 'swing' },
  { label: 'Pray', run: 'pray' },
  { label: 'Meditate', run: 'meditate' },
  { label: 'Snack', run: 'snack' },
  { label: 'Water', run: 'garden' },
  { label: 'Write', run: 'write' },
  { label: 'Lift', run: 'mountain' },
  { label: 'Bridge', run: 'bridge' },
  { label: 'Friend', run: 'baby' },
];

/** Any screen can ask him to do something; MarutiCompanion listens. */
export const DO_EVENT = 'maruti:do';
export const askMaruti = (what: ChipRun): void => {
  window.dispatchEvent(new CustomEvent<ChipRun>(DO_EVENT, { detail: what }));
};
