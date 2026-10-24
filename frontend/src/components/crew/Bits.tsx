import React, { useState } from 'react';
import { btn, input } from './ui';

interface OneLineProps {
  placeholder: string;
  action: string;
  busy: boolean;
  maxLength?: number;
  normalize?: (value: string) => string;
  /** Returns a message while the value is not acceptable. Shown under the field, and the button stays off. */
  validate?: (value: string) => string | null;
  /** Return false to keep the typed text (the request failed); anything else clears the field. */
  onSubmit: (value: string) => Promise<boolean | void> | boolean | void;
}

/** One field and one button. Enter submits, and the text is only cleared when the request worked. */
export const OneLine: React.FC<OneLineProps> = ({ placeholder, action, busy, maxLength = 40, normalize, validate, onSubmit }) => {
  const [value, setValue] = useState('');
  const [sending, setSending] = useState(false);
  const clean = (normalize ?? ((v: string) => v.trim()))(value);
  const problem = clean && validate ? validate(clean) : null;

  const go = async () => {
    if (!clean || problem || busy || sending) return;
    setSending(true);
    try {
      const ok = await onSubmit(clean);
      if (ok !== false) setValue('');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-1">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void go();
        }}
      >
        <input
          className={input}
          value={value}
          maxLength={maxLength}
          placeholder={placeholder}
          aria-label={placeholder}
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          onChange={(e) => setValue(e.target.value)}
        />
        <button type="submit" disabled={busy || sending || !clean || !!problem} className={btn}>
          {action}
        </button>
      </form>
      {problem && <p className="font-caption text-[11px] text-error">{problem}</p>}
    </div>
  );
};

/** Seven days, Monday first. A filled dot is a day showed up. Empty days are quiet dots, never a zero or a cross. */
export const Dots: React.FC<{ marks: number }> = ({ marks }) => {
  const days = Array.from({ length: 7 }, (_, i) => (marks >> i) & 1);
  const n = days.reduce<number>((a, b) => a + b, 0);
  return (
    <span role="img" aria-label={`Showed up on ${n} ${n === 1 ? 'day' : 'days'}`} className="tracking-[0.35em] text-ink select-none">
      {days.map((d) => (d ? '◉' : '·')).join('')}
    </span>
  );
};

/** A pill that opens exactly one panel at a time. */
export const Chip: React.FC<{ on: boolean; dot?: boolean; onClick: () => void; children: React.ReactNode }> = ({ on, dot, onClick, children }) => (
  <button
    type="button"
    aria-pressed={on}
    onClick={onClick}
    className={`relative h-9 px-3 rounded-full border font-caption text-caption transition-colors ${
      on ? 'bg-ink text-ground-chalk border-ink' : 'bg-surface text-ink border-line hover:bg-surface-container-low'
    }`}
  >
    {children}
    {dot && !on && <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-domain-habits-fill" aria-hidden="true" />}
  </button>
);
