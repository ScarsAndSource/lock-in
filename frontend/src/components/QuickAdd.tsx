import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { captureTasks } from '../api/tasks';
import { SupportCard } from './SupportCard';
import type { SupportPayload } from '../types';
import { errorMessage } from '../lib/format';

interface QuickAddProps {
  onAdded: () => Promise<void>;
}

/** One quiet row until it is needed. Same AI capture as before: tasks, reminders, things you keep forgetting. */
export const QuickAdd: React.FC<QuickAddProps> = ({ onAdded }) => {
  const { showToast } = useApp();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [support, setSupport] = useState<SupportPayload | null>(null);

  const submit = async () => {
    const value = text.trim();
    if (!value || sending) return;
    setSending(true);
    setSupport(null);
    try {
      const res = await captureTasks(value);
      if (res.mode === 'support') {
        setSupport(res.support);
        return; // nothing was saved; keep the text so it isn't lost
      }
      setText('');
      const n = res.tasks.length;
      const dup = res.skipped_duplicates ? ` (${res.skipped_duplicates} already on your list)` : '';
      if (n === 0) showToast(res.skipped_duplicates ? 'Already on your list.' : 'No task found in that.');
      else if (res.mode === 'fallback') showToast(`Saved ${n} as written. AI was unavailable, so set times yourself.${dup}`);
      else showToast(`Added ${n} task${n === 1 ? '' : 's'}.${dup}`);
      setOpen(false);
      await onAdded();
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not add tasks'));
    } finally {
      setSending(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="w-full h-12 px-4 bg-surface border border-dashed border-outline-variant rounded-xl flex items-center gap-2 text-muted-text hover:text-ink hover:border-outline transition-colors"
      >
        <span className="material-symbols-outlined text-[20px]">add</span>
        <span className="font-small text-small">Add a task or reminder</span>
      </button>
    );
  }

  return (
    <section className="w-full bg-surface rounded-xl p-3 border border-line space-y-2">
      <textarea
        autoFocus
        rows={2}
        value={text}
        maxLength={1000}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void submit();
        }}
        placeholder="In your own words: tasks, reminders, things you keep forgetting…"
        className="w-full bg-surface-container-low border border-line rounded-lg px-3 py-2 font-small text-ink resize-none"
      />
      <div className="flex gap-2">
        <button
          type="button"
          disabled={sending || !text.trim()}
          onClick={() => void submit()}
          className="flex-1 h-10 rounded-xl bg-ink text-ground-chalk font-body-strong disabled:opacity-40"
        >
          {sending ? 'Sorting…' : 'Add'}
        </button>
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setSupport(null);
          }}
          className="px-4 h-10 rounded-xl bg-surface-container text-ink font-caption text-caption font-semibold"
        >
          Cancel
        </button>
      </div>
      {support && <SupportCard support={support} />}
    </section>
  );
};
