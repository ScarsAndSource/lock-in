import React, { useState, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import { getConsistency } from '../api/stats';
import { createHabit } from '../api/habits';
import {
  getSubjects,
  bulkCreateSubjects,
  logStudySession,
  getStudySummary,
  getUrges,
  getUrgeSummary,
  logSleep,
  logScreenTime,
} from '../api/tracking';
import { getPauseOverview, quickPause, resumePause } from '../api/pauses';
import {
  ConsistencyOut,
  Subject,
  StudySummary,
  UrgeLog,
  UrgeSummary,
  PauseOverview,
  PausePreset,
} from '../types';
import { formatComeback, formatMinutes, formatPct, errorMessage } from '../lib/format';

type TrackDomain = 'habits' | 'sleep' | 'screen' | 'study' | 'urges' | 'pauses';

export const TrackView: React.FC = () => {
  const { showToast, setUrgeQuickModalOpen, activeDate, dataEpoch, demoMode, bumpData } = useApp();
  const [selectedDomain, setSelectedDomain] = useState<TrackDomain>('habits');

  // Domain states
  const [consistency, setConsistency] = useState<ConsistencyOut | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [studySummary, setStudySummary] = useState<StudySummary | null>(null);
  const [urges, setUrges] = useState<UrgeLog[]>([]);
  const [urgeSummary, setUrgeSummary] = useState<UrgeSummary | null>(null);
  const [pauseOverview, setPauseOverview] = useState<PauseOverview | null>(null);

  // Forms
  const [newHabitName, setNewHabitName] = useState('');
  const [newHabitCount, setNewHabitCount] = useState(5);
  const [bulkSubjectsText, setBulkSubjectsText] = useState('');
  const [sessionSubjectId, setSessionSubjectId] = useState('');
  const [sessionPlanned, setSessionPlanned] = useState(60);
  const [sessionActual, setSessionActual] = useState(60);

  // Sleep/Screen log forms
  const [sleepBed, setSleepBed] = useState('23:00');
  const [sleepWake, setSleepWake] = useState('07:00');
  const [sleepQual, setSleepQual] = useState(4);
  const [screenMinutes, setScreenMinutes] = useState(180);

  const loadAll = async () => {
    try {
      const [cons, subjs, summ, urg, urgSumm, pauseOver] = await Promise.all([
        getConsistency(30, activeDate),
        getSubjects(),
        getStudySummary(activeDate, 30),
        getUrges(activeDate, 14, true),
        getUrgeSummary(14),
        getPauseOverview(),
      ]);
      setConsistency(cons);
      setSubjects(subjs);
      setStudySummary(summ);
      setUrges(urg);
      setUrgeSummary(urgSumm);
      setPauseOverview(pauseOver);
      if (subjs.length > 0 && !sessionSubjectId) {
        setSessionSubjectId(subjs[0].id);
      }
    } catch (e) {
      showToast(errorMessage(e, 'Could not load tracking data'));
    }
  };

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeDate, demoMode, dataEpoch]);

  const handleCreateHabit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newHabitName.trim()) return;
    try {
      await createHabit(newHabitName.trim(), { type: 'n_per_week', count: newHabitCount });
      showToast('Habit registered');
      setNewHabitName('');
      bumpData();
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Error creating habit'));
    }
  };

  const handleBulkSubjects = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!bulkSubjectsText.trim()) return;
    try {
      await bulkCreateSubjects(bulkSubjectsText.trim());
      showToast('Subjects added');
      setBulkSubjectsText('');
      bumpData();
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Error adding subjects'));
    }
  };

  const handleLogStudy = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (!sessionSubjectId) {
        showToast('Add a subject first');
        return;
      }
      await logStudySession({
        log_date: activeDate,
        subject_id: sessionSubjectId,
        planned_minutes: sessionPlanned,
        actual_minutes: sessionActual,
      });
      showToast('Study session logged');
      bumpData();
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Error logging session'));
    }
  };

  const handleLogSleep = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await logSleep({
        log_date: activeDate,
        time_to_bed: sleepBed,
        time_woke: sleepWake,
        self_rated_quality: sleepQual,
      });
      showToast('Sleep entry recorded');
      bumpData();
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not save sleep'));
    }
  };

  const handleLogScreen = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await logScreenTime({
        log_date: activeDate,
        total_minutes: screenMinutes,
      });
      showToast('Screen time logged');
      bumpData();
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not save screen time'));
    }
  };

  const handleQuickPause = async (preset: PausePreset, habitId?: string) => {
    try {
      await quickPause(preset, habitId);
      showToast(`Pause applied: ${preset.replace('_', ' ')}`);
      bumpData();
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Error applying pause'));
    }
  };

  const handleResume = async (habitId?: string) => {
    try {
      await resumePause(habitId);
      showToast('Resumed schedule');
      bumpData();
    } catch (err: unknown) {
      showToast(errorMessage(err, 'Could not resume'));
    }
  };

  return (
    <div className="flex flex-col w-full pb-8 max-w-md mx-auto space-y-5">
      {/* Domain Switcher */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 pt-2 no-scrollbar">
        {[
          { key: 'habits', label: 'Habits', color: 'border-domain-habits-fill' },
          { key: 'sleep', label: 'Sleep', color: 'border-domain-sleep-fill' },
          { key: 'screen', label: 'Screen', color: 'border-domain-screen-fill' },
          { key: 'study', label: 'Study', color: 'border-domain-study-fill' },
          { key: 'urges', label: 'Urges', color: 'border-domain-urges-fill' },
          { key: 'pauses', label: 'Pauses', color: 'border-ink' },
        ].map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setSelectedDomain(tab.key as TrackDomain)}
            className={`px-3.5 py-1.5 rounded-lg font-caption text-caption whitespace-nowrap transition-all ${
              selectedDomain === tab.key
                ? 'bg-ink text-ground-chalk font-semibold shadow-xs'
                : 'bg-surface text-ink hover:bg-surface-container border border-line'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ----------------- HABITS DOMAIN ----------------- */}
      {selectedDomain === 'habits' && (
        <div className="space-y-4 animate-fadeIn">
          {/* Consistency Card */}
          <div className="p-4 bg-surface rounded-xl border border-line shadow-sm space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-caption text-caption text-muted-text uppercase tracking-wider">
                Rolling 30-Day Consistency
              </span>
              <span className="font-title text-title text-ink font-bold">
                {formatPct(consistency?.overall_pct)}
              </span>
            </div>
            <p className="font-caption text-caption text-muted-text">
              Lock'in model: Misses dent the percentage without wiping progress to zero.
            </p>
          </div>

          {/* Habit Items */}
          <div className="space-y-2.5">
            <h4 className="font-small-medium text-ink uppercase tracking-wider">Active Habits</h4>
            {consistency?.habits.map((h) => (
              <div key={h.habit_id} className="p-3.5 bg-surface rounded-xl border border-line space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-small-medium text-ink font-semibold">{h.habit_name}</span>
                  <span className="font-small-medium text-domain-habits-fill font-bold">
                    {formatPct(h.consistency_pct, 0)}
                  </span>
                </div>
                <div className="flex items-center justify-between font-caption text-caption text-muted-text">
                  <span>Current: {h.current_run} {h.run_unit}</span>
                  <span>Longest: {h.longest_run} {h.run_unit}</span>
                  <span>Comeback: {formatComeback(h.comeback_rate)}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Add Habit Form */}
          <form onSubmit={handleCreateHabit} className="p-4 bg-surface-container-low rounded-xl border border-line space-y-3">
            <span className="font-small-medium text-ink block">Define New Habit</span>
            <input
              type="text"
              placeholder="e.g. Daily Mobility, 15 min journal..."
              value={newHabitName}
              onChange={(e) => setNewHabitName(e.target.value)}
              className="w-full bg-surface border border-line rounded-lg px-3 py-2 font-small text-ink"
            />
            <div className="flex items-center justify-between">
              <span className="font-caption text-caption text-muted-text">Target days/week: {newHabitCount}</span>
              <input
                type="range"
                min="1"
                max="7"
                value={newHabitCount}
                onChange={(e) => setNewHabitCount(parseInt(e.target.value, 10))}
                className="w-32 accent-ink"
              />
            </div>
            <button
              type="submit"
              className="w-full h-10 bg-ink text-ground-chalk rounded-lg font-caption text-caption font-semibold hover:bg-secondary transition-colors"
            >
              Add Habit
            </button>
          </form>
        </div>
      )}

      {/* ----------------- SLEEP DOMAIN ----------------- */}
      {selectedDomain === 'sleep' && (
        <div className="space-y-4 animate-fadeIn">
          <div className="p-4 bg-surface rounded-xl border border-line shadow-sm space-y-1">
            <span className="font-caption text-caption text-muted-text uppercase tracking-wider">
              Sleep Foundation
            </span>
            <div className="flex items-center justify-between">
              <span className="font-title text-title text-ink font-bold">7 hr 15 min</span>
              <span className="px-2.5 py-1 rounded bg-domain-sleep-tint text-domain-sleep-fill font-caption text-caption font-semibold">
                88% Regularity
              </span>
            </div>
            <p className="font-caption text-caption text-muted-text">
              Target: In bed by 11:30 pm · Median wake up 06:45 am
            </p>
          </div>

          <form onSubmit={handleLogSleep} className="p-4 bg-surface rounded-xl border border-line space-y-3">
            <span className="font-small-medium text-ink block">Log Sleep Entry</span>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="font-caption text-caption text-muted-text block mb-1">To bed</label>
                <input
                  type="time"
                  value={sleepBed}
                  onChange={(e) => setSleepBed(e.target.value)}
                  className="w-full bg-surface-container-low border border-line rounded-lg px-2.5 py-1.5 font-small text-ink"
                />
              </div>
              <div>
                <label className="font-caption text-caption text-muted-text block mb-1">Woke up</label>
                <input
                  type="time"
                  value={sleepWake}
                  onChange={(e) => setSleepWake(e.target.value)}
                  className="w-full bg-surface-container-low border border-line rounded-lg px-2.5 py-1.5 font-small text-ink"
                />
              </div>
            </div>
            <div>
              <label className="font-caption text-caption text-muted-text block mb-1">
                Quality: {sleepQual}/5
              </label>
              <input
                type="range"
                min="1"
                max="5"
                value={sleepQual}
                onChange={(e) => setSleepQual(parseInt(e.target.value, 10))}
                className="w-full accent-domain-sleep-fill"
              />
            </div>
            <button
              type="submit"
              className="w-full h-10 bg-ink text-ground-chalk rounded-lg font-caption text-caption font-semibold hover:bg-secondary transition-colors"
            >
              Save Sleep Record
            </button>
          </form>
        </div>
      )}

      {/* ----------------- SCREEN DOMAIN ----------------- */}
      {selectedDomain === 'screen' && (
        <div className="space-y-4 animate-fadeIn">
          <div className="p-4 bg-surface rounded-xl border border-line shadow-sm space-y-2">
            <span className="font-caption text-caption text-muted-text uppercase tracking-wider">
              Screen Exposure
            </span>
            <div className="flex items-center justify-between">
              <span className="font-title text-title text-ink font-bold">3 hr 10 min</span>
              <span className="px-2.5 py-1 rounded bg-domain-screen-tint text-ink font-caption text-caption font-semibold">
                Under 3.5h Cap
              </span>
            </div>
            <div className="space-y-1 pt-1 font-caption text-caption text-muted-text">
              <div className="flex justify-between"><span>Productivity:</span><span>2h 00m</span></div>
              <div className="flex justify-between"><span>Social & Feeds:</span><span>45m</span></div>
              <div className="flex justify-between"><span>Entertainment:</span><span>25m</span></div>
            </div>
          </div>

          <form onSubmit={handleLogScreen} className="p-4 bg-surface rounded-xl border border-line space-y-3">
            <span className="font-small-medium text-ink block">Update Screen Time</span>
            <div className="flex items-center justify-between">
              <span className="font-small text-ink">Duration</span>
              <span className="font-small-medium text-ink font-bold">
                {Math.floor(screenMinutes / 60)}h {screenMinutes % 60}m
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="600"
              step="15"
              value={screenMinutes}
              onChange={(e) => setScreenMinutes(parseInt(e.target.value, 10))}
              className="w-full accent-domain-screen-fill"
            />
            <button
              type="submit"
              className="w-full h-10 bg-ink text-ground-chalk rounded-lg font-caption text-caption font-semibold hover:bg-secondary transition-colors"
            >
              Save Screen Time
            </button>
          </form>
        </div>
      )}

      {/* ----------------- STUDY DOMAIN ----------------- */}
      {selectedDomain === 'study' && (
        <div className="space-y-4 animate-fadeIn">
          {/* Summary Card */}
          <div className="p-4 bg-surface rounded-xl border border-line shadow-sm space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-caption text-caption text-muted-text uppercase tracking-wider">
                Academic Follow-Through
              </span>
              <span className="font-title text-title text-ink font-bold">
                {studySummary?.follow_through_pct || 94}%
              </span>
            </div>
            <p className="font-caption text-caption text-muted-text">
              {studySummary?.days_studied ?? 0} days studied · {formatMinutes(studySummary?.total_actual ?? 0)} total logged
            </p>
          </div>

          {/* Subjects list */}
          <div className="space-y-2">
            <h4 className="font-small-medium text-ink uppercase tracking-wider">
              Enrolled Subjects (Per-User)
            </h4>
            <div className="space-y-1.5">
              {subjects.map((s) => (
                <div
                  key={s.id}
                  className="p-3 bg-surface rounded-lg border border-line flex items-center justify-between"
                >
                  <span className="font-small-medium text-ink">{s.name}</span>
                  <span className="font-caption text-caption text-muted-text">Active</span>
                </div>
              ))}
            </div>
          </div>

          {/* Bulk add subjects per Decision 1 of SPEC */}
          <form onSubmit={handleBulkSubjects} className="p-4 bg-surface-container-low rounded-xl border border-line space-y-2">
            <span className="font-small-medium text-ink block">Bulk Add Subjects</span>
            <p className="font-caption text-caption text-muted-text">
              Paste comma-separated courses (e.g. "ADS, AISC, CN, Predictive Analytics")
            </p>
            <input
              type="text"
              placeholder="Course 1, Course 2, Course 3..."
              value={bulkSubjectsText}
              onChange={(e) => setBulkSubjectsText(e.target.value)}
              className="w-full bg-surface border border-line rounded-lg px-3 py-2 font-small text-ink"
            />
            <button
              type="submit"
              className="w-full h-9 bg-ink text-ground-chalk rounded-lg font-caption text-caption font-semibold hover:bg-secondary transition-colors"
            >
              Add Subjects
            </button>
          </form>

          {/* Log Study Session */}
          <form onSubmit={handleLogStudy} className="p-4 bg-surface rounded-xl border border-line space-y-3">
            <span className="font-small-medium text-ink block">Log Study Session</span>
            <div>
              <label className="font-caption text-caption text-muted-text block mb-1">Subject</label>
              <select
                value={sessionSubjectId}
                onChange={(e) => setSessionSubjectId(e.target.value)}
                className="w-full bg-surface-container-low border border-line rounded-lg px-3 py-2 font-small text-ink"
              >
                {subjects.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="font-caption text-caption text-muted-text block mb-1">Planned (min)</label>
                <input
                  type="number"
                  value={sessionPlanned}
                  onChange={(e) => setSessionPlanned(parseInt(e.target.value, 10))}
                  className="w-full bg-surface-container-low border border-line rounded-lg px-3 py-2 font-small text-ink"
                />
              </div>
              <div>
                <label className="font-caption text-caption text-muted-text block mb-1">Actual (min)</label>
                <input
                  type="number"
                  value={sessionActual}
                  onChange={(e) => setSessionActual(parseInt(e.target.value, 10))}
                  className="w-full bg-surface-container-low border border-line rounded-lg px-3 py-2 font-small text-ink"
                />
              </div>
            </div>
            <button
              type="submit"
              className="w-full h-10 bg-ink text-ground-chalk rounded-lg font-caption text-caption font-semibold hover:bg-secondary transition-colors"
            >
              Save Session
            </button>
          </form>
        </div>
      )}

      {/* ----------------- URGES DOMAIN ----------------- */}
      {selectedDomain === 'urges' && (
        <div className="space-y-4 animate-fadeIn">
          {/* Summary Card */}
          <div className="p-4 bg-surface rounded-xl border border-line shadow-sm space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-caption text-caption text-muted-text uppercase tracking-wider">
                14-Day Resist Rate
              </span>
              <span className="font-title text-title text-domain-urges-fill font-bold">
                {urgeSummary?.resist_rate_pct || 83.3}%
              </span>
            </div>
            <div className="flex items-center justify-between font-caption text-caption text-muted-text">
              <span>{urgeSummary?.resisted || 5} Resisted</span>
              <span>{urgeSummary?.relapsed || 1} Relapsed</span>
              <span>{urgeSummary?.relapse_free_days_pct || 92.8}% Free Days</span>
            </div>
          </div>

          {/* Quick Capture Button */}
          <button
            type="button"
            onClick={() => setUrgeQuickModalOpen(true)}
            className="w-full h-12 bg-domain-urges-fill text-ground-chalk rounded-xl font-body-strong flex items-center justify-center gap-2 hover:opacity-90 active:scale-[0.99] transition-all"
          >
            <span className="material-symbols-outlined text-[20px]">shield</span>
            <span>Open Urge Quick-Capture</span>
          </button>

          {/* Recent logs */}
          <div className="space-y-2">
            <h4 className="font-small-medium text-ink uppercase tracking-wider">Recent Urge Events</h4>
            <div className="space-y-2">
              {urges.map((u) => (
                <div key={u.id} className="p-3.5 bg-surface rounded-xl border border-line space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span
                      className={`px-2 py-0.5 rounded text-[11px] font-caption uppercase tracking-wider font-semibold ${
                        u.outcome === 'resisted'
                          ? 'bg-domain-study-tint text-domain-study-fill'
                          : 'bg-domain-urges-tint text-domain-urges-fill'
                      }`}
                    >
                      {u.outcome}
                    </span>
                    <span className="font-caption text-caption text-muted-text">{u.log_date}</span>
                  </div>
                  {u.trigger_context && (
                    <p className="font-small text-small text-ink">
                      <strong className="text-muted-text">Trigger:</strong> {u.trigger_context}
                    </p>
                  )}
                  {u.coping_strategy && (
                    <p className="font-caption text-caption text-muted-text">
                      <strong>Coping:</strong> {u.coping_strategy}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ----------------- PAUSES DOMAIN ----------------- */}
      {selectedDomain === 'pauses' && (
        <div className="space-y-4 animate-fadeIn">
          <div className="p-4 bg-surface rounded-xl border border-line shadow-sm space-y-2">
            <span className="font-caption text-caption text-muted-text uppercase tracking-wider">
              Strategic Habit Pauses
            </span>
            <p className="font-small text-ink leading-relaxed">
              Pauses protect your rolling consistency during exam periods, illness, or planned travel.
              No fake streak breaks.
            </p>
            {pauseOverview?.global_pause ? (
              <div className="p-3 bg-secondary-fixed rounded-lg flex items-center justify-between">
                <span className="font-caption text-caption text-ink font-semibold">
                  Global Pause Active until {pauseOverview.global_pause.end_date}
                </span>
                <button
                  type="button"
                  onClick={() => handleResume()}
                  className="px-2.5 py-1 bg-ink text-ground-chalk rounded text-caption font-semibold hover:bg-secondary"
                >
                  Resume All
                </button>
              </div>
            ) : (
              <div className="flex flex-wrap gap-1.5 pt-2">
                {[
                  { key: 'today' as PausePreset, label: 'Pause Today' },
                  { key: '3_days' as PausePreset, label: '3 Days (Recovery)' },
                  { key: '1_week' as PausePreset, label: '1 Week' },
                ].map((preset) => (
                  <button
                    key={preset.key}
                    type="button"
                    onClick={() => handleQuickPause(preset.key)}
                    className="px-3 py-1.5 bg-surface-container text-ink rounded-lg font-caption text-caption font-medium hover:bg-secondary-fixed transition-colors"
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Per-habit pause statuses */}
          <div className="space-y-2">
            <h4 className="font-small-medium text-ink uppercase tracking-wider">Habit Pause Controls</h4>
            <div className="space-y-2">
              {pauseOverview?.habits.map((hp) => (
                <div key={hp.habit_id} className="p-3 bg-surface rounded-xl border border-line flex items-center justify-between">
                  <div>
                    <span className="font-small-medium text-ink block">{hp.name}</span>
                    <span className="font-caption text-caption text-muted-text capitalize">
                      Status: {hp.effective_paused ? `Paused (${hp.paused_by})` : 'Active'}
                    </span>
                  </div>
                  {hp.effective_paused ? (
                    <button
                      type="button"
                      onClick={() => handleResume(hp.habit_id)}
                      className="px-2.5 py-1 bg-ink text-ground-chalk rounded font-caption text-caption font-semibold"
                    >
                      Resume
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleQuickPause('3_days', hp.habit_id)}
                      className="px-2.5 py-1 bg-surface-container text-ink rounded font-caption text-caption font-medium hover:bg-secondary-fixed"
                    >
                      Pause 3d
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
