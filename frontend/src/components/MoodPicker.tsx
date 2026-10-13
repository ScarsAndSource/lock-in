import React from 'react';

interface MoodPickerProps {
  valence: number | null;
  energy: number | null;
  onChange: (next: { valence: number | null; energy: number | null }) => void;
}

const Row: React.FC<{
  label: string;
  low: string;
  high: string;
  value: number | null;
  onPick: (n: number) => void;
}> = ({ label, low, high, value, onPick }) => (
  <div className="space-y-1">
    <div className="flex items-center justify-between">
      <span className="font-small text-ink">{label}</span>
      <span className="font-caption text-caption text-muted-text">
        {low} → {high}
      </span>
    </div>
    <div className="flex items-center bg-surface-container p-0.5 rounded-lg">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onPick(n)}
          className={`flex-1 py-1.5 rounded font-small-medium transition-colors ${
            value === n ? 'bg-ink text-ground-chalk font-semibold' : 'text-ink'
          }`}
        >
          {n}
        </button>
      ))}
    </div>
  </div>
);

/** Two taps: how the day felt, how much energy. Both are needed before it counts. */
export const MoodPicker: React.FC<MoodPickerProps> = ({ valence, energy, onChange }) => (
  <div className="p-3 bg-surface rounded-xl border border-line space-y-3">
    <Row
      label="How did today feel?"
      low="rough"
      high="great"
      value={valence}
      onPick={(n) => onChange({ valence: n, energy })}
    />
    <Row
      label="Energy"
      low="drained"
      high="buzzing"
      value={energy}
      onPick={(n) => onChange({ valence, energy: n })}
    />
    {(valence === null) !== (energy === null) && (
      <p className="font-caption text-caption text-muted-text">Tap the other row too and it gets saved.</p>
    )}
  </div>
);
