import { request, isDemoMode } from './client';
import type { SupportPayload } from '../types';

export type ShareKey = 'days' | 'hours' | 'proud' | 'focus' | 'habits';
export type CheerKind = 'showed_up' | 'proud' | 'hard_week' | 'rooting';

export const CHEER_TEXT: Record<CheerKind, string> = {
  showed_up: 'saw you show up',
  proud: 'proud of you',
  hard_week: 'that was a hard week, nice',
  rooting: 'rooting for you',
};

export const SHARE_ROWS: { key: ShareKey; label: string; hint: string }[] = [
  { key: 'days', label: 'Days I showed up', hint: 'Like "4 of 5 planned days". Never who missed.' },
  { key: 'hours', label: 'Study hours', hint: 'Only as a crew total, capped per day.' },
  { key: 'proud', label: 'What I\'m proud of', hint: 'One line you write when you close your week.' },
  { key: 'focus', label: 'My focus for next week', hint: 'One line you write when you close your week.' },
  { key: 'habits', label: 'Habit names', hint: 'You pick which ones, each week.' },
];

export interface CrewMember { username: string; role: 'owner' | 'member'; status: 'active' | 'invited'; is_me: boolean }
export interface Crew {
  id: string;
  name: string;
  role: 'owner' | 'member';
  quiet: boolean;
  invite_code: string | null;
  invite_expires_at: string | null;
  members: CrewMember[];
}
export interface CrewInvite { crew_id: string; crew_name: string; from_username: string | null; created_at: string }
export interface CrewOverview {
  username: string | null;
  share: Partial<Record<ShareKey, boolean>>;
  crews: Crew[];
  invites: CrewInvite[];
  blocks: string[];
}

export interface WeekPreview {
  days_showed: number;
  days_planned: number;
  marks: number;
  study_minutes: number;
  habit_names: string[];
}
export interface WeekInfo { week_start: string; week_end: string; closed: boolean; preview: WeekPreview }
export interface CloseResult { week_start: string; created: boolean; support: SupportPayload | null }

export interface CardMember {
  username: string;
  is_me: boolean;
  state: 'shared' | 'resting' | 'private';
  days_showed: number | null;
  days_planned: number | null;
  marks: number | null;
  proud: string | null;
  focus: string | null;
  habits: string[] | null;
}
export type CardData =
  | { locked: true; week_start: string }
  | { locked: false; week_start: string; week_end: string; members: CardMember[]; study_minutes: number | null; hours_sharers: number; goal?: { target_minutes: number; met: boolean | null } };

export interface CrewInbox {
  cheers: { id: string; kind: CheerKind; from_username: string; at: string; seen: boolean }[];
  boosts: { id: string; from_username: string; crew_id: string; crew_name: string; at: string; seen: boolean }[];
}

function live<T>(fn: () => Promise<T>): Promise<T> {
  if (isDemoMode()) return Promise.reject(new Error('Crew needs a real account. Sign in first.'));
  return fn();
}
const send = <T>(method: string, path: string, body?: unknown) =>
  live(() => request<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) }));

export const getCrewOverview = () => live(() => request<CrewOverview>('/crew/overview'));
export const getCrewInbox = () => live(() => request<CrewInbox>('/crew/inbox'));
export const markCrewInboxSeen = () => send<{ ok: boolean }>('POST', '/crew/inbox/seen');
export const setCrewUsername = (username: string) => send('PUT', '/crew/username', { username });
export const setCrewShare = (share: Record<ShareKey, boolean>) => send('PUT', '/crew/share', share);
export const createCrew = (name: string) => send('POST', '/crew', { name });
export const inviteToCrew = (id: string, username: string) => send('POST', `/crew/${id}/invite`, { username });
export const respondToInvite = (id: string, accept: boolean) => send('POST', `/crew/${id}/respond`, { accept });
export const joinCrewWithCode = (code: string) => send('POST', '/crew/join', { code });
export const makeInviteCode = (id: string, revoke = false) =>
  send<{ ok: boolean; code?: string; expires_at?: string }>('POST', `/crew/${id}/code`, { revoke });
export const leaveCrew = (id: string) => send('POST', `/crew/${id}/leave`);
export const setCrewQuiet = (id: string, quiet: boolean) => send('PUT', `/crew/${id}/quiet`, { quiet });
export const blockUser = (username: string) => send('POST', '/crew/blocks', { username });
export const unblockUser = (username: string) => send('DELETE', `/crew/blocks/${encodeURIComponent(username)}`);
export const getCrewWeek = () => live(() => request<WeekInfo>('/crew/week'));
export const closeCrewWeek = (body: { proud: string | null; focus: string | null; habits: string[] }) =>
  send<CloseResult>('POST', '/crew/week/close', body);
export const getCrewCard = (id: string, week: string) =>
  live(() => request<CardData>(`/crew/${id}/card?week=${encodeURIComponent(week)}`));
export const sendCheer = (id: string, to: string, kind: CheerKind) => send('POST', `/crew/${id}/cheer`, { to, kind });
export const sendBoost = (id: string, to: string | null) => send('POST', `/crew/${id}/boost`, { to });

export interface GoalInfo { week_start: string; target_minutes: number | null }
export interface BuddyDeal {
  id: string;
  crew_id: string;
  role: 'owner' | 'buddy';
  other: string;
  status: 'pending' | 'active';
  threshold: number;
  auto_send: boolean;
  message: string;
  armed_from: string | null;
  last_sent_at: string | null;
  created_at: string;
  misses: number | null;
  due: boolean;
}
export interface BuddyMessage { id: string; crew_id: string; from_username: string; body: string; at: string; seen: boolean }
export interface BuddyOverview { deals: BuddyDeal[]; messages: BuddyMessage[] }
export interface DuelSide { ratio_pct: number; baseline_pct: number; delta_pct: number }
export interface Duel {
  id: string;
  crew_id: string;
  role: 'challenger' | 'opponent';
  other: string;
  week_start: string;
  status: 'pending' | 'active';
  my_scored: boolean;
  result: { mine: DuelSide; theirs: DuelSide } | null;
}

export const getCrewGoal = (id: string) => live(() => request<GoalInfo>(`/crew/${id}/goal`));
export const setCrewGoal = (id: string, hours: number | null) => send('PUT', `/crew/${id}/goal`, { hours });
export const getBuddies = () => live(() => request<BuddyOverview>('/crew/buddy'));
export const proposeBuddy = (body: { crew_id: string; to: string; threshold: number; message: string; auto_send: boolean }) =>
  send<{ ok: boolean; support: SupportPayload | null }>('POST', '/crew/buddy', body);
export const respondBuddy = (id: string, accept: boolean) => send('POST', `/crew/buddy/${id}/respond`, { accept });
export const sendBuddyMessage = (id: string) => send('POST', `/crew/buddy/${id}/send`);
export const holdBuddy = (id: string) => send('POST', `/crew/buddy/${id}/hold`);
export const cancelBuddy = (id: string) => send('DELETE', `/crew/buddy/${id}`);
export const getDuels = () => live(() => request<{ duels: Duel[] }>('/crew/duels'));
export const proposeDuel = (crew_id: string, to: string) => send('POST', '/crew/duels', { crew_id, to });
export const respondDuel = (id: string, accept: boolean) => send('POST', `/crew/duels/${id}/respond`, { accept });
export const cancelDuel = (id: string) => send('DELETE', `/crew/duels/${id}`);
