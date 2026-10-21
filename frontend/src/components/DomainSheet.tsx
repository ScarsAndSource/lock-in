import React from 'react';
import { useApp } from '../context/AppContext';
import { Sheet } from './Sheet';
import { TrackView } from '../views/TrackView';

/** The old Track tab, opened on demand from the Now chips or the Mirror domain tiles. */
export const DomainSheet: React.FC = () => {
  const { domainSheet, closeDomain } = useApp();
  if (!domainSheet) return null;
  return (
    <Sheet open onClose={closeDomain} title="Details" eyebrow="Log and review" tall>
      <TrackView key={domainSheet} initialDomain={domainSheet} />
    </Sheet>
  );
};
