import React, { useEffect, useState } from 'react';
import { getIdentity } from '../../api/growth';
import type { GrowthIdentity } from '../../api/growth';

/** One quiet line under the weekly review narrative. Renders nothing until the person has written their sentence. */
export const IdentityVote: React.FC<{ weekStart: string }> = ({ weekStart }) => {
  const [identity, setIdentity] = useState<GrowthIdentity | null>(null);

  useEffect(() => {
    let cancelled = false;
    getIdentity(weekStart)
      .then((i) => {
        if (!cancelled) setIdentity(i);
      })
      .catch(() => {
        if (!cancelled) setIdentity(null);
      });
    return () => {
      cancelled = true;
    };
  }, [weekStart]);

  if (!identity) return null;

  return (
    <p className="font-small text-small text-muted-text leading-relaxed">
      “{identity.sentence}” Each check-in is a vote for that person.{' '}
      {identity.votes > 0 ? `You cast ${identity.votes} this week.` : 'None this week, and the next one still counts.'}
    </p>
  );
};
