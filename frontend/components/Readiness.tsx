import type { Readiness as ReadinessData, Signal } from "@/lib/api";
import { signed } from "@/lib/format";
import { hrvTone, rangePosition, restingHrTone, sleepTone, type Tone } from "@/lib/status";

const LEVEL: Record<ReadinessData["level"], { label: string; tone: Tone }> = {
  high: { label: "High", tone: "ok" },
  moderate: { label: "Moderate", tone: "amber" },
  low: { label: "Low", tone: "red" },
};

const SIGNAL: Record<Signal["key"], { name: string; unit: string; digits: number; tone: (value: number, normal: number) => Tone }> = {
  sleep: { name: "Sleep", unit: "h", digits: 1, tone: (v, n) => sleepTone(v, 0, n) },
  resting_hr: { name: "Resting HR", unit: "bpm", digits: 0, tone: restingHrTone },
  hrv: { name: "HRV", unit: "ms", digits: 0, tone: hrvTone },
};

const SIZE = 148;
const STROKE = 11;
const RADIUS = (SIZE - STROKE) / 2;
const LENGTH = 2 * Math.PI * RADIUS;

/** The one number the page leads with. The ring fills clockwise from the top. */
export function ReadinessRing({ readiness }: { readiness: ReadinessData | null }) {
  const level = readiness ? LEVEL[readiness.level] : null;
  return (
    <div
      className={`ring tone-${level?.tone ?? "none"}`} role="img"
      aria-label={readiness ? `Readiness ${readiness.score} out of 100, ${level!.label}` : "Readiness: not enough data yet"}
    >
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} aria-hidden="true">
        <circle className="ring-track" cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} strokeWidth={STROKE} />
        {readiness && readiness.score > 0 && (
          <circle
            className="ring-fill" cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} strokeWidth={STROKE}
            strokeDasharray={`${(readiness.score / 100) * LENGTH} ${LENGTH}`}
            transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
          />
        )}
      </svg>
      <div className="ring-text" aria-hidden="true">
        <b>{readiness ? readiness.score : "–"}</b>
        <span>{level ? <><i />{level.label}</> : "Readiness"}</span>
      </div>
    </div>
  );
}

/** Why the score is what it is: each signal against the user's own normal. */
export function Drivers({ signals }: { signals: Signal[] }) {
  return (
    <ul className="drivers" aria-label="What is driving your readiness">
      {signals.map((s) => {
        const { name, unit, digits, tone } = SIGNAL[s.key];
        const position = rangePosition(s.value, s.normal);
        return (
          <li key={s.key} className={`tone-${tone(s.value, s.normal)}`}>
            <i className="driver-dot" />
            <span className="driver-name">{name}</span>
            <span className="driver-value">{s.value.toFixed(digits)}<small>{unit}</small></span>
            <span className="driver-delta">{signed(s.value - s.normal, digits)} vs normal</span>
            {/* The middle tick is the user's normal; the bar reaches towards today's reading */}
            <span className="driver-bar" aria-hidden="true">
              <span style={{ left: `${Math.min(50, position)}%`, width: `${Math.abs(position - 50)}%` }} />
            </span>
          </li>
        );
      })}
    </ul>
  );
}
