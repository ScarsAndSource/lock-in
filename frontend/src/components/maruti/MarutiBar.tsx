import React from 'react';
import { BUDDY_NAME } from '../Buddy';
import { WORLD_CHIPS, askMaruti } from './activities';
import { usePrefersReducedMotion } from './motion';
import type { MarutiBrain } from './useMarutiBrain';

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
 * Maruti himself lives on the screen (MarutiPet). This is only his remote: the buttons that ask him to do something,
 * plus voice and calm. Full in an empty chat, just the two switches once you are talking.
 */
export const MarutiBar: React.FC<{ brain: MarutiBrain; compact?: boolean }> = ({ brain, compact = false }) => {
  const reduced = usePrefersReducedMotion();
  const canMove = !brain.calm && !brain.quiet && !brain.comfort && !reduced;

  if (compact) {
    return (
      <div className="flex justify-end mb-2 shrink-0">
        <MarutiControls brain={brain} />
      </div>
    );
  }

  return (
    <div className="space-y-2 text-center shrink-0 mb-2">
      <div className="flex items-center justify-between gap-2">
        <p className="font-section text-section text-ink">Hey, I’m {BUDDY_NAME}.</p>
        <MarutiControls brain={brain} />
      </div>
      <div className="flex gap-1.5 overflow-x-auto pb-1 text-left" aria-label={`Ask ${BUDDY_NAME} to do something`}>
        {WORLD_CHIPS.map((chip) => (
          <button
            key={chip.label}
            type="button"
            disabled={!canMove}
            onClick={() => askMaruti(chip.run)}
            className="shrink-0 whitespace-nowrap rounded-full bg-surface border border-line text-ink px-3 py-1 font-caption text-caption disabled:opacity-40"
          >
            {chip.label}
          </button>
        ))}
      </div>
      <p className="font-caption text-caption text-muted-text">
        {canMove ? `Pick one, or tap him, and ${BUDDY_NAME} does it right on your screen.` : `${BUDDY_NAME} is keeping still right now.`}
      </p>
    </div>
  );
};
