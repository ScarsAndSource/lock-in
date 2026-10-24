import React from 'react';
import { BUDDY_NAME } from '../Buddy';
import type { MarutiMood } from './useMarutiBrain';
import './maruti.css';

const layer = (name: string) => `/buddy/m-${name}.png`;

interface MarutiSpriteProps {
  mood: MarutiMood;
  flip?: boolean;
  onTap?: () => void;
  className?: string;
}

/**
 * Maruti on his cloud, built from separate pixel layers so the gada arm, tail, eyes and mouth move on their own.
 * Draw order: cloud, tail, body, gada arm, then the blink / happy-eyes / open-mouth overlays.
 */
export const MarutiSprite: React.FC<MarutiSpriteProps> = ({ mood, flip = false, onTap, className = '' }) => (
  <button
    type="button"
    onClick={onTap}
    aria-label={`${BUDDY_NAME}. Tap to say hi`}
    className={`mr m-${mood} ${flip ? 'mr-flip' : ''} ${className}`}
  >
    <span className="mr-float">
      <img className="mr-layer mr-cloud" src={layer('cloud')} alt="" draggable={false} />
      <img className="mr-layer mr-tail" src={layer('tail')} alt="" draggable={false} />
      <img className="mr-layer mr-body" src={layer('body')} alt="" draggable={false} />
      <img className="mr-layer mr-arm" src={layer('arm')} alt="" draggable={false} />
      <img className="mr-layer mr-eyes-closed" src={layer('eyes-closed')} alt="" draggable={false} />
      <img className="mr-layer mr-eyes-happy" src={layer('eyes-happy')} alt="" draggable={false} />
      <img className="mr-layer mr-mouth" src={layer('mouth-open')} alt="" draggable={false} />
    </span>
  </button>
);
