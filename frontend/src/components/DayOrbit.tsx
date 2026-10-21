import React from 'react';
import type { RhythmDto } from '../api/companion';

const C = 100; // viewBox centre
const R_RING = 78; // the day itself
const R_RISK = 91; // tough hours, drawn just outside the ring
const R_TICKS = 66;
const R_DOTS = 54; // one dot per habit due today

/** Midnight at the bottom, noon at the top, clockwise: mornings rise on the left like the sun. */
const angle = (minute: number): number => (((minute % 1440) + 1440) % 1440) / 1440 * 2 * Math.PI + Math.PI / 2;
const point = (r: number, minute: number) => ({ x: C + r * Math.cos(angle(minute)), y: C + r * Math.sin(angle(minute)) });

function arc(r: number, from: number, to: number): string {
  const span = ((((to - from) % 1440) + 1440) % 1440) || 1440;
  if (span >= 1439) return '';
  const a = point(r, from);
  const b = point(r, to);
  return `M ${a.x.toFixed(2)} ${a.y.toFixed(2)} A ${r} ${r} 0 ${span > 720 ? 1 : 0} 1 ${b.x.toFixed(2)} ${b.y.toFixed(2)}`;
}

export function clockText(minute: number): string {
  const m = ((minute % 1440) + 1440) % 1440;
  const h = Math.floor(m / 60);
  return `${h % 12 || 12}:${String(m % 60).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`;
}

function band(minute: number): string {
  const h = Math.floor(minute / 60);
  return h < 5 ? 'Late night' : h < 12 ? 'Morning' : h < 17 ? 'Afternoon' : h < 21 ? 'Evening' : 'Late evening';
}

const TAIL = [0, 1, 2, 3, 4, 5];

interface DayOrbitProps {
  rhythm: RhythmDto | null;
  localMinute: number;
  heading: string;
  done: number;
  total: number;
  isDemo?: boolean;
}

/**
 * The day as a small watch face. The ring is 24 hours (noon on top); the blue arc is the person's own night, the
 * warm arcs outside are the hours their urge logs say are hard, the green bead is when they usually close the day,
 * the dots inside are today's habits, and the comet is now. Everything except the comet is learned from their data,
 * and it says so when it is still guessing.
 */
export const DayOrbit: React.FC<DayOrbitProps> = ({ rhythm, localMinute, heading, done, total, isDemo = false }) => {
  const dots = Math.min(total, 12);
  const filled = total > 0 ? Math.round((Math.min(done, total) / total) * dots) : 0;
  const nowPt = point(R_RING, localMinute);
  const hasNight = rhythm !== null && rhythm.wake !== null && rhythm.bed !== null;
  const hasWindows = rhythm !== null && rhythm.windows.length > 0;
  const hasClose = rhythm !== null && rhythm.checkin !== null;
  const learning = rhythm === null || rhythm.confidence === 'low';

  const summary = [
    `It is ${clockText(localMinute)}.`,
    hasNight && rhythm ? `You usually sleep ${clockText(rhythm.bed ?? 0)} to ${clockText(rhythm.wake ?? 0)}.` : null,
    hasClose && rhythm ? `You usually close the day around ${clockText(rhythm.checkin ?? 0)}.` : null,
    hasWindows && rhythm
      ? `Tough hours: ${rhythm.windows.map((w) => `${clockText(w.start)} to ${clockText(w.end)}`).join(' and ')}.`
      : null,
    total > 0 ? `${done} of ${total} habits done today.` : null,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <section className="w-full flex flex-col items-center pt-1">
      <div className="relative w-[212px] h-[212px]">
        <svg viewBox="0 0 200 200" className="w-full h-full" role="img" aria-label={summary}>
          {/* the 24 hour ring */}
          <circle cx={C} cy={C} r={R_RING} fill="none" className="stroke-surface-container" strokeWidth={8} />

          {/* hour ticks: noon, 6am, 6pm and midnight are longer */}
          {Array.from({ length: 24 }, (_, h) => {
            const major = h % 6 === 0;
            const a = point(R_TICKS, h * 60);
            const b = point(R_TICKS - (major ? 5 : 2.5), h * 60);
            return (
              <line
                key={h}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                className="stroke-outline-variant"
                strokeWidth={major ? 1.4 : 0.8}
                strokeLinecap="round"
              />
            );
          })}

          {/* the person's night */}
          {hasNight && rhythm && (
            <path
              d={arc(R_RING, rhythm.bed ?? 0, rhythm.wake ?? 0)}
              fill="none"
              className="stroke-domain-sleep-fill"
              strokeWidth={8}
              strokeLinecap="round"
              opacity={0.55}
            />
          )}

          {/* hours that are hard for them, from their own urge logs */}
          {rhythm?.windows.map((w) => (
            <path
              key={w.start}
              d={arc(R_RISK, w.start, w.end)}
              fill="none"
              className="stroke-domain-urges-fill"
              strokeWidth={5}
              strokeLinecap="round"
              opacity={0.3 + 0.6 * Math.min(1, w.weight)}
            />
          ))}

          {/* when they usually close the day */}
          {hasClose && rhythm && (
            <circle
              cx={point(R_RING, rhythm.checkin ?? 0).x}
              cy={point(R_RING, rhythm.checkin ?? 0).y}
              r={4.5}
              className="fill-surface stroke-domain-study-fill"
              strokeWidth={2.2}
            />
          )}

          {/* today's habits, one dot each */}
          {Array.from({ length: dots }, (_, i) => {
            const a = (i / dots) * 2 * Math.PI - Math.PI / 2;
            const x = C + R_DOTS * Math.cos(a);
            const y = C + R_DOTS * Math.sin(a);
            return i < filled ? (
              <circle key={i} cx={x} cy={y} r={3.2} className="fill-ink" />
            ) : (
              <circle key={i} cx={x} cy={y} r={2.7} className="fill-none stroke-outline-variant" strokeWidth={1.4} />
            );
          })}

          {/* the comet: a short fading tail behind a pulsing head */}
          {TAIL.map((i) => (
            <path
              key={i}
              d={arc(R_RING, localMinute - (i + 1) * 14, localMinute - i * 14)}
              fill="none"
              className="stroke-ink"
              strokeWidth={4}
              strokeLinecap="round"
              opacity={0.5 - i * 0.08}
            />
          ))}
          <circle
            cx={nowPt.x}
            cy={nowPt.y}
            r={5}
            className="fill-ink animate-orbitPulse"
            style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
          />
          <circle cx={nowPt.x} cy={nowPt.y} r={5.5} className="fill-ink" />
          <circle cx={nowPt.x} cy={nowPt.y} r={2} className="fill-surface" />
        </svg>

        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none text-center">
          <span className="font-caption text-caption text-muted-text">{heading}</span>
          <span className="font-title text-title text-ink leading-tight">{clockText(localMinute)}</span>
          <span className="font-caption text-caption text-muted-text">{band(localMinute)}</span>
        </div>
      </div>

      <p className="font-caption text-caption text-muted-text text-center min-h-[18px]">
        {isDemo
          ? 'Demo rhythm'
          : learning
            ? 'Still learning your rhythm'
            : [
                hasNight ? 'night' : null,
                hasClose ? 'usual close' : null,
                hasWindows ? 'tough hours' : null,
              ]
                .filter(Boolean)
                .join(' · ')}
      </p>
    </section>
  );
};
