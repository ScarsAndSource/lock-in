import React, { useCallback, useEffect, useState } from 'react';
import { useApp } from '../context/AppContext';
import {
  currentDeviceSubscribed, disablePush, enablePush, getNotificationPrefs, patchNotificationPrefs,
  pushSupported, sendTestPush,
} from '../api/notifications';
import type { NotificationPrefs } from '../types';
import { errorMessage } from '../lib/format';

const hhmm = (t: string) => t.slice(0, 5);
const hourLabel = (h: number) => `${h % 12 || 12}:00 ${h < 12 ? 'AM' : 'PM'}`;

export const NotificationSettings: React.FC = () => {
  const { showToast, demoMode } = useApp();
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null);
  const [subscribed, setSubscribed] = useState(false);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setPrefs(await getNotificationPrefs());
      setSubscribed(await currentDeviceSubscribed());
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not load notification settings'));
    }
  }, [showToast]);

  useEffect(() => {
    refresh();
  }, [refresh, demoMode]);

  const save = async (patch: Parameters<typeof patchNotificationPrefs>[0]) => {
    try {
      setPrefs(await patchNotificationPrefs(patch));
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not save'));
      refresh(); // snap the controls back to what the server actually has
    }
  };

  const toggleDevice = async () => {
    setBusy(true);
    try {
      if (subscribed) {
        await disablePush();
        showToast('Notifications off on this device.');
      } else {
        await enablePush();
        showToast('Notifications on for this device.');
      }
      await refresh();
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not change notifications'));
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setBusy(true);
    try {
      const n = await sendTestPush();
      showToast(n > 0 ? 'Test sent. Check your notifications.' : 'The push service did not accept it. Try turning notifications off and on.');
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Test failed'));
    } finally {
      setBusy(false);
    }
  };

  const field = 'bg-surface border border-line rounded-lg px-2.5 py-1.5 font-small text-ink';

  return (
    <section className="bg-surface rounded-xl p-4 border border-line shadow-sm space-y-4">
      <div>
        <span className="font-caption text-caption text-muted-text uppercase tracking-wider block">
          Reminders & nudges
        </span>
        <h3 className="font-section text-section text-ink">Notifications</h3>
        <p className="font-caption text-caption text-muted-text leading-relaxed">
          Nudges back off instead of piling up, small things arrive as one daily digest, and quiet hours always win.
          On iPhone, add the app to your Home Screen first.
        </p>
      </div>

      {prefs && !prefs.push_available && !demoMode && (
        <p className="font-small text-muted-text">Push isn't set up on the server yet. Your task list still works.</p>
      )}
      {!pushSupported() && <p className="font-small text-muted-text">This browser can't receive push notifications.</p>}

      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy || !pushSupported()}
          onClick={toggleDevice}
          className="flex-1 h-10 rounded-xl bg-surface-container text-ink font-body-strong disabled:opacity-40"
        >
          {subscribed ? 'Turn off on this device' : 'Turn on for this device'}
        </button>
        {subscribed && (
          <button
            type="button"
            disabled={busy}
            onClick={test}
            className="px-4 h-10 rounded-xl bg-surface-container text-ink font-body-strong disabled:opacity-40"
          >
            Test
          </button>
        )}
      </div>

      {prefs && (
        <div className="space-y-3">
          <label className="flex items-center justify-between gap-3 font-small text-ink">
            <span>Send notifications at all</span>
            <input
              type="checkbox"
              checked={prefs.push_enabled}
              onChange={(e) => save({ push_enabled: e.target.checked })}
              className="w-5 h-5"
            />
          </label>
          <label className="flex items-center justify-between gap-3 font-small text-ink">
            <span>Small things digest at</span>
            <select
              value={prefs.nudge_hour}
              onChange={(e) => save({ nudge_hour: Number(e.target.value) })}
              className={field}
            >
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>
                  {hourLabel(h)}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-center justify-between gap-3 font-small text-ink">
            <span>Quiet hours</span>
            <span className="flex items-center gap-1.5">
              <input
                type="time"
                value={hhmm(prefs.quiet_start)}
                onChange={(e) => e.target.value && save({ quiet_start: e.target.value })}
                className={field}
              />
              <span className="text-muted-text">to</span>
              <input
                type="time"
                value={hhmm(prefs.quiet_end)}
                onChange={(e) => e.target.value && save({ quiet_end: e.target.value })}
                className={field}
              />
            </span>
          </div>
          <label className="flex items-center justify-between gap-3 font-small text-ink">
            <span>Most notifications per day</span>
            <select
              value={prefs.max_per_day}
              onChange={(e) => save({ max_per_day: Number(e.target.value) })}
              className={field}
            >
              {[1, 2, 3, 4, 5, 6, 8, 10].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
    </section>
  );
};
