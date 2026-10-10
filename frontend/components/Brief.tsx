import { ok, type Dashboard } from "@/lib/api";
import { fixed, signed, thousands } from "@/lib/format";
import {
  buildStatus, hrvTone, latest, rangePosition, restingHrTone, shortNightStreak, sleepTone, stepsTone, type Tone,
} from "@/lib/status";

type TileProps = {
  label: string;
  value: string;
  unit: string;
  tone: Tone;
  current: number | null;
  normal: number | null;
  delta?: string;
  normalText?: string;
};

function Tile({ label, value, unit, tone, current, normal, delta, normalText }: TileProps) {
  const position = current != null && normal ? rangePosition(current, normal) : null;
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}<span>{unit}</span></div>
      {/* The middle of the bar is the user's normal; the dot is the latest reading */}
      <div className={`range tone-${tone}`} aria-hidden="true">
        {position != null && (
          <>
            <span className="range-fill" style={{ left: `${Math.min(50, position)}%`, width: `${Math.abs(position - 50)}%` }} />
            <span className="range-dot" style={{ left: `${position}%` }} />
          </>
        )}
      </div>
      <div className="tile-sub">
        {delta ? <><b className={`tone-${tone}`}>{delta}</b> vs {normalText}</> : "No baseline yet"}
      </div>
    </div>
  );
}

export default function Brief({ data, error, days }: { data: Dashboard | null; error: string | null; days: number }) {
  if (error) return <section className="brief"><p className="brief-detail">{error}</p></section>;
  if (!data) return <section className="brief"><p className="brief-detail">Reading your data</p></section>;

  const sleep = ok(data.sleep);
  const metrics = ok(data.metrics);
  const status = buildStatus(sleep, metrics);

  const lastNight = sleep?.nights.at(-1);
  const sleepNormal = sleep?.baseline_avg_hours_before_period ?? null;
  const base = metrics?.baseline_before_period;
  const rhr = metrics ? latest(metrics.days, "resting_hr") : null;
  const hrv = metrics ? latest(metrics.days, "hrv_ms") : null;
  const steps = metrics?.avg_steps ?? null;

  return (
    <section className="brief">
      <div className={`brief-label tone-${status.tone}`}><i />{status.label}</div>
      <h1>{status.headline}</h1>
      {status.detail && <p className="brief-detail">{status.detail}</p>}

      <div className="tiles">
        <Tile
          label="Sleep" value={fixed(lastNight?.hours)} unit="h"
          tone={lastNight && sleep ? sleepTone(lastNight.hours, shortNightStreak(sleep), sleepNormal) : "ok"}
          current={lastNight?.hours ?? null} normal={sleepNormal}
          delta={lastNight && sleepNormal != null ? signed(lastNight.hours - sleepNormal, 1) : undefined}
          normalText={`${fixed(sleepNormal)} h`}
        />
        <Tile
          label="Resting HR" value={rhr ? String(rhr.resting_hr) : "–"} unit="bpm"
          tone={rhr ? restingHrTone(rhr.resting_hr, base?.avg_resting_hr ?? null) : "ok"}
          current={rhr?.resting_hr ?? null} normal={base?.avg_resting_hr ?? null}
          delta={rhr && base?.avg_resting_hr != null ? signed(rhr.resting_hr - base.avg_resting_hr) : undefined}
          normalText={fixed(base?.avg_resting_hr, 0)}
        />
        <Tile
          label="HRV" value={hrv ? fixed(hrv.hrv_ms, 0) : "–"} unit="ms"
          tone={hrv ? hrvTone(hrv.hrv_ms, base?.avg_hrv_ms ?? null) : "ok"}
          current={hrv?.hrv_ms ?? null} normal={base?.avg_hrv_ms ?? null}
          delta={hrv && base?.avg_hrv_ms != null ? signed(hrv.hrv_ms - base.avg_hrv_ms) : undefined}
          normalText={fixed(base?.avg_hrv_ms, 0)}
        />
        <Tile
          label={`Steps · ${days}d avg`} value={thousands(steps)} unit=""
          tone={stepsTone(steps, base?.avg_steps ?? null)}
          current={steps} normal={base?.avg_steps ?? null}
          delta={steps != null && base?.avg_steps
            ? `${signed(Math.round(((steps - base.avg_steps) / base.avg_steps) * 100))}%`
            : undefined}
          normalText={thousands(base?.avg_steps)}
        />
      </div>
    </section>
  );
}
