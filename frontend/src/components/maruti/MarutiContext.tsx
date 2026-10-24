import React, { createContext, useContext } from 'react';
import { useMarutiBrain } from './useMarutiBrain';
import type { MarutiBrain } from './useMarutiBrain';

const MarutiCtx = createContext<MarutiBrain | null>(null);

/** One Maruti for the whole app: the chat tab and the roaming overlay share the same brain. */
export const MarutiProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // The hillside world (MarutiWorld) moves him now, so the brain's own wandering stays off.
  const brain = useMarutiBrain(false);
  return <MarutiCtx.Provider value={brain}>{children}</MarutiCtx.Provider>;
};

export function useMaruti(): MarutiBrain {
  const brain = useContext(MarutiCtx);
  if (!brain) throw new Error('useMaruti must be used inside MarutiProvider');
  return brain;
}
