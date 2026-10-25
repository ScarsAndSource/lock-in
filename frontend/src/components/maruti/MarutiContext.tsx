import React, { createContext, useContext } from 'react';
import { useMarutiBrain } from './useMarutiBrain';
import type { MarutiBrain } from './useMarutiBrain';

const MarutiCtx = createContext<MarutiBrain | null>(null);

/** One Maruti for the whole app: the chat tab and the on-screen sprite share the same brain. */
export const MarutiProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const brain = useMarutiBrain();
  return <MarutiCtx.Provider value={brain}>{children}</MarutiCtx.Provider>;
};

export function useMaruti(): MarutiBrain {
  const brain = useContext(MarutiCtx);
  if (!brain) throw new Error('useMaruti must be used inside MarutiProvider');
  return brain;
}
