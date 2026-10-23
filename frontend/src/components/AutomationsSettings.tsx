import React, { useCallback, useEffect, useState } from 'react';
import { useApp } from '../context/AppContext';
import { API_BASE } from '../api/client';
import {
  MAX_ACTIVE_INGEST_TOKENS,
  createIngestToken,
  ingestUrl,
  listIngestTokens,
  revokeIngestToken,
  type IngestToken,
  type IngestTokenCreated,
} from '../api/capture';
import { errorMessage } from '../lib/format';

type Platform = 'android' | 'ios';
type Mode = 'sleep' | 'habit';

const input = 'w-full bg-surface-container-low border border-line rounded-lg px-3 py-2 font-small text-ink';
const primaryBtn = 'w-full h-10 bg-ink text-ground-chalk rounded-lg font-caption text-caption font-semibold disabled:opacity-40';

function ago(iso: string | null): string {
  if (!iso) return 'never used';
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 1) return 'used just now';
  if (mins < 60) return `used ${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `used ${hrs} hr ago`;
  return `used ${Math.round(hrs / 24)} days ago`;
}

const CopyRow: React.FC<{ label: string; value: string; onCopy: (value: string, what: string) => void }> = ({
  label,
  value,
  onCopy,
}) => (
  <div className="space-y-1">
    <span className="font-caption text-[11px] text-muted-text uppercase tracking-wider block">{label}</span>
    <div className="flex gap-2 items-start">
      <code className="flex-1 min-w-0 break-all bg-surface-container-low border border-line rounded-lg px-2.5 py-1.5 font-caption text-[12px] text-ink">
        {value}
      </code>
      <button
        type="button"
        aria-label={`Copy ${label}`}
        onClick={() => onCopy(value, label)}
        className="w-9 h-9 shrink-0 rounded-lg bg-surface-container text-ink flex items-center justify-center"
      >
        <span className="material-symbols-outlined text-[18px]">content_copy</span>
      </button>
    </div>
  </div>
);

/**
 * Phone automations. One key per automation. Two kinds:
 *   sleep key  - can add "went to bed", "woke up" (and an advanced screen-time total). Nothing else.
 *   habit key  - tied to ONE habit; can only mark that habit done for today (arrive at the gym, a Focus mode starts...).
 * Both are write-only: a key cannot read anything back. The key is shown ONCE, right after it is made, as ready-to-paste
 * URLs (the key rides in the address, so no headers and no JSON are needed). The server never shows it again.
 */
export const AutomationsSettings: React.FC = () => {
  const { demoMode, showToast, checkinView } = useApp();
  const [tokens, setTokens] = useState<IngestToken[]>([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<Mode>('sleep');
  const [habitId, setHabitId] = useState('');
  const [label, setLabel] = useState('');
  const [creating, setCreating] = useState(false);
  const [fresh, setFresh] = useState<IngestTokenCreated | null>(null);
  const [platform, setPlatform] = useState<Platform>('android');

  const habits = checkinView?.entries ?? [];
  const habitName = (id: string | null | undefined) => habits.find((h) => h.habit_id === id)?.habit_name ?? 'a habit';
  const base = (API_BASE || window.location.origin).replace(/\/$/, '');
  const active = tokens.filter((t) => !t.revoked_at);
  const atCap = active.length >= MAX_ACTIVE_INGEST_TOKENS;
  const chosenHabit = habits.find((h) => h.habit_id === habitId);

  const load = useCallback(async () => {
    if (demoMode) {
      setLoading(false);
      return;
    }
    try {
      setTokens(await listIngestTokens());
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not load your automations'));
    } finally {
      setLoading(false);
    }
  }, [demoMode, showToast]);

  useEffect(() => {
    void load();
  }, [load]);

  const copy = async (value: string, what: string) => {
    try {
      await navigator.clipboard.writeText(value);
      showToast(`${what} copied`);
    } catch {
      showToast('Could not copy. Select it and copy by hand.');
    }
  };

  const name = (mode === 'habit' ? label.trim() || (chosenHabit ? `${chosenHabit.habit_name} auto` : '') : label.trim()).slice(0, 40);
  const canCreate = !creating && !atCap && name.length > 0 && (mode === 'sleep' || habitId !== '');

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canCreate) return;
    setCreating(true);
    try {
      const made = await createIngestToken(name, mode === 'habit' ? habitId : undefined);
      setFresh(made);
      setLabel('');
      await load();
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not create the automation'));
    } finally {
      setCreating(false);
    }
  };

  const revoke = async (t: IngestToken) => {
    if (!window.confirm(`Revoke "${t.label}"? That automation stops working immediately.`)) return;
    try {
      await revokeIngestToken(t.id);
      if (fresh?.id === t.id) setFresh(null);
      showToast('Automation revoked');
      await load();
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not revoke it'));
    }
  };

  if (demoMode) {
    return <p className="pt-2 font-small text-small text-muted-text">Automations need the live backend. Turn off demo data to set them up.</p>;
  }

  const freshIsHabit = Boolean(fresh?.habit_id);

  return (
    <div className="space-y-4 pt-2">
      <p className="font-caption text-caption text-muted-text leading-relaxed">
        Let your phone do the logging. A sleep automation calls Lock’in when you go to bed and wake up. A habit automation
        marks one habit done when something happens, like arriving at the gym. Each key can only write, never read anything
        back, and you can revoke it any time.
      </p>

      {fresh && (
        <div role="alert" className="p-3 rounded-xl border border-ink bg-surface-container space-y-3">
          <p className="font-small-medium text-small-medium text-ink">
            {freshIsHabit ? `Habit automation “${fresh.label}”` : `Sleep automation “${fresh.label}”`}
          </p>
          <p className="font-caption text-caption text-muted-text">
            Copy the link{freshIsHabit ? '' : 's'} now. {freshIsHabit ? 'It contains' : 'They contain'} your key, so treat{' '}
            {freshIsHabit ? 'it' : 'them'} like a password. Shown once; if you lose {freshIsHabit ? 'it' : 'them'}, revoke this
            automation and make a new one.
          </p>
          {freshIsHabit ? (
            <CopyRow label="Link: mark habit done" value={ingestUrl(fresh.token, 'habit_done')} onCopy={(v, w) => void copy(v, w)} />
          ) : (
            <>
              <CopyRow label="Link: went to bed" value={ingestUrl(fresh.token, 'sleep_start')} onCopy={(v, w) => void copy(v, w)} />
              <CopyRow label="Link: woke up" value={ingestUrl(fresh.token, 'sleep_end')} onCopy={(v, w) => void copy(v, w)} />
            </>
          )}
          <button type="button" onClick={() => setFresh(null)} className={primaryBtn}>
            I’ve saved {freshIsHabit ? 'it' : 'them'}
          </button>
        </div>
      )}

      <form onSubmit={create} className="space-y-2">
        <div className="flex gap-2">
          {(['sleep', 'habit'] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`flex-1 h-9 rounded-lg font-caption text-caption font-semibold border ${
                mode === m ? 'bg-ink text-ground-chalk border-ink' : 'bg-surface text-ink border-line'
              }`}
            >
              {m === 'sleep' ? 'Sleep' : 'Habit done'}
            </button>
          ))}
        </div>
        {mode === 'habit' &&
          (habits.length === 0 ? (
            <p className="font-caption text-caption text-muted-text">Add a habit first, then come back to automate it.</p>
          ) : (
            <select value={habitId} onChange={(e) => setHabitId(e.target.value)} className={input} aria-label="Which habit">
              <option value="">Pick the habit this marks done</option>
              {habits.map((h) => (
                <option key={h.habit_id} value={h.habit_id}>
                  {h.habit_name}
                </option>
              ))}
            </select>
          ))}
        <input
          type="text"
          value={label}
          maxLength={40}
          onChange={(e) => setLabel(e.target.value)}
          placeholder={mode === 'sleep' ? 'Name it, e.g. Phone sleep' : chosenHabit ? `Name it (default: ${chosenHabit.habit_name} auto)` : 'Name it (optional)'}
          className={input}
        />
        <button type="submit" disabled={!canCreate} className={primaryBtn}>
          {creating ? 'Creating…' : atCap ? `Limit of ${MAX_ACTIVE_INGEST_TOKENS} reached. Revoke one first` : 'Create automation'}
        </button>
      </form>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="font-caption text-caption text-muted-text uppercase tracking-wider">Your automations</span>
          <button type="button" aria-label="Refresh" onClick={() => void load()} className="text-muted-text hover:text-ink">
            <span className="material-symbols-outlined text-[18px]">refresh</span>
          </button>
        </div>
        {loading && <p className="font-small text-muted-text">Loading…</p>}
        {!loading && tokens.length === 0 && <p className="font-small text-muted-text">None yet.</p>}
        {tokens.map((t) => (
          <div key={t.id} className="p-3 bg-surface-container-low rounded-xl border border-surface-container flex items-center gap-2">
            <div className="min-w-0 flex-1">
              <span className="font-small-medium text-ink block truncate">{t.label}</span>
              <span className="font-caption text-caption text-muted-text">
                {t.habit_id ? `Marks ${habitName(t.habit_id)} done · ` : 'Sleep · '}
                {t.revoked_at ? 'revoked' : ago(t.last_used_at)}
              </span>
            </div>
            {!t.revoked_at && (
              <button
                type="button"
                onClick={() => void revoke(t)}
                className="px-3 h-8 rounded-lg bg-error-container text-on-error-container font-caption text-caption font-semibold"
              >
                Revoke
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="space-y-3 pt-1 border-t border-surface-container">
        <span className="font-small-medium text-small-medium text-ink block pt-3">Setup guide</span>
        <div className="flex gap-2">
          {(['android', 'ios'] as const).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPlatform(p)}
              className={`flex-1 h-9 rounded-lg font-caption text-caption font-semibold border ${
                platform === p ? 'bg-ink text-ground-chalk border-ink' : 'bg-surface text-ink border-line'
              }`}
            >
              {p === 'android' ? 'Android' : 'iPhone (Shortcuts)'}
            </button>
          ))}
        </div>

        {platform === 'android' ? (
          <ol className="list-decimal pl-5 space-y-1.5 font-small text-small text-ink leading-relaxed">
            <li>Install an automation app that can send a web request: MacroDroid, Tasker, or HTTP Shortcuts.</li>
            <li>
              Make a macro. Pick the trigger: for a habit, arriving at a place, a Focus or Do Not Disturb mode starting, or the
              charger connecting; for sleep, your alarm being dismissed, plus a bedtime trigger of your choice.
            </li>
            <li>Add the action “HTTP Request” (MacroDroid), Net → HTTP Request (Tasker), or a new shortcut (HTTP Shortcuts).</li>
            <li>Paste the link you copied above. Method GET or POST both work. No headers and no body are needed.</li>
            <li>Run it once by hand. “Used just now” in the list above means it reached Lock’in.</li>
          </ol>
        ) : (
          <ol className="list-decimal pl-5 space-y-1.5 font-small text-small text-ink leading-relaxed">
            <li>Open Shortcuts, go to Automation, and make a new personal automation.</li>
            <li>
              Pick the trigger: for a habit, Arrive at a place or a Focus turning on; for sleep, the Sleep trigger (“Bedtime
              starts” / “Wake Up”; the names shift between iOS versions), or an Alarm that “Is Stopped”.
            </li>
            <li>Add the action “Get Contents of URL” and paste the link you copied above. Leave the method as it is.</li>
            <li>Turn off “Ask Before Running”, so it runs without a prompt.</li>
          </ol>
        )}

        <ul className="list-disc pl-5 space-y-1 font-caption text-caption text-muted-text leading-relaxed">
          <li>Sleep: the time defaults to “now”, events older than 36 hours are refused, and a bedtime logged after 3 pm counts toward the night that ends tomorrow morning.</li>
          <li>Habit: it never overwrites something you already logged today, and it only marks “done”. Untick it in the habit list if it fired by mistake.</li>
          <li>
            Screen time can’t be read by phone automations. The Screenshot button in the check-in is the reliable route.
          </li>
        </ul>

        <details className="rounded-xl border border-surface-container p-3">
          <summary className="font-caption text-caption font-semibold text-ink cursor-pointer">
            Advanced: send the key in a header instead of the link
          </summary>
          <div className="space-y-3 pt-3">
            <p className="font-caption text-caption text-muted-text leading-relaxed">
              For tools that prefer a header and a JSON body. The key is the same one; use the value you copied when you made it
              (Bearer plus the key). POST only.
            </p>
            <CopyRow label="URL" value={`${base}/ingest/event`} onCopy={(v, w) => void copy(v, w)} />
            <CopyRow label="Authorization header" value="Bearer <your key>" onCopy={(v, w) => void copy(v, w)} />
            <CopyRow label="Content-Type header" value="application/json" onCopy={(v, w) => void copy(v, w)} />
            <CopyRow label="Body: went to bed" value='{"kind": "sleep_start"}' onCopy={(v, w) => void copy(v, w)} />
            <CopyRow label="Body: woke up" value='{"kind": "sleep_end"}' onCopy={(v, w) => void copy(v, w)} />
            <CopyRow label="Body: habit done (habit key only)" value='{"kind": "habit_done"}' onCopy={(v, w) => void copy(v, w)} />
            <CopyRow label="Body: screen time total" value='{"kind": "screen_time", "minutes": 180}' onCopy={(v, w) => void copy(v, w)} />
          </div>
        </details>
      </div>
    </div>
  );
};
