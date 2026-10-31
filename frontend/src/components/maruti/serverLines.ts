import { ApiError } from '../../api/client';
import { pick } from './lines';

/**
 * What Maruti says when the server pushes back on a chat message (busy, slow down, out of AI for today, overloaded),
 * instead of a red error toast. These are normal, expected answers, not failures: he says it in his own voice, the
 * draft goes back into the box, and nothing is lost. Anything else (a real error) returns null and keeps the toast.
 */
export interface ServerLine {
  text: string;
  /** Put the person's text back in the input so they can send it again. */
  keepDraft: boolean;
}

const BUSY: readonly string[] = ['Ruk ruk, pehla sawaal abhi soch raha hoon.', 'Ek minute, pehle wala jawab aa jaye.'];
const SLOW: readonly string[] = ['Thoda dheere, bhai. Thodi der mein phir puchh.', 'Saans le le, thodi der ruk ke bhej.'];
const QUOTA: readonly string[] = [
  'Aaj ka AI quota khatam. Kal subah phir milte hain, tracker chalta rahega.',
  'Aaj ke jawab ho gaye. Logs aur tracker ab bhi kaam kar rahe hain.',
];
const HEAVY: readonly string[] = ['Abhi thoda bhaari chal raha hai. Ek pal mein phir bhej.', 'Line pe bheed hai. Thodi der baad phir try kar.'];

export function marutiLineFor(err: unknown): ServerLine | null {
  if (!(err instanceof ApiError)) return null;
  if (err.status === 409) return { text: pick(BUSY), keepDraft: true };
  if (err.status === 429) {
    if (/allowance/i.test(err.message)) return { text: pick(QUOTA), keepDraft: true };
    const wait = err.retryAfter;
    const text = pick(SLOW);
    return { text: wait !== undefined && wait <= 90 ? `${text} (${wait}s)` : text, keepDraft: true };
  }
  if (err.status === 503) return { text: pick(HEAVY), keepDraft: true };
  return null;
}
