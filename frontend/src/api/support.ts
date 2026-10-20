import { request, isDemoMode } from './client';
import { SupportPayload } from '../types';
import { localTodayISO, qs } from '../lib/dates';

/**
 * Crisis resources. Live mode asks the backend, which picks the region from the user's timezone
 * (India gets Tele-MANAS / KIRAN / 112). The demo returns a neutral, non-US payload.
 */
export async function fetchSupport(timezone?: string | null): Promise<SupportPayload> {
  if (isDemoMode()) {
    return {
      region: 'GLOBAL',
      message:
        'What you wrote sounds heavy, and it is bigger than a habit or a score. Please reach a real person now: a helpline below, or someone you trust who can be with you.',
      resources: [
        {
          name: 'Local emergency number',
          contact: 'your local emergency number',
          detail: 'If you might act on these thoughts soon, call it now.',
        },
        { name: 'Find a helpline', contact: 'findahelpline.com', detail: 'Helplines listed by country.' },
      ],
      verified_on: localTodayISO(),
    };
  }
  return request<SupportPayload>(`/support/resources${qs({ timezone: timezone || undefined })}`);
}
