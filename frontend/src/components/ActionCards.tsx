import React, { useState } from 'react';
import type { ActionCard } from '../types';
import { confirmAction, undoAction } from '../api/chat';
import { useApp } from '../context/AppContext';
import { errorMessage } from '../lib/format';

type Local = { card: ActionCard; undone?: boolean; dismissed?: boolean; busy?: boolean };

/**
 * What the Companion did with a message. Applied writes show "Logged. Undo"; ambiguous ones wait for one tap.
 * Self-contained: it owns the per-card state, so the chat only renders <ActionCards cards={message.actions} />.
 * Cards exist for the live reply only (undo payloads and pending args are deliberately not stored).
 */
export const ActionCards: React.FC<{ cards?: ActionCard[] }> = ({ cards }) => {
  const { showToast } = useApp();
  const [items, setItems] = useState<Local[]>(() => (cards ?? []).map((card) => ({ card })));
  if (items.length === 0) return null;

  const patch = (id: string, change: Partial<Local>) =>
    setItems((prev) => prev.map((i) => (i.card.id === id ? { ...i, ...change } : i)));

  const confirm = async (card: ActionCard) => {
    patch(card.id, { busy: true });
    try {
      patch(card.id, { card: await confirmAction(card), busy: false });
    } catch (err: unknown) {
      patch(card.id, { busy: false });
      showToast(errorMessage(err, 'Could not apply that'));
    }
  };

  const undo = async (card: ActionCard) => {
    patch(card.id, { busy: true });
    try {
      await undoAction(card);
      patch(card.id, { undone: true, busy: false });
    } catch (err: unknown) {
      patch(card.id, { busy: false });
      showToast(errorMessage(err, 'Could not undo that'));
    }
  };

  const btn = 'px-2.5 py-1 rounded-lg font-caption text-caption font-semibold disabled:opacity-40';
  return (
    <div className="space-y-1.5 pt-1" aria-live="polite">
      {items.map(({ card, undone, dismissed, busy }) => {
        if (dismissed) return null;
        const failed = card.status === 'failed';
        return (
          <div
            key={card.id}
            className="flex items-center justify-between gap-2 rounded-lg border border-line bg-surface-container-low px-2.5 py-1.5"
          >
            <span className={`font-caption text-caption text-ink ${undone ? 'line-through opacity-60' : ''}`}>
              {card.status === 'applied' ? (undone ? '↩ ' : '✓ ') : failed ? '✗ ' : '? '}
              {card.summary}
              {failed && card.reason ? ` — ${card.reason}` : ''}
              {card.status === 'pending' && card.reason ? ` — ${card.reason}` : ''}
            </span>
            {card.status === 'applied' && !undone && card.undo && (
              <button type="button" disabled={busy} onClick={() => undo(card)} className={`${btn} bg-surface text-ink`}>
                Undo
              </button>
            )}
            {card.status === 'pending' && (
              <span className="flex gap-1.5 shrink-0">
                <button type="button" disabled={busy} onClick={() => confirm(card)} className={`${btn} bg-ink text-ground-chalk`}>
                  Save
                </button>
                <button type="button" disabled={busy} onClick={() => patch(card.id, { dismissed: true })} className={`${btn} bg-surface text-ink`}>
                  Skip
                </button>
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
};
