import React, { useState, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import { localTodayISO } from '../lib/dates';
import {
  getProfile,
  patchProfile,
  getIntentions,
  createIntention,
  getActiveMission,
  exportAccountData,
  deleteAccount,
} from '../api/profile';
import { Profile, Intention, MissionDetail, Domain } from '../types';
import { errorMessage } from '../lib/format';

export const MoreView: React.FC = () => {
  const { demoMode, toggleDemoMode, token, saveToken, showToast } = useApp();

  const [profile, setProfile] = useState<Profile | null>(null);
  const [intentions, setIntentions] = useState<Intention[]>([]);
  const [mission, setMission] = useState<MissionDetail | null>(null);

  // Form states
  const [timezoneInput, setTimezoneInput] = useState('Asia/Kolkata');
  const [tokenInput, setTokenInput] = useState(token || '');
  const [cueInput, setCueInput] = useState('');
  const [actionInput, setActionInput] = useState('');
  const [domainInput, setDomainInput] = useState<Domain>('habit');
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    getProfile().then((p) => {
      setProfile(p);
      setTimezoneInput(p.timezone);
    });
    getIntentions().then(setIntentions);
    getActiveMission().then(setMission);
  }, []);

  const handleSaveTimezone = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const updated = await patchProfile(timezoneInput);
      setProfile(updated);
      showToast('Timezone updated!');
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Error updating timezone'));
    }
  };

  const handleSaveToken = (e: React.FormEvent) => {
    e.preventDefault();
    saveToken(tokenInput.trim() || null);
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
      showToast('If-then pre-commitment locked!');
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Error creating intention'));
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
      showToast('Account data exported!');
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Export error'));
    }
  };

  const handleDelete = async () => {
    if (!window.confirm('Are you absolutely certain? This will wipe your account data.')) {
      return;
    }
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
    <div className="flex flex-col w-full pb-8 max-w-md mx-auto space-y-6 animate-fadeIn">
      {/* Active Mission Card */}
      {mission && (
        <section className="bg-surface rounded-xl p-4 border border-line shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <span className="font-caption text-caption text-muted-text uppercase tracking-wider block">
                Active Mission Sprint
              </span>
              <h3 className="font-title text-title text-ink text-xl font-bold">
                {mission.mission.title}
              </h3>
            </div>
            <span className="px-2.5 py-1 rounded bg-domain-study-tint text-domain-study-fill font-caption text-caption font-semibold">
              Day {mission.progress.day_number}/{mission.progress.days_total}
            </span>
          </div>

          <div className="space-y-1">
            <div className="w-full bg-surface-container rounded-full h-2 overflow-hidden">
              <div
                className="bg-ink h-full rounded-full transition-all"
                style={{ width: `${mission.progress.elapsed_pct}%` }}
              />
            </div>
            <div className="flex justify-between font-caption text-caption text-muted-text">
              <span>{mission.progress.phase}</span>
              <span>{mission.progress.days_left} days remaining</span>
            </div>
          </div>

          {mission.progress.next_checkpoint && (
            <div className="p-2.5 bg-surface-container-low rounded-lg text-small flex items-center justify-between">
              <span className="font-caption text-muted-text">Next Checkpoint:</span>
              <strong className="text-ink font-small-medium">
                {mission.progress.next_checkpoint.label} ({mission.progress.next_checkpoint.checkpoint_date})
              </strong>
            </div>
          )}
        </section>
      )}

      {/* Pre-commitments (Implementation Intentions) */}
      <section className="bg-surface rounded-xl p-4 border border-line shadow-sm space-y-4">
        <div>
          <span className="font-caption text-caption text-muted-text uppercase tracking-wider block">
            Pre-Commitments (Gollwitzer)
          </span>
          <h3 className="font-section text-section text-ink">If-Then Intentions</h3>
          <p className="font-caption text-caption text-muted-text leading-relaxed">
            Fading cue automaticity: reminders fade as behaviors become automatic.
          </p>
        </div>

        <div className="space-y-2">
          {intentions.map((intent) => (
            <div
              key={intent.id}
              className="p-3 bg-surface-container-low rounded-xl border border-surface-container space-y-1"
            >
              <div className="flex items-center justify-between">
                <span className="font-caption text-[11px] uppercase tracking-wider px-2 py-0.5 rounded bg-surface text-ink font-semibold">
                  {intent.linked_domain}
                </span>
                <span className="font-caption text-caption text-muted-text">Active</span>
              </div>
              <p className="font-small text-ink">
                <strong>IF:</strong> {intent.cue}
              </p>
              <p className="font-small text-ink">
                <strong>THEN:</strong> {intent.action}
              </p>
            </div>
          ))}
        </div>

        {/* Add intention form */}
        <form onSubmit={handleCreateIntention} className="p-3 bg-ground-chalk rounded-xl space-y-2 border border-line">
          <span className="font-small-medium text-ink block font-semibold">Add Pre-Commitment</span>
          <select
            value={domainInput}
            onChange={(e) => setDomainInput(e.target.value as Domain)}
            className="w-full bg-surface border border-line rounded-lg px-2.5 py-1.5 font-small text-ink"
          >
            <option value="habit">Habit Domain</option>
            <option value="study">Study Domain</option>
            <option value="sleep">Sleep Domain</option>
            <option value="urge">Urge Domain</option>
            <option value="screen_time">Screen Time Domain</option>
          </select>
          <input
            type="text"
            placeholder="IF (Cue, e.g. I open YouTube while studying)..."
            value={cueInput}
            onChange={(e) => setCueInput(e.target.value)}
            className="w-full bg-surface border border-line rounded-lg px-3 py-2 font-small text-ink"
          />
          <input
            type="text"
            placeholder="THEN (Action, e.g. Close tab and stand up for 60s)..."
            value={actionInput}
            onChange={(e) => setActionInput(e.target.value)}
            className="w-full bg-surface border border-line rounded-lg px-3 py-2 font-small text-ink"
          />
          <button
            type="submit"
            className="w-full h-9 bg-ink text-ground-chalk rounded-lg font-caption text-caption font-semibold hover:bg-secondary"
          >
            Lock Pre-Commitment
          </button>
        </form>
      </section>

      {/* Profile & Timezone Settings */}
      <section className="bg-surface rounded-xl p-4 border border-line shadow-sm space-y-3">
        <h3 className="font-section text-section text-ink">Profile & Rhythm</h3>
        <form onSubmit={handleSaveTimezone} className="space-y-3">
          <div>
            <label className="font-caption text-caption text-muted-text block mb-1">Timezone</label>
            <input
              type="text"
              value={timezoneInput}
              onChange={(e) => setTimezoneInput(e.target.value)}
              className="w-full bg-surface-container-low border border-line rounded-lg px-3 py-2 font-small text-ink"
            />
          </div>
          <div className="flex items-center justify-between font-caption text-caption text-muted-text">
            <span>Tone Preference:</span>
            <strong className="text-ink capitalize">{profile?.tone_preference || 'Direct'} (Locked for v1)</strong>
          </div>
          <div className="flex items-center justify-between font-caption text-caption text-muted-text">
            <span>Profile Sync Date:</span>
            <strong className="text-ink">{profile?.today || localTodayISO()}</strong>
          </div>
          <button
            type="submit"
            className="w-full h-9 bg-ink text-ground-chalk rounded-lg font-caption text-caption font-semibold hover:bg-secondary"
          >
            Update Profile
          </button>
        </form>
      </section>

      {/* Backend API & Auth Configuration */}
      <section className="bg-surface rounded-xl p-4 border border-line shadow-sm space-y-3">
        <h3 className="font-section text-section text-ink">API & Backend Connectivity</h3>
        <div className="flex items-center justify-between p-3 bg-surface-container rounded-lg">
          <div>
            <span className="font-small-medium text-ink block font-semibold">Active Mode</span>
            <span className="font-caption text-caption text-muted-text">
              {demoMode ? 'Local Demo & Mock Data' : 'Live FastAPI Backend (http://localhost:8000)'}
            </span>
          </div>
          <button
            type="button"
            onClick={() => toggleDemoMode(!demoMode)}
            className="px-3 py-1.5 rounded-lg font-caption text-caption font-semibold bg-ink text-ground-chalk hover:bg-secondary transition-colors"
          >
            {demoMode ? 'Switch to Live' : 'Switch to Demo'}
          </button>
        </div>

        <form onSubmit={handleSaveToken} className="space-y-2 pt-1">
          <label className="font-caption text-caption text-muted-text block">
            Supabase Bearer Token (Optional for live authenticated requests)
          </label>
          <input
            type="password"
            placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6..."
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            className="w-full bg-surface-container-low border border-line rounded-lg px-3 py-2 font-small text-ink"
          />
          <button
            type="submit"
            className="w-full h-9 bg-surface-container text-ink border border-line rounded-lg font-caption text-caption font-semibold hover:bg-secondary-fixed transition-colors"
          >
            Save Token
          </button>
        </form>
      </section>

      {/* Privacy, Export, and Delete */}
      <section className="bg-surface rounded-xl p-4 border border-line shadow-sm space-y-3">
        <h3 className="font-section text-section text-ink">Privacy & Data Control</h3>
        <p className="font-caption text-caption text-muted-text">
          Lock'in is explicitly an isolated island. No social feeds, no public leaderboards.
        </p>
        <button
          type="button"
          onClick={handleExport}
          className="w-full h-10 rounded-xl bg-surface-container text-ink font-body-strong flex items-center justify-center gap-2 hover:bg-secondary-fixed transition-colors"
        >
          <span className="material-symbols-outlined text-[18px]">download</span>
          <span>Export All Data (JSON)</span>
        </button>
        <button
          type="button"
          disabled={isDeleting}
          onClick={handleDelete}
          className="w-full h-10 rounded-xl bg-error-container text-on-error-container font-body-strong flex items-center justify-center gap-2 hover:opacity-90 transition-opacity"
        >
          <span className="material-symbols-outlined text-[18px]">delete_forever</span>
          <span>Delete Account & Data</span>
        </button>
      </section>
    </div>
  );
};
