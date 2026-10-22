import React, { useCallback, useEffect, useState } from 'react';
import { useApp } from '../context/AppContext';
import { API_BASE } from '../api/client';
import {
  MAX_ACTIVE_INGEST_TOKENS,
  createIngestToken,
  listIngestTokens,
  revokeIngestToken,
  type IngestToken,
  type IngestTokenCreated,
} from '../api/capture';
import { errorMessage } from '../lib/format';

type Platform = 'ios' | 'android';

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
 * Passive capture setup. One token per phone automation (write-only: it can add sleep and screen-time events and
 * nothing else). The token is shown ONCE, right after it is made; the server never stores or returns it again.
 * Mounted inside Settings.
 */
export const AutomationsSettings: React.FC = () => {
  const { demoMode, showToast } = useApp();
  const [tokens, setTokens] = useState<IngestToken[]>([]);
  const [loading, setLoading] = useState(true);
  const [label, setLabel] = useState('');
  const [creating, setCreating] = useState(false);
  const [fresh, setFresh] = useState<IngestTokenCreated | null>(null);
  const [platform, setPlatform] = useState<Platform>('ios');

  const endpoint = `${API_BASE || window.location.origin}/ingest/event`;
  const active = tokens.filter((t) => !t.revoked_at);
  const atCap = active.length >= MAX_ACTIVE_INGEST_TOKENS;

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

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = label.trim();
    if (!name || creating) return;
    setCreating(true);
    try {
      const made = await createIngestToken(name);
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

  const bearer = `Bearer ${fresh ? fresh.token : '<your token>'}`;
  const bodies = [
    { what: 'Went to bed', json: '{"kind": "sleep_start"}' },
    { what: 'Woke up', json: '{"kind": "sleep_end"}' },
    { what: 'Screen time total (advanced)', json: '{"kind": "screen_time", "minutes": 180}' },
  ];

  return (
    <div className="space-y-4 pt-2">
      <p className="font-caption text-caption text-muted-text leading-relaxed">
        Let your phone log sleep for you. An automation on your phone calls Lock’in when you go to bed and when you wake up.
        Each automation gets its own key that can only add sleep and screen-time events. It cannot read anything back.
      </p>

      {fresh && (
        <div role="alert" className="p-3 rounded-xl border border-ink bg-surface-container space-y-2">
          <p className="font-small-medium text-small-medium text-ink">Key for “{fresh.label}”</p>
          <p className="font-caption text-caption text-muted-text">
            Copy it now. It is shown once and cannot be recovered. If you lose it, revoke it and make a new one.
          </p>
          <CopyRow label="Key" value={fresh.token} onCopy={(v, w) => void copy(v, w)} />
          <button type="button" onClick={() => setFresh(null)} className={primaryBtn}>
            I’ve saved it
          </button>
        </div>
      )}

      <form onSubmit={create} className="space-y-2">
        <input
          type="text"
          value={label}
          maxLength={40}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Name it, e.g. iPhone wake-up"
          className={input}
        />
        <button type="submit" disabled={creating || !label.trim() || atCap} className={primaryBtn}>
          {creating ? 'Creating…' : atCap ? `Limit of ${MAX_ACTIVE_INGEST_TOKENS} reached. Revoke one first` : 'Create automation key'}
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
              <span className="font-caption text-caption text-muted-text">{t.revoked_at ? 'revoked' : ago(t.last_used_at)}</span>
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
          {(['ios', 'android'] as const).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPlatform(p)}
              className={`flex-1 h-9 rounded-lg font-caption text-caption font-semibold border ${
                platform === p ? 'bg-ink text-ground-chalk border-ink' : 'bg-surface text-ink border-line'
              }`}
            >
              {p === 'ios' ? 'iPhone (Shortcuts)' : 'Android (Tasker / MacroDroid)'}
            </button>
          ))}
        </div>

        {platform === 'ios' ? (
          <ol className="list-decimal pl-5 space-y-1.5 font-small text-small text-ink leading-relaxed">
            <li>Open Shortcuts, go to Automation, and make a new personal automation.</li>
            <li>
              Pick the Sleep trigger: “Bedtime starts” for going to bed, “Wake Up” for waking (names shift a little between iOS
              versions). An Alarm trigger set to “Is Stopped” also works for waking.
            </li>
            <li>Add the action “Get Contents of URL”, open Show More, and set the method to POST.</li>
            <li>Add two headers: Authorization and Content-Type, with the values below.</li>
            <li>Set Request Body to JSON, add a Text field named kind, and give it the value for that automation.</li>
            <li>Turn off “Ask Before Running”, so it runs without a prompt.</li>
          </ol>
        ) : (
          <ol className="list-decimal pl-5 space-y-1.5 font-small text-small text-ink leading-relaxed">
            <li>Make a macro or profile. For waking: alarm dismissed. For bed: your own trigger, such as a bedtime schedule or the phone charging after your usual hour.</li>
            <li>Add the action “HTTP Request” (MacroDroid) or Net → HTTP Request (Tasker).</li>
            <li>Method POST, with the URL below.</li>
            <li>Add the Authorization and Content-Type headers below.</li>
            <li>Set the body to the JSON for that automation, content type application/json.</li>
          </ol>
        )}

        <CopyRow label="URL" value={endpoint} onCopy={(v, w) => void copy(v, w)} />
        <CopyRow label="Authorization header" value={bearer} onCopy={(v, w) => void copy(v, w)} />
        <CopyRow label="Content-Type header" value="application/json" onCopy={(v, w) => void copy(v, w)} />
        {bodies.map((b) => (
          <CopyRow key={b.what} label={`Body: ${b.what}`} value={b.json} onCopy={(v, w) => void copy(v, w)} />
        ))}

        <ul className="list-disc pl-5 space-y-1 font-caption text-caption text-muted-text leading-relaxed">
          <li>The time defaults to “now”. Events older than 36 hours are refused.</li>
          <li>A bedtime logged after 3 pm counts toward the night that ends tomorrow morning.</li>
          <li>Run the automation once by hand. “Used just now” above confirms it reached Lock’in.</li>
          <li>
            Shortcuts has no action that reads your Screen Time total, and most Android automation apps cannot read Digital
            Wellbeing either. For screen time, the Screenshot button in the check-in is the reliable route; treat the
            screen_time event as advanced.
          </li>
        </ul>
      </div>
    </div>
  );
};
