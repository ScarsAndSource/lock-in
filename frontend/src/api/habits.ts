import { request, isDemoMode } from './client';
import { Habit, HabitLog, HabitStatus, TargetFrequency } from '../types';
import { INITIAL_HABITS } from '../store/mockData';

let localHabits = [...INITIAL_HABITS];
const localLogs: Record<string, HabitLog> = {};

export async function getHabits(): Promise<Habit[]> {
  if (isDemoMode()) {
    return localHabits.filter((h) => !h.archived_at);
  }
  return request<Habit[]>('/habits');
}

export interface TierText {
  floor_text?: string | null;
  stretch_text?: string | null;
}

export async function createHabit(
  name: string,
  target_frequency: TargetFrequency,
  tiers: TierText = {}
): Promise<Habit> {
  const floor_text = tiers.floor_text?.trim() || null;
  const stretch_text = tiers.stretch_text?.trim() || null;
  if (isDemoMode()) {
    const habit: Habit = {
      id: `habit-${Date.now()}`,
      name,
      target_frequency,
      archived_at: null,
      floor_text,
      stretch_text,
    };
    localHabits.push(habit);
    return habit;
  }
  return request<Habit>('/habits', {
    method: 'POST',
    body: JSON.stringify({ name, target_frequency, floor_text, stretch_text }),
  });
}

export async function patchHabit(
  habitId: string,
  data: { name?: string; archived?: boolean; target_frequency?: TargetFrequency } & TierText
): Promise<Habit> {
  if (isDemoMode()) {
    const habit = localHabits.find((h) => h.id === habitId);
    if (!habit) throw new Error('Habit not found');
    if (data.name) habit.name = data.name;
    if (data.target_frequency) habit.target_frequency = data.target_frequency;
    if ('floor_text' in data) habit.floor_text = data.floor_text?.trim() || null;
    if ('stretch_text' in data) habit.stretch_text = data.stretch_text?.trim() || null;
    if (data.archived !== undefined) habit.archived_at = data.archived ? new Date().toISOString() : null;
    return habit;
  }
  return request<Habit>(`/habits/${habitId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function logHabit(
  habitId: string,
  log_date: string,
  status: HabitStatus,
  note?: string | null
): Promise<HabitLog> {
  if (isDemoMode()) {
    const log: HabitLog = {
      habit_id: habitId,
      log_date,
      status,
      note: note || null,
      is_default: false,
    };
    localLogs[`${habitId}_${log_date}`] = log;
    return log;
  }
  return request<HabitLog>(`/habits/${habitId}/logs`, {
    method: 'POST',
    body: JSON.stringify({ log_date, status, note }),
  });
}
