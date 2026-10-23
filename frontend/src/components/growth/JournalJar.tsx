import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useApp } from '../../context/AppContext';
import { STICKERS, getJournal, putJournal } from '../../api/growth';
import type { JournalEntry } from '../../api/growth';
import type { SupportPayload } from '../../types';
import { SupportCard } from '../SupportCard';
import { formatDayShort, localTodayISO } from '../../lib/dates';
import { errorMessage } from '../../lib/format';
import { CLS } from './ui';

const PROMPTS = [
  'One tiny thing that went okay?',
  'What made you smile, even a little?',
  'A small win nobody saw?',
  'Something about today worth keeping?',
  'One word for today, and why?',
  'What would past-you be proud of?',
  'A kind thing you gave or got?',
  'What would you tell yesterday-you?',
];

export const JournalJar: React.FC = () => {
  const { showToast } = useApp();
  const today = localTodayISO();
  const prompt = useMemo(() => PROMPTS[Math.floor(Date.now() / 86_400_000) % PROMPTS.length], []);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [text, setText] = useState('');
  const [sticker, setSticker] = useState<string | null>(null);
  const [initial, setInitial] = useState({ text: '', sticker: null as string | null });
  const [busy, setBusy] = useState(false);
  const [support, setSupport] = useState<SupportPayload | null>(null);

  const load = useCallback(() => {
    getJournal(14)
      .then((list) => {
        setEntries(list);
        const mine = list.find((e) => e.entry_date === today);
        setText(mine?.text ?? '');
        setSticker(mine?.sticker ?? null);
        setInitial({ text: mine?.text ?? '', sticker: mine?.sticker ?? null });
      })
      .catch(() => setEntries([]));
  }, [today]);

  useEffect(() => {
    load();
  }, [load]);

  const changed = text !== initial.text || sticker !== initial.sticker;

  const save = async () => {
    setBusy(true);
    try {
      const res = await putJournal(today, { text, sticker });
      setSupport(res.support ?? null);
      showToast('Tucked into the jar 🫙');
      load();
    } catch (err) {
      showToast(errorMessage(err, 'Could not save that'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="font-body-strong text-body-strong text-ink">{prompt}</p>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Sticker for today">
        {STICKERS.map((s) => (
          <button
            key={s}
            type="button"
            aria-pressed={sticker === s}
            onClick={() => setSticker(sticker === s ? null : s)}
            className={`w-10 h-10 rounded-xl border text-xl flex items-center justify-center transition-colors ${
              sticker === s ? 'bg-ink border-ink' : 'bg-surface border-line'
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      <textarea
        className={CLS.area}
        rows={3}
        value={text}
        maxLength={Math.max(280, initial.text.length)}
        onChange={(e) => setText(e.target.value)}
        placeholder="Optional. Skipping is fine."
      />

      <button type="button" className={`${CLS.primary} w-full`} disabled={busy || !changed} onClick={() => void save()}>
        {busy ? 'Saving…' : 'Add to the jar'}
      </button>

      {support && <SupportCard support={support} />}

      {entries.length > 0 && (
        <ul className="space-y-2 pt-1">
          {entries.map((e) => (
            <li key={e.entry_date} className="flex gap-3 items-start">
              <span className="text-xl w-7 text-center shrink-0">{e.sticker ?? '·'}</span>
              <span className="min-w-0">
                <span className={`${CLS.label} mb-0.5`}>{formatDayShort(e.entry_date)}</span>
                <span className="font-small text-small text-ink whitespace-pre-wrap break-words block">{e.text}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
