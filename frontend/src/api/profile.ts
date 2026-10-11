import { request, isDemoMode } from './client';
import { Profile, MissionDetail, Intention, SupportPayload } from '../types';
import { INITIAL_PROFILE, INITIAL_MISSION, INITIAL_INTENTIONS } from '../store/mockData';

let localProfile = { ...INITIAL_PROFILE };
let localMission = JSON.parse(JSON.stringify(INITIAL_MISSION)) as MissionDetail;
let localIntentions = [...INITIAL_INTENTIONS];

export async function getProfile(): Promise<Profile> {
  if (isDemoMode()) return localProfile;
  try {
    return await request<Profile>('/me');
  } catch {
    return localProfile;
  }
}

export async function patchProfile(timezone: string): Promise<Profile> {
  if (isDemoMode()) {
    localProfile.timezone = timezone;
    return localProfile;
  }
  return request<Profile>('/me', {
    method: 'PATCH',
    body: JSON.stringify({ timezone }),
  });
}

export async function getActiveMission(): Promise<MissionDetail> {
  if (isDemoMode()) return localMission;
  try {
    return await request<MissionDetail>('/missions/active');
  } catch {
    return localMission;
  }
}

export async function getIntentions(): Promise<Intention[]> {
  if (isDemoMode()) return localIntentions;
  try {
    return await request<Intention[]>('/intentions');
  } catch {
    return localIntentions;
  }
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
      message: 'Support resources are available 24/7 if you are feeling overwhelmed.',
      resources: [
        { name: 'Crisis Text Line', contact: 'Text HOME to 741741', detail: 'Free 24/7 crisis support via SMS' },
        { name: 'National Suicide & Crisis Lifeline', contact: 'Dial 988', detail: 'Confidential phone and text hotline' },
        { name: 'Campus Support Services', contact: 'Refer to institutional directory', detail: 'Academic and mental wellbeing counseling' },
      ],
      verified_on: '2026-10-11',
    };
  }
  return request<SupportPayload>('/support/resources');
}

export async function exportAccountData(): Promise<any> {
  if (isDemoMode()) {
    return {
      profile: localProfile,
      mission: localMission,
      intentions: localIntentions,
      exported_at: new Date().toISOString(),
      note: 'Self-service account data export per SPEC Section 9',
    };
  }
  return request('/me/export');
}

export async function deleteAccount(): Promise<any> {
  if (isDemoMode()) {
    return { status: 'deleted' };
  }
  return request('/me', {
    method: 'DELETE',
    body: JSON.stringify({ confirm: 'DELETE MY DATA' }),
  });
}
