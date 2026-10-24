import React from 'react';

/** The companion's name. Change it here and it changes everywhere (chat, nav, placeholders). */
export const BUDDY_NAME = 'Maruti';
const FACE = '/buddy/buddy-face.png';

/** Round pixel-art face used next to every companion message and in the nav. */
export const BuddyAvatar: React.FC<{ size?: number; bounce?: boolean; className?: string }> = ({
  size = 32,
  bounce = false,
  className = '',
}) => (
  <img
    src={FACE}
    alt={BUDDY_NAME}
    width={size}
    height={size}
    style={{ imageRendering: 'pixelated', width: size, height: size }}
    className={`rounded-full border border-line bg-surface shrink-0 object-cover ${bounce ? 'animate-bounce' : ''} ${className}`}
    draggable={false}
  />
);
