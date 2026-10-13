import { request, isDemoMode, isNotFound } from './client';
import { Profile, MissionDetail, Intention, SupportPayload, DueIntention, TonePreference } from '../types';
import { INITIAL_PROFILE, INITIAL_MISSION, INITIAL_INTENTIONS } from '../store/mockData';
import { localTodayISO } from '../lib/dates';

let localProfile = { ...INITIAL_PROFILE };
let localMission = JSON.parse(JSON.stringify(INITIAL_MISSION)) as MissionDetail;
let localIntentions = [...INITIAL_INTENTIONS];

export async function getProfile(): Promise<Profile> {
  if (isDemoMode()) {
    return { ...localProfile, today: localTodayISO() };
  }
  return request<Profile>('/me');
}

export async function patchProfile(timezone: string): Promise<Profile> {
  if (isDemoMode()) {
    localProfile.timezone = timezone;
    return { ...localProfile, today: localTodayISO() };
  }
  return request<Profile>('/me', {
    method: 'PATCH',
    body: JSON.stringify({ timezone }),
  });
}

export async function patchTone(tone_preference: TonePreference): Promise<Profile> {
  if (isDemoMode()) {
    localProfile.tone_preference = tone_preference;
    return { ...localProfile, today: localTodayISO() };
  }
  return request<Profile>('/me', {
    method: 'PATCH',
    body: JSON.stringify({ tone_preference }),
  });
}

export async function getActiveMission(): Promise<MissionDetail | null> {
  if (isDemoMode()) return localMission;
  try {
    return await request<MissionDetail>('/missions/active');
  } catch (err) {
    if (isNotFound(err)) return null;
    throw err;
  }
}

export async function getIntentions(): Promise<Intention[]> {
  if (isDemoMode()) return localIntentions.filter((i) => i.active);
  return request<Intention[]>(`/intentions?active_only=true`);
}

export async function getDueIntentions(domain?: Intention['linked_domain']): Promise<DueIntention[]> {
  if (isDemoMode()) {
    return localIntentions
      .filter((i) => i.active && (!domain || i.linked_domain === domain))
      .slice(0, 2)
      .map((intention) => ({
        intention,
        level: 'full' as const,
        reason: 'Cue is still useful — behavior is not automatic yet',
      }));
  }
  const q = domain ? `?domain=${domain}` : '';
  return request<DueIntention[]>(`/intentions/due${q}`);
}

export async function createIntention(payload: {
  linked_domain: 'habit' | 'screen_time' | 'urge' | 'study' | 'sleep';
  linked_entity_id?: string | null;
  cue: string;
  action: string;
}): Promise<Intention> {
  if (isDemoMode()) {
    const item: Intention = {
      id: `intent-${Date.now()}`,
      linked_domain: payload.linked_domain,
      linked_entity_id: payload.linked_entity_id || null,
      cue: payload.cue,
      action: payload.action,
      active: true,
      created_at: new Date().toISOString(),
    };
    localIntentions.unshift(item);
    return item;
  }
  return request<Intention>('/intentions', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getSupportResources(): Promise<SupportPayload> {
  if (isDemoMode()) {
    return {
      region: 'Universal / Regional',
      message: 'If you are in crisis, use real support — not the coaching layer.',
      resources: [
        { name: 'Crisis Text Line', contact: 'Text HOME to 741741', detail: 'Free 24/7 crisis support via SMS' },
        { name: 'National Suicide & Crisis Lifeline', contact: 'Dial 988', detail: 'Confidential phone and text hotline' },
        { name: 'Campus Support Services', contact: 'Refer to institutional directory', detail: 'Academic and mental wellbeing counseling' },
      ],
      verified_on: localTodayISO(),
    };
  }
  return request<SupportPayload>('/support/resources');
}

export async function exportAccountData(): Promise<unknown> {
  if (isDemoMode()) {
    return {
      profile: { ...localProfile, today: localTodayISO() },
      mission: localMission,
      intentions: localIntentions,
      exported_at: new Date().toISOString(),
      note: 'Demo export — switch to live mode for a full account dump',
    };
  }
  return request('/me/export');
}

export async function deleteAccount(): Promise<unknown> {
  if (isDemoMode()) {
    return { deleted: 0, note: 'Demo mode does not delete a real account' };
  }
  return request('/me', {
    method: 'DELETE',
    body: JSON.stringify({ confirm: 'DELETE MY DATA' }),
  });
}
