import { request, isDemoMode, isNotFound } from './client';
import { Insight, RetroDetail, InsightFeedback, WeekMode } from '../types';
import { INITIAL_INSIGHTS, INITIAL_RETRO } from '../store/mockData';

let localInsights = [...INITIAL_INSIGHTS];
let localRetro: RetroDetail | null = { ...INITIAL_RETRO };

export async function getInsights(): Promise<Insight[]> {
  if (isDemoMode()) return localInsights;
  return request<Insight[]>('/insights');
}

export async function submitInsightFeedback(insightId: string, feedback: InsightFeedback): Promise<Insight> {
  if (isDemoMode()) {
    const item = localInsights.find((i) => i.id === insightId);
    if (!item) throw new Error('Insight not found');
    item.user_feedback = feedback;
    return item;
  }
  return request<Insight>(`/insights/${insightId}/feedback`, {
    method: 'POST',
    body: JSON.stringify({ feedback }),
  });
}

export async function refreshInsights(): Promise<{ generated: Insight[]; skipped_reason?: string | null }> {
  if (isDemoMode()) {
    return { generated: localInsights, skipped_reason: null };
  }
  return request<{ generated: Insight[]; skipped_reason?: string | null }>('/insights/refresh', { method: 'POST' });
}

export async function getLatestRetro(): Promise<RetroDetail | null> {
  if (isDemoMode()) return localRetro;
  try {
    return await request<RetroDetail>('/retros/latest');
  } catch (err) {
    if (isNotFound(err)) return null;
    throw err;
  }
}

export async function generateRetro(mode: WeekMode = 'auto'): Promise<RetroDetail> {
  if (isDemoMode()) {
    if (!localRetro) localRetro = { ...INITIAL_RETRO };
    localRetro.status = 'ready';
    localRetro.completed_at = null;
    return localRetro;
  }
  return request<RetroDetail>('/retros/generate', {
    method: 'POST',
    body: JSON.stringify({ mode }),
  });
}

export async function updateRetroTone(weekStart: string, mode: WeekMode): Promise<RetroDetail> {
  if (isDemoMode()) {
    if (!localRetro) throw new Error('No retro yet');
    localRetro.week_mode = {
      mode: mode === 'rough' ? 'rough' : 'normal',
      reasons: mode === 'rough' ? ['User requested rough-week calibrated coaching'] : ['Normal accountability tone'],
      source: 'user',
    };
    return localRetro;
  }
  return request<RetroDetail>(`/retros/${weekStart}/tone`, {
    method: 'POST',
    body: JSON.stringify({ mode }),
  });
}

export async function completeRetro(weekStart: string): Promise<{
  retro: RetroDetail;
  insights: { generated: Insight[]; skipped_reason?: string | null };
}> {
  if (isDemoMode()) {
    if (!localRetro) throw new Error('No retro yet');
    localRetro.completed_at = new Date().toISOString();
    localRetro.status = 'completed';
    return { retro: localRetro, insights: { generated: localInsights } };
  }
  return request(`/retros/${weekStart}/complete`, { method: 'POST' });
}
