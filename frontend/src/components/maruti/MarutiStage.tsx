import React from 'react';
import { BUDDY_NAME } from '../Buddy';
import { MarutiSprite } from './MarutiSprite';
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
 * Empty chat: Maruti on the hillside, strolling, hovering, joking and rolling with laughter. Tap him.
 * While the roaming overlay is him (flying, eavesdropping, standing guard) this sprite hides and its bubble moves with him.
 */
export const MarutiHero: React.FC<{ brain: MarutiBrain }> = ({ brain }) => (
  <div className="space-y-2">
    <div className="relative w-full overflow-hidden rounded-2xl border border-line" style={{ aspectRatio: '1024 / 559' }}>
      <img src="/buddy/maruti-stage.webp" alt="" className="absolute inset-0 w-full h-full object-cover" draggable={false} />
      <div
        className="absolute"
        style={{
          left: '34.375%', top: '8.587%', width: '34.57%', height: '81.22%',
          transform: `translate(${brain.x * 100}%, ${brain.y * 100}%)`, transition: `transform ${brain.walkMs}ms ease-in-out`,
        }}
      >
        <MarutiSprite
          home
          mood={shownMood(brain)}
          flip={brain.flip}
          onTap={brain.poke}
          className={brain.away ? 'invisible' : ''}
        />
      </div>
      {brain.bubble && !brain.away && <Bubble text={brain.bubble} className="absolute left-2 top-2 max-w-[40%]" />}
      <MarutiControls brain={brain} className="absolute right-2 top-2" />
    </div>
    <p className="font-section text-section text-ink">Hey, I’m {BUDDY_NAME}.</p>
  </div>
);

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
