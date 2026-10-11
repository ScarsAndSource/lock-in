import { request, isDemoMode } from './client';
import { ConsistencyOut, ChainOut, PatternsOut } from '../types';
import { INITIAL_CONSISTENCY, INITIAL_CHAIN, INITIAL_PATTERNS } from '../store/mockData';

export async function getConsistency(window_days: number = 30): Promise<ConsistencyOut> {
  if (isDemoMode()) return INITIAL_CONSISTENCY;
  try {
    return await request<ConsistencyOut>(`/stats/consistency?window_days=${window_days}`);
  } catch {
    return INITIAL_CONSISTENCY;
  }
}

export async function getChain(days: number = 14): Promise<ChainOut> {
  if (isDemoMode()) return INITIAL_CHAIN;
  try {
    return await request<ChainOut>(`/stats/chain?days=${days}`);
  } catch {
    return INITIAL_CHAIN;
  }
}

export async function getPatterns(days: number = 30): Promise<PatternsOut> {
  if (isDemoMode()) return INITIAL_PATTERNS;
  try {
    return await request<PatternsOut>(`/stats/patterns?days=${days}`);
  } catch {
    return INITIAL_PATTERNS;
  }
}
