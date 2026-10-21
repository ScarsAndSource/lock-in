import React, { useCallback, useEffect, useState } from 'react';
import { useApp } from '../context/AppContext';
import { Disclosure } from './Disclosure';
import {
  abandonExperiment,
  finishExperiment,
  getActiveExperiment,
  getExperimentMetrics,
  listExperiments,
  startExperiment,
} from '../api/experiments';
import type { Adherence, Experiment, ExperimentMetric, MetricInfo, VerdictKind } from '../api/experiments';

const MIN_BASELINE = 5;
const DURATIONS = [5, 7, 14];

const PRESETS: { text: string; metric: ExperimentMetric }[] = [
  { text: 'Phone out of the bedroom by 11:30pm', metric: 'sleep_hours' },
  { text: 'No phone for the first 30 min after waking', metric: 'mood' },
  { text: 'Study block before opening any app', metric: 'screen_minutes' },
  { text: "Plan tomorrow's top 3 tasks tonight", metric: 'task_rate' },
];

const VERDICT_LABEL: Record<VerdictKind, string> = {
  helped: 'Helped',
  hurt: 'Went the wrong way',
  no_clear_effect: 'No clear effect',
  not_enough_data: 'Not enough data',
  not_followed: 'Not followed',
};

const ADHERENCE: { key: Adherence; label: string }[] = [
  { key: 'mostly', label: 'Mostly' },
  { key: 'partly', label: 'Partly' },
  { key: 'barely', label: 'Barely' },
];

function dayDiff(a: string, b: string): number {
  return Math.round((Date.parse(`${a}T00:00:00Z`) - Date.parse(`${b}T00:00:00Z`)) / 86_400_000);
}

const Sparkline: React.FC<{ exp: Experiment }> = ({ exp }) => {
  const W = 300;
  const H = 72;
  const PAD = 6;
  const slots = exp.baseline_days + exp.treatment_days;
  const real = exp.points.filter((p) => p.value !== null) as { day: string; value: number; phase: string }[];
  if (real.length < 2) return null;

  const lo = Math.min(...real.map((p) => p.value));
  const hi = Math.max(...real.map((p) => p.value));
  const range = hi - lo || 1;
  const x = (idx: number) => PAD + (idx / Math.max(slots - 1, 1)) * (W - 2 * PAD);
  const y = (v: number) => H - PAD - ((v - lo) / range) * (H - 2 * PAD);
  const idxOf = (day: string) => dayDiff(day, exp.start_date) + exp.baseline_days;
  const v = exp.verdict;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-[72px]" role="img" aria-label="Baseline versus test days">
      <line
        x1={x(exp.baseline_days - 0.5)}
        x2={x(exp.baseline_days - 0.5)}
        y1={2}
        y2={H - 2}
        stroke="currentColor"
        className="text-line"
        strokeWidth={1}
      />
      {v && v.baseline_mean !== null && (
        <line
          x1={x(0)}
          x2={x(exp.baseline_days - 1)}
          y1={y(v.baseline_mean)}
          y2={y(v.baseline_mean)}
          stroke="currentColor"
          className="text-muted-text"
          strokeDasharray="4 3"
          strokeWidth={1}
        />
      )}
      {v && v.treatment_mean !== null && (
        <line
          x1={x(exp.baseline_days)}
          x2={x(slots - 1)}
          y1={y(v.treatment_mean)}
          y2={y(v.treatment_mean)}
          stroke="currentColor"
          className="text-ink"
          strokeDasharray="4 3"
          strokeWidth={1}
        />
      )}
      {real.map((p) => (
        <circle
          key={p.day}
          cx={x(idxOf(p.day))}
          cy={y(p.value)}
          r={2.5}
          fill="currentColor"
          className={p.phase === 'test' ? 'text-ink' : 'text-muted-text'}
        />
      ))}
    </svg>
  );
};

const VerdictBlock: React.FC<{ exp: Experiment }> = ({ exp }) => {
  const v = exp.verdict;
  if (!v) return null;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="px-2 py-0.5 rounded bg-surface-container font-caption text-caption font-semibold text-ink">
          {VERDICT_LABEL[v.kind]}
        </span>
        {exp.provisional && <span className="font-caption text-caption text-muted-text">so far</span>}
      </div>
      <p className="font-small text-ink">{v.sentence}</p>
      {v.caveats.map((c) => (
        <p key={c} className="font-caption text-caption text-muted-text">
          {c}
        </p>
      ))}
    </div>
  );
};

export const ExperimentCard: React.FC = () => {
  const { showToast, demoMode, dataEpoch } = useApp();
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState<Experiment | null>(null);
  const [past, setPast] = useState<Experiment[]>([]);
  const [metrics, setMetrics] = useState<MetricInfo[]>([]);
  const [formOpen, setFormOpen] = useState(false);
  const [change, setChange] = useState('');
  const [metric, setMetric] = useState<ExperimentMetric | null>(null);
  const [treatmentDays, setTreatmentDays] = useState(7);
  const [startOn, setStartOn] = useState<'today' | 'tomorrow'>('today');
  const [finishing, setFinishing] = useState(false);
  const [result, setResult] = useState<Experiment | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [a, list, m] = await Promise.all([getActiveExperiment(), listExperiments(10), getExperimentMetrics()]);
      setActive(a);
      setPast(list.filter((e) => e.status === 'done'));
      setMetrics(m);
    } catch {
      /* keep whatever is already on screen */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, demoMode, dataEpoch]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Something went wrong');
    } finally {
      setBusy(false);
    }
  };

  const submit = () =>
    run(async () => {
      const text = change.trim();
      if (!text || !metric) return;
      const exp = await startExperiment({
        title: text.slice(0, 120),
        change: text.slice(0, 200),
        metric,
        treatment_days: treatmentDays,
        start: startOn,
      });
      setActive(exp);
      setFormOpen(false);
      setChange('');
      setMetric(null);
      setResult(null);
    });

  const finish = (adherence: Adherence) =>
    run(async () => {
      if (!active) return;
      const done = await finishExperiment(active.id, adherence);
      setActive(null);
      setFinishing(false);
      setResult(done);
      setPast((p) => [done, ...p]);
    });

  const drop = () =>
    run(async () => {
      if (!active) return;
      if (!window.confirm('Drop this experiment? Nothing will be saved from it.')) return;
      await abandonExperiment(active.id);
      setActive(null);
      setFinishing(false);
    });

  if (loading) return null;

  return (
    <section className="bg-surface rounded-xl p-4 border border-line space-y-3">
      <div>
        <span className="font-caption text-caption text-muted-text uppercase tracking-wider block">Experiment</span>
        <h3 className="font-section text-section text-ink">
          {active ? active.change : 'Test a change on yourself'}
        </h3>
      </div>

      {/* ---------- a finished run, shown once ---------- */}
      {result && !active && (
        <div className="space-y-2 p-3 rounded-lg bg-surface-container">
          <p className="font-small-medium text-small-medium text-ink">{result.change}</p>
          <VerdictBlock exp={result} />
          <button
            type="button"
            onClick={() => setResult(null)}
            className="h-9 px-3 rounded-lg border border-line font-caption text-caption text-ink"
          >
            Got it
          </button>
        </div>
      )}

      {/* ---------- a run in progress ---------- */}
      {active && (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <div className="flex justify-between font-caption text-caption text-muted-text">
              <span>
                {active.phase === 'waiting'
                  ? `Starts ${active.start_date}`
                  : active.phase === 'complete'
                    ? 'Test window done'
                    : `Day ${active.day_number} of ${active.treatment_days}`}
              </span>
              <span>Watching {active.metric_label.toLowerCase()}</span>
            </div>
            <div className="w-full bg-surface-container rounded-full h-2 overflow-hidden">
              <div
                className="bg-ink h-full rounded-full transition-all"
                style={{ width: `${Math.min(100, (active.day_number / active.treatment_days) * 100)}%` }}
              />
            </div>
          </div>

          <Sparkline exp={active} />
          {active.phase !== 'waiting' && <VerdictBlock exp={active} />}

          {!finishing ? (
            <div className="flex gap-2">
              {active.phase !== 'waiting' && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setFinishing(true)}
                  className="flex-1 h-11 rounded-lg bg-ink text-ground-chalk font-small-medium text-small-medium disabled:opacity-50"
                >
                  {active.phase === 'complete' ? 'Get the verdict' : 'Finish early'}
                </button>
              )}
              <button
                type="button"
                disabled={busy}
                onClick={drop}
                className="h-11 px-4 rounded-lg border border-line font-small-medium text-small-medium text-ink disabled:opacity-50"
              >
                Drop it
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              <p className="font-small text-ink">How well did you keep to it?</p>
              <div className="grid grid-cols-3 gap-2">
                {ADHERENCE.map((a) => (
                  <button
                    key={a.key}
                    type="button"
                    disabled={busy}
                    onClick={() => finish(a.key)}
                    className="h-11 rounded-lg border border-line font-small-medium text-small-medium text-ink hover:bg-surface-container-low disabled:opacity-50"
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ---------- nothing running ---------- */}
      {!active && !formOpen && (
        <button
          type="button"
          onClick={() => setFormOpen(true)}
          className="w-full h-11 rounded-lg bg-ink text-ground-chalk font-small-medium text-small-medium"
        >
          Start an experiment
        </button>
      )}

      {!active && formOpen && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((p) => (
              <button
                key={p.text}
                type="button"
                onClick={() => {
                  setChange(p.text);
                  setMetric(p.metric);
                }}
                className="px-3 py-1.5 rounded-full border border-line font-caption text-caption text-ink hover:bg-surface-container-low"
              >
                {p.text}
              </button>
            ))}
          </div>

          <input
            value={change}
            onChange={(e) => setChange(e.target.value)}
            maxLength={200}
            placeholder="What will you change?"
            className="w-full h-11 px-3 rounded-lg border border-line bg-surface font-small text-ink"
          />

          <div className="space-y-1.5">
            <span className="font-caption text-caption text-muted-text">What should move?</span>
            <div className="grid grid-cols-2 gap-2">
              {metrics.map((m) => {
                const short = Math.max(0, MIN_BASELINE - m.usable_days);
                const disabled = short > 0;
                return (
                  <button
                    key={m.key}
                    type="button"
                    disabled={disabled}
                    onClick={() => setMetric(m.key)}
                    className={`min-h-[44px] px-3 py-1.5 rounded-lg border text-left transition-colors ${
                      metric === m.key ? 'bg-ink text-ground-chalk border-ink' : 'border-line text-ink'
                    } ${disabled ? 'opacity-40' : ''}`}
                  >
                    <span className="font-small-medium text-small-medium block">{m.label}</span>
                    <span className="font-caption text-caption opacity-70">
                      {disabled ? `needs ${short} more day${short === 1 ? '' : 's'} logged` : `${m.better} is better`}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center bg-surface-container p-0.5 rounded-lg">
              {DURATIONS.map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setTreatmentDays(d)}
                  className={`px-3 h-9 rounded font-caption text-caption ${
                    treatmentDays === d ? 'bg-ink text-ground-chalk font-semibold' : 'text-ink'
                  }`}
                >
                  {d} days
                </button>
              ))}
            </div>
            <div className="flex items-center bg-surface-container p-0.5 rounded-lg">
              {(['today', 'tomorrow'] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setStartOn(s)}
                  className={`px-3 h-9 rounded font-caption text-caption capitalize ${
                    startOn === s ? 'bg-ink text-ground-chalk font-semibold' : 'text-ink'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy || !change.trim() || !metric}
              onClick={submit}
              className="flex-1 h-11 rounded-lg bg-ink text-ground-chalk font-small-medium text-small-medium disabled:opacity-40"
            >
              Start
            </button>
            <button
              type="button"
              onClick={() => setFormOpen(false)}
              className="h-11 px-4 rounded-lg border border-line font-small-medium text-small-medium text-ink"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {past.length > 0 && (
        <Disclosure title="Past experiments" summary={`${past.length}`}>
          <div className="space-y-3 pt-2">
            {past.map((e) => (
              <div key={e.id} className="space-y-0.5">
                <p className="font-small-medium text-small-medium text-ink">{e.change}</p>
                <p className="font-caption text-caption text-muted-text">
                  {e.start_date} · {e.verdict ? VERDICT_LABEL[e.verdict.kind] : 'Closed'}
                </p>
                {e.verdict && <p className="font-small text-ink">{e.verdict.sentence}</p>}
              </div>
            ))}
          </div>
        </Disclosure>
      )}
    </section>
  );
};
