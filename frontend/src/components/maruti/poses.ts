/**
 * Full-body Maruti poses cut from the artwork (public/buddy/poses/*.png).
 * Every PNG is resampled so his head is the same size as the layered Maruti (177x227 canvas),
 * so a pose drawn at `w / 177` of the sprite width always matches him.
 * To add a pose: drop the PNG into public/buddy/poses, add its name and size here, then use it in an activity.
 */
export type PoseName =
  | 'meditate-rock' | 'namaste-om' | 'scroll-write' | 'hold-mountain' | 'lift-mountain' | 'build-bridge'
  | 'fruit-basket' | 'water-sapling' | 'hold-baby' | 'fly-gada-rock' | 'fly-small';

export const POSES: Record<PoseName, { w: number; h: number }> = {
  'meditate-rock': { w: 175, h: 204 },
  'namaste-om': { w: 174, h: 237 },
  'scroll-write': { w: 198, h: 261 },
  'hold-mountain': { w: 194, h: 282 },
  'lift-mountain': { w: 171, h: 211 },
  'build-bridge': { w: 162, h: 210 },
  'fruit-basket': { w: 223, h: 226 },
  'water-sapling': { w: 114, h: 221 },
  'hold-baby': { w: 126, h: 256 },
  'fly-gada-rock': { w: 211, h: 257 },
  'fly-small': { w: 168, h: 229 },
};

export const poseSrc = (name: PoseName): string => `/buddy/poses/${name}.png`;
