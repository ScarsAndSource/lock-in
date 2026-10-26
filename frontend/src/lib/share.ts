import { idbDelete, idbGet } from './idb';

/** What the service worker stored after an Android share (public/sw.js writes this record under id "pending"). */
export interface PendingShare {
  id: 'pending';
  at: number;
  text: string;
  file: File | null;
}

const MAX_AGE_MS = 24 * 60 * 60 * 1000;

export async function readPendingShare(): Promise<PendingShare | null> {
  try {
    const share = await idbGet<PendingShare>('share', 'pending');
    if (!share) return null;
    if (Date.now() - share.at > MAX_AGE_MS || (!share.text && !share.file)) {
      await idbDelete('share', 'pending');
      return null;
    }
    return share;
  } catch {
    return null;
  }
}

export async function clearPendingShare(): Promise<void> {
  try {
    await idbDelete('share', 'pending');
  } catch {
    /* best effort */
  }
}
