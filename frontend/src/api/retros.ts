import { request, isDemoMode } from './client';
import { Insight, RetroDetail, InsightFeedback, WeekMode } from '../types';
import { INITIAL_INSIGHTS, INITIAL_RETRO } from '../store/mockData';

let localInsights = [...INITIAL_INSIGHTS];
let localRetro = { ...INITIAL_RETRO };

export async function getInsights(): Promise<Insight[]> {
  if (isDemoMode()) return localInsights;
  try {
    return await request<Insight[]>('/insights');
  } catch {
    return localInsights;
  }
}

export async function submitInsightFeedback(insightId: string, feedback: InsightFeedback): Promise<Insight> {
  if (isDemoMode()) {
    const item = localInsights.find((i) => i.id === insightId);
    if (item) item.user_feedback = feedback;
    return item || localInsights[0];
  }
  return request<Insight>(`/insights/${insightId}/feedback`, {
    method: 'POST',
    body: JSON.stringify({ feedback }),
  });
}

export async function refreshInsights(): Promise<{ generated: Insight[] }> {
  if (isDemoMode()) {
    return { generated: localInsights };
  }
  return request<{ generated: Insight[] }>('/insights/refresh', { method: 'POST' });
}

export async function getLatestRetro(): Promise<RetroDetail> {
  if (isDemoMode()) return localRetro;
  try {
    return await request<RetroDetail>('/retros/latest');
  } catch {
    return localRetro;
  }
}

export async function updateRetroTone(weekStart: string, mode: WeekMode): Promise<RetroDetail> {
  if (isDemoMode()) {
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

export async function completeRetro(weekStart: string): Promise<any> {
  if (isDemoMode()) {
    localRetro.completed_at = new Date().toISOString();
    localRetro.status = 'completed';
    return { retro: localRetro, insights: { generated: localInsights } };
  }
  return request(`/retros/${weekStart}/complete`, { method: 'POST' });
}
