import { request, isDemoMode } from './client';
import type { NotificationPrefs } from '../types';

const DEMO_PREFS: NotificationPrefs = {
  push_enabled: true,
  quiet_start: '22:00:00',
  quiet_end: '08:00:00',
  nudge_hour: 18,
  max_per_day: 4,
  devices: 0,
  push_available: false,
  companion_enabled: true,
  checkin_hour: 21,
  plan_cues_in_quiet: false,
  discreet_push: true,
};
let demoPrefs: NotificationPrefs = { ...DEMO_PREFS };

export async function getNotificationPrefs(): Promise<NotificationPrefs> {
  if (isDemoMode()) return demoPrefs;
  return request<NotificationPrefs>('/notifications/prefs');
}

export interface NotificationPrefsPatch {
  push_enabled?: boolean;
  quiet_start?: string; // "HH:MM"
  quiet_end?: string;
  nudge_hour?: number;
  max_per_day?: number;
  companion_enabled?: boolean;
  checkin_hour?: number;
  plan_cues_in_quiet?: boolean;
  discreet_push?: boolean;
}

export async function patchNotificationPrefs(patch: NotificationPrefsPatch): Promise<NotificationPrefs> {
  if (isDemoMode()) {
    demoPrefs = {
      ...demoPrefs,
      ...patch,
      quiet_start: patch.quiet_start ? `${patch.quiet_start}:00` : demoPrefs.quiet_start,
      quiet_end: patch.quiet_end ? `${patch.quiet_end}:00` : demoPrefs.quiet_end,
    };
    return demoPrefs;
  }
  return request<NotificationPrefs>('/notifications/prefs', { method: 'PATCH', body: JSON.stringify(patch) });
}

// ---------------------------------------------------------------- web push
export function pushSupported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

function keyToBytes(base64Url: string): Uint8Array {
  const pad = '='.repeat((4 - (base64Url.length % 4)) % 4);
  const raw = atob((base64Url + pad).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

function sameKey(a: ArrayBuffer | null, b: Uint8Array): boolean {
  if (!a) return false;
  const x = new Uint8Array(a);
  return x.length === b.length && x.every((v, i) => v === b[i]);
}

/** Only resolves when a service worker is actually active (it is only registered in the production build). */
async function readyRegistration(): Promise<ServiceWorkerRegistration> {
  const timeout = new Promise<never>((_, reject) =>
    window.setTimeout(
      () => reject(new Error('Notifications need the installed app (production build). The service worker is not active here.')),
      4000
    )
  );
  return Promise.race([navigator.serviceWorker.ready, timeout]);
}

export async function currentDeviceSubscribed(): Promise<boolean> {
  if (!pushSupported()) return false;
  try {
    const reg = await navigator.serviceWorker.getRegistration();
    return Boolean(reg && (await reg.pushManager.getSubscription()));
  } catch {
    return false;
  }
}

export async function enablePush(): Promise<void> {
  if (isDemoMode()) throw new Error('Notifications need the live backend. Turn off demo mode first.');
  if (!pushSupported()) throw new Error('This browser does not support push notifications.');
  const { public_key } = await request<{ public_key: string | null }>('/notifications/vapid-key');
  if (!public_key) throw new Error('Push is not set up on the server yet.');

  const permission = await Notification.requestPermission();
  if (permission !== 'granted') throw new Error('Notification permission was not granted.');

  const reg = await readyRegistration();
  const serverKey = keyToBytes(public_key);
  let sub = await reg.pushManager.getSubscription();
  if (sub && !sameKey(sub.options.applicationServerKey, serverKey)) {
    await sub.unsubscribe(); // server keys were rotated: the old subscription can never receive anything
    sub = null;
  }
  if (!sub) {
    sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: serverKey.buffer as ArrayBuffer });
  }
  const json = sub.toJSON();
  await request<void>('/notifications/subscription', {
    method: 'PUT',
    body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }),
  });
}

export async function disablePush(): Promise<void> {
  if (!pushSupported()) return;
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = reg ? await reg.pushManager.getSubscription() : null;
  if (!sub) return;
  if (!isDemoMode()) {
    await request<void>('/notifications/subscription', {
      method: 'DELETE',
      body: JSON.stringify({ endpoint: sub.endpoint }),
    });
  }
  await sub.unsubscribe();
}

export async function sendTestPush(): Promise<number> {
  const res = await request<{ delivered: number }>('/notifications/test', { method: 'POST' });
  return res.delivered;
}
