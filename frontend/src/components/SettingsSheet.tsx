import React, { useEffect, useState } from 'react';
import { useApp } from '../context/AppContext';
import { Sheet } from './Sheet';
import { Disclosure } from './Disclosure';
import { NotificationSettings } from './NotificationSettings';
import { CalendarImport } from './CalendarImport';
import { AutomationsSettings } from './AutomationsSettings';
import { CrewPanel } from './crew/CrewPanel';
import {
  getProfile,
  patchProfile,
  patchTone,
  getIntentions,
  createIntention,
  exportAccountData,
  deleteAccount,
} from '../api/profile';
import { signOut } from '../api/auth';
import { API_BASE } from '../api/client';
import type { Domain, Intention, Profile, TonePreference } from '../types';
import { errorMessage } from '../lib/format';

const TONE_OPTIONS: { key: TonePreference; label: string; hint: string }[] = [
  { key: 'auto', label: 'Auto', hint: 'Blunt by default, gentler after a rough stretch' },
  { key: 'direct', label: 'Direct', hint: 'Always blunt' },
  { key: 'coach', label: 'Coach', hint: 'Always warmer, same facts' },
];

const isTone = (v: string | undefined): v is TonePreference => v === 'auto' || v === 'direct' || v === 'coach';

const DOMAIN_OPTIONS: { key: Domain; label: string }[] = [
  { key: 'habit', label: 'Habit' },
  { key: 'study', label: 'Study' },
  { key: 'sleep', label: 'Sleep' },
  { key: 'urge', label: 'Urge' },
  { key: 'screen_time', label: 'Screen time' },
];

const input = 'w-full bg-surface-container-low border border-line rounded-lg px-3 py-2 font-small text-ink';
const primaryBtn = 'w-full h-10 bg-ink text-ground-chalk rounded-lg font-caption text-caption font-semibold hover:bg-secondary';

export const SettingsSheet: React.FC = () => {
  const { setSettingsOpen, demoMode, toggleDemoMode, showToast } = useApp();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [intentions, setIntentions] = useState<Intention[]>([]);
  const [timezoneInput, setTimezoneInput] = useState('Asia/Kolkata');
  const [cueInput, setCueInput] = useState('');
  const [actionInput, setActionInput] = useState('');
  const [domainInput, setDomainInput] = useState<Domain>('habit');
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getProfile()
      .then((p) => {
        if (cancelled) return;
        setProfile(p);
        setTimezoneInput(p.timezone);
      })
      .catch(() => {});
    getIntentions()
      .then((list) => {
        if (!cancelled) setIntentions(list);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const close = () => setSettingsOpen(false);
  const tone: TonePreference = isTone(profile?.tone_preference) ? profile.tone_preference : 'auto';

  const handleTone = async (next: TonePreference) => {
    try {
      setProfile(await patchTone(next));
      showToast(`Tone set to ${next}`);
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not change tone'));
    }
  };

  const handleSaveTimezone = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setProfile(await patchProfile(timezoneInput));
      showToast('Timezone updated');
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Error updating timezone'));
    }
  };

  const handleCreateIntention = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cueInput.trim() || !actionInput.trim()) return;
    try {
      const created = await createIntention({
        linked_domain: domainInput,
        cue: cueInput.trim(),
        action: actionInput.trim(),
      });
      setIntentions((prev) => [created, ...prev]);
      setCueInput('');
      setActionInput('');
      showToast('If-then plan saved');
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Error saving plan'));
    }
  };

  const handleExport = async () => {
    try {
      const data = await exportAccountData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `lockin-export-${new Date().toISOString().split('T')[0]}.json`;
      a.click();
      URL.revokeObjectURL(url);
      showToast('Data exported');
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Export error'));
    }
  };

  const handleDelete = async () => {
    if (!window.confirm('Are you absolutely certain? This will wipe your account data.')) return;
    setIsDeleting(true);
    try {
      await deleteAccount();
      showToast('Data deleted.');
      window.location.reload();
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Error deleting data'));
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <Sheet open onClose={close} title="Settings" tall>
      <div className="space-y-3">
        <Disclosure title="How I talk to you" summary={TONE_OPTIONS.find((t) => t.key === tone)?.label}>
          <div className="space-y-2 pt-2">
            {TONE_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                type="button"
                onClick={() => void handleTone(opt.key)}
                className={`w-full p-3 rounded-xl text-left border transition-colors ${
                  tone === opt.key ? 'bg-ink text-ground-chalk border-ink' : 'bg-surface-container-low text-ink border-line'
                }`}
              >
                <span className="font-small-medium text-small-medium block">{opt.label}</span>
                <span className={`font-caption text-caption ${tone === opt.key ? 'text-surface-dim' : 'text-muted-text'}`}>
                  {opt.hint}
                </span>
              </button>
            ))}
          </div>
        </Disclosure>

        <Disclosure title="Notifications">
          <div className="pt-2">
            <NotificationSettings />
          </div>
        </Disclosure>

        <Disclosure title="Calendar and exams">
          <CalendarImport />
        </Disclosure>

        <Disclosure title="Automations" summary="Sleep, hands-free">
          <AutomationsSettings />
        </Disclosure>

        <Disclosure title="Crew" summary="Small groups, no rankings" defaultOpen={sessionStorage.getItem('lockin_crew') === '1'}>
          <CrewPanel />
        </Disclosure>

        <Disclosure title="If-then plans" summary={`${intentions.length} active`}>
          <div className="space-y-3 pt-2">
            <p className="font-caption text-caption text-muted-text leading-relaxed">
              A cue you will actually meet, and what you do when you meet it. Reminders fade as the behavior becomes automatic.
            </p>
            {intentions.map((intent) => (
              <div key={intent.id} className="p-3 bg-surface-container-low rounded-xl border border-surface-container space-y-1">
                <span className="font-caption text-[11px] uppercase tracking-wider px-2 py-0.5 rounded bg-surface text-ink font-semibold">
                  {intent.linked_domain.replace('_', ' ')}
                </span>
                <p className="font-small text-ink">
                  <strong>If:</strong> {intent.cue}
                </p>
                <p className="font-small text-ink">
                  <strong>Then:</strong> {intent.action}
                </p>
              </div>
            ))}
            <form onSubmit={handleCreateIntention} className="space-y-2">
              <select value={domainInput} onChange={(e) => setDomainInput(e.target.value as Domain)} className={input}>
                {DOMAIN_OPTIONS.map((d) => (
                  <option key={d.key} value={d.key}>
                    {d.label}
                  </option>
                ))}
              </select>
              <input
                type="text"
                placeholder="If… (e.g. I open YouTube while studying)"
                value={cueInput}
                onChange={(e) => setCueInput(e.target.value)}
                className={input}
              />
              <input
                type="text"
                placeholder="Then… (e.g. close the tab and stand up for 60s)"
                value={actionInput}
                onChange={(e) => setActionInput(e.target.value)}
                className={input}
              />
              <button type="submit" className={primaryBtn}>
                Save plan
              </button>
            </form>
          </div>
        </Disclosure>

        <Disclosure title="Timezone" summary={profile?.timezone}>
          <form onSubmit={handleSaveTimezone} className="space-y-2 pt-2">
            <input type="text" value={timezoneInput} onChange={(e) => setTimezoneInput(e.target.value)} className={input} />
            <button type="submit" className={primaryBtn}>
              Save timezone
            </button>
          </form>
        </Disclosure>

        <Disclosure title="Your data">
          <div className="space-y-2 pt-2">
            <p className="font-caption text-caption text-muted-text">
              Lock'in is an isolated island. No social feeds, no leaderboards.
            </p>
            <button
              type="button"
              onClick={() => void handleExport()}
              className="w-full h-10 rounded-xl bg-surface-container text-ink font-body-strong flex items-center justify-center gap-2 hover:bg-secondary-fixed transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">download</span>
              <span>Export all data (JSON)</span>
            </button>
            <button
              type="button"
              disabled={isDeleting}
              onClick={() => void handleDelete()}
              className="w-full h-10 rounded-xl bg-error-container text-on-error-container font-body-strong flex items-center justify-center gap-2 hover:opacity-90 transition-opacity disabled:opacity-60"
            >
              <span className="material-symbols-outlined text-[18px]">delete_forever</span>
              <span>Delete account and data</span>
            </button>
          </div>
        </Disclosure>

        <button
          type="button"
          onClick={() => {
            close();
            if (demoMode) toggleDemoMode(false);
            else void signOut();
          }}
          className="w-full h-11 bg-surface-container text-ink border border-line rounded-xl font-body-strong hover:bg-secondary-fixed transition-colors"
        >
          {demoMode ? 'Exit demo' : 'Sign out'}
        </button>

        {import.meta.env.DEV && (
          <div className="p-3 rounded-xl border border-dashed border-outline-variant space-y-2">
            <p className="font-caption text-caption text-muted-text">Dev only · API: {API_BASE || 'same origin'}</p>
            <button
              type="button"
              onClick={() => toggleDemoMode(!demoMode)}
              className="px-3 h-9 rounded-lg bg-surface-container text-ink font-caption text-caption font-semibold"
            >
              {demoMode ? 'Switch to live API' : 'Switch to demo data'}
            </button>
          </div>
        )}
      </div>
    </Sheet>
  );
};
