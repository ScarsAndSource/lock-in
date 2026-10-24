import React from 'react';
import { BUDDY_NAME } from '../Buddy';
import { MarutiSprite } from './MarutiSprite';
import { MarutiActor, MarutiProps, WORLD_CHIPS, useMarutiWorld } from './MarutiWorld';
import { shownMood } from './useMarutiBrain';
import type { MarutiBrain } from './useMarutiBrain';

const Bubble: React.FC<{ text: string; className?: string }> = ({ text, className = '' }) => (
  <div
    role="status"
    aria-live="polite"
    className={`relative bg-surface text-ink border border-line rounded-2xl px-3 py-2 font-small text-small shadow-sm ${className}`}
  >
    {text}
  </div>
);

/** Voice on/off and calm mode (no wandering), both remembered on this device. */
export const MarutiControls: React.FC<{ brain: MarutiBrain; className?: string }> = ({ brain, className = '' }) => (
  <div className={`flex gap-1 ${className}`}>
    <button
      type="button"
      onClick={brain.toggleVoice}
      aria-pressed={brain.voice}
      aria-label={brain.voice ? `Mute ${BUDDY_NAME}'s voice` : `Let ${BUDDY_NAME} speak`}
      className="w-8 h-8 rounded-lg bg-surface border border-line text-ink flex items-center justify-center"
    >
      <span className="material-symbols-outlined text-[18px]">{brain.voice ? 'volume_up' : 'volume_off'}</span>
    </button>
    <button
      type="button"
      onClick={brain.toggleCalm}
      aria-pressed={brain.calm}
      aria-label={brain.calm ? `Let ${BUDDY_NAME} move around` : `Keep ${BUDDY_NAME} still`}
      className="w-8 h-8 rounded-lg bg-surface border border-line text-ink flex items-center justify-center"
    >
      <span className="material-symbols-outlined text-[18px]">{brain.calm ? 'motion_photos_off' : 'motion_photos_on'}</span>
    </button>
  </div>
);

/**
 * Empty chat: Maruti lives on the hillside. He walks the path, climbs the trees, flies, swings on a vine, prays at the
 * temple, meditates, waters his sapling and more. Tap the sky to fly him there, a tree to climb it, the ground to call him,
 * or use the buttons. While the roaming overlay is him (flying across the screen, eavesdropping, standing guard) he hides here.
 */
export const MarutiHero: React.FC<{ brain: MarutiBrain }> = ({ brain }) => {
  const { world, canMove, start, tapStage } = useMarutiWorld(brain);

  const onStageClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('button')) return;
    const r = e.currentTarget.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) return;
    tapStage(((e.clientX - r.left) / r.width) * 100, ((e.clientY - r.top) / r.height) * 100);
  };

  return (
    <div className="space-y-2">
      <div
        role="presentation"
        onClick={onStageClick}
        className="relative w-full overflow-hidden rounded-2xl border border-line"
        style={{ aspectRatio: '1024 / 559' }}
      >
        <img src="/buddy/maruti-stage.webp" alt="" className="absolute inset-0 w-full h-full object-cover" draggable={false} />
        <MarutiProps world={world} />
        <MarutiActor brain={brain} world={world} onTap={brain.poke} />
        {brain.bubble && !brain.away && <Bubble text={brain.bubble} className="absolute left-2 top-2 max-w-[40%] z-10" />}
        <MarutiControls brain={brain} className="absolute right-2 top-2 z-10" />
      </div>
      <div className="flex gap-1.5 overflow-x-auto pb-1" aria-label={`Ask ${BUDDY_NAME} to do something`}>
        {WORLD_CHIPS.map((chip) => (
          <button
            key={chip.label}
            type="button"
            disabled={!canMove}
            onClick={() => start(chip.run)}
            className="shrink-0 whitespace-nowrap rounded-full bg-surface border border-line text-ink px-3 py-1 font-caption text-caption disabled:opacity-40"
          >
            {chip.label}
          </button>
        ))}
      </div>
      <p className="font-section text-section text-ink">Hey, I’m {BUDDY_NAME}.</p>
      <p className="font-caption text-caption text-muted-text">
        {canMove
          ? 'Tap the sky to fly him there, a tree to climb it, the path to call him.'
          : `${BUDDY_NAME} is keeping still right now.`}
      </p>
    </div>
  );
};

/** Once a chat has messages Maruti shrinks to a strip above them: still reacting, never in the way. */
export const MarutiStrip: React.FC<{ brain: MarutiBrain }> = ({ brain }) => (
  <div className="flex items-end gap-2 mb-2 shrink-0">
    <div className="w-[52px] shrink-0">
      <MarutiSprite
        home
        mood={shownMood(brain)}
        flip={brain.flip}
        onTap={brain.poke}
        className={brain.away ? 'invisible' : ''}
      />
    </div>
    <div className="flex-1 min-w-0 min-h-[40px] flex items-center">
      {brain.bubble && !brain.away ? (
        <Bubble text={brain.bubble} />
      ) : (
        !brain.away && <span className="font-caption text-caption text-muted-text">{BUDDY_NAME} is here. Tap him.</span>
      )}
    </div>
    <MarutiControls brain={brain} />
  </div>
);
