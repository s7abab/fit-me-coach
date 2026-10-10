import { ok, type Dashboard, type Night } from "@/lib/api";
import { clockMinutes, fixed, shortDate, signed, thousands } from "@/lib/format";
import { SHORT_NIGHT_HOURS, hrvTone, latest, restingHrTone, type Tone } from "@/lib/status";
import Chart from "./Chart";

const RANGES = [7, 14, 30];

// The sleep timeline runs from 21:00 to 09:00
const TRACK_START = 21 * 60;
const TRACK_MINUTES = 12 * 60;

function SleepTrack({ night }: { night: Night }) {
  const offset = (clock: string) => (clockMinutes(clock) - TRACK_START + 1440) % 1440;
  const start = Math.min(offset(night.bedtime), TRACK_MINUTES);
  const end = Math.min(Math.max(offset(night.wake_time), start), TRACK_MINUTES);
  return (
    <div className="track" aria-hidden="true">
      <span
        className={night.hours < SHORT_NIGHT_HOURS ? "is-amber" : undefined}
        style={{ left: `${(start / TRACK_MINUTES) * 100}%`, width: `${((end - start) / TRACK_MINUTES) * 100}%` }}
      />
    </div>
  );
}

function Card({ title, hint, aside, children }: { title: string; hint?: string; aside?: string | null; children: React.ReactNode }) {
  return (
    <section className="card">
      <header>
        <h2>{title}{hint && <small>{hint}</small>}</h2>
        {aside && <span>{aside}</span>}
      </header>
      {children}
    </section>
  );
}

type SummaryProps = {
  value: string;
  unit: string;
  when: string; // which reading this is: "last night", "today", "daily average"
  delta?: string; // difference from the user's normal, already signed
  tone?: Tone;
  normal?: string;
};

/** The one number to take away from a chart, and how it compares with the user's normal. */
function Summary({ value, unit, when, delta, tone = "ok", normal }: SummaryProps) {
  return (
    <div className="summary">
      <div className="summary-value">{value}<span>{unit}</span><small>{when}</small></div>
      <p className="summary-delta">
        {delta ? <><b className={`tone-${tone}`}>{delta}</b> vs your normal of {normal}</> : "Not enough history for a normal yet"}
      </p>
    </div>
  );
}

/** "last night" / "today" when the reading is from today, otherwise its date. */
function when(date: string, ifToday: string) {
  return date === new Date().toLocaleDateString("en-CA") ? ifToday : shortDate(date);
}

type Props = { data: Dashboard | null; days: number; onDays: (days: number) => void };

export default function Trends({ data, days, onDays }: Props) {
  const sleep = data && ok(data.sleep);
  const metrics = data && ok(data.metrics);
  const workouts = data?.workouts;
  const base = metrics?.baseline_before_period;

  const night = sleep?.nights.at(-1);
  const sleepNormal = sleep?.baseline_avg_hours_before_period ?? null;
  const rhr = metrics ? latest(metrics.days, "resting_hr") : null;
  const hrv = metrics ? latest(metrics.days, "hrv_ms") : null;
  const steps = metrics?.avg_steps ?? null;

  return (
    <section className="trends" aria-label="Trends">
      <div className="trends-head">
        <h2>Trends</h2>
        <div className="segmented" role="group" aria-label="Period">
          {RANGES.map((n) => (
            <button key={n} type="button" aria-pressed={n === days} onClick={() => onDays(n)}>{n}d</button>
          ))}
        </div>
      </div>

      {data && (
        <div className="trend-grid">
          <Card title="Sleep" aside={sleep ? `${days}-day avg ${fixed(sleep.avg_hours)} h` : null}>
            {night && (
              <Summary
                value={fixed(night.hours)} unit="h" when={when(night.date, "last night")}
                tone={night.hours < SHORT_NIGHT_HOURS ? "amber" : "ok"}
                delta={sleepNormal != null ? `${signed(night.hours - sleepNormal, 1)} h` : undefined}
                normal={`${fixed(sleepNormal)} h`}
              />
            )}
            <Chart
              label="Sleep" unit="h" format={(v) => v.toFixed(1)}
              data={(sleep?.nights ?? []).map((n) => ({ date: n.date, value: n.hours }))}
              normal={sleep?.baseline_avg_hours_before_period}
              guide={{ value: SHORT_NIGHT_HOURS, label: "Short 6.0" }}
              flag={(v) => v < SHORT_NIGHT_HOURS} flagLabel="Under 6 hours"
            />
          </Card>
          <Card title="Resting heart rate" hint="Lower is usually better" aside={metrics ? `${days}-day avg ${fixed(metrics.avg_resting_hr, 0)}` : null}>
            {rhr && (
              <Summary
                value={String(rhr.resting_hr)} unit="bpm" when={when(rhr.date, "today")}
                tone={restingHrTone(rhr.resting_hr, base?.avg_resting_hr ?? null)}
                delta={base?.avg_resting_hr != null ? `${signed(rhr.resting_hr - base.avg_resting_hr)} bpm` : undefined}
                normal={`${fixed(base?.avg_resting_hr, 0)} bpm`}
              />
            )}
            <Chart
              label="Resting heart rate" unit="bpm" format={(v) => v.toFixed(0)}
              data={(metrics?.days ?? []).map((d) => ({ date: d.date, value: d.resting_hr }))}
              normal={base?.avg_resting_hr}
              flag={(v) => restingHrTone(v, base?.avg_resting_hr ?? null) !== "ok"} flagLabel="Above your normal"
            />
          </Card>
          <Card title="Heart rate variability" hint="Higher usually means better recovered" aside={metrics ? `${days}-day avg ${fixed(metrics.avg_hrv_ms, 0)}` : null}>
            {hrv && (
              <Summary
                value={fixed(hrv.hrv_ms, 0)} unit="ms" when={when(hrv.date, "today")}
                tone={hrvTone(hrv.hrv_ms, base?.avg_hrv_ms ?? null)}
                delta={base?.avg_hrv_ms != null ? `${signed(hrv.hrv_ms - base.avg_hrv_ms)} ms` : undefined}
                normal={`${fixed(base?.avg_hrv_ms, 0)} ms`}
              />
            )}
            <Chart
              label="Heart rate variability" unit="ms" format={(v) => v.toFixed(0)}
              data={(metrics?.days ?? []).map((d) => ({ date: d.date, value: d.hrv_ms }))}
              normal={base?.avg_hrv_ms}
              flag={(v) => hrvTone(v, base?.avg_hrv_ms ?? null) !== "ok"} flagLabel="Below your normal"
            />
          </Card>
          <Card title="Steps">
            {steps != null && (
              <Summary
                value={thousands(steps)} unit="" when={`a day, last ${days} days`}
                delta={base?.avg_steps ? `${signed(Math.round(((steps - base.avg_steps) / base.avg_steps) * 100))}%` : undefined}
                normal={thousands(base?.avg_steps)}
              />
            )}
            <Chart
              kind="bar" label="Steps" unit="steps" format={(v) => thousands(v)}
              data={(metrics?.days ?? []).map((d) => ({ date: d.date, value: d.steps }))}
              normal={base?.avg_steps}
            />
          </Card>

          <Card title="Nights" aside={sleep ? `avg bedtime ${sleep.avg_bedtime}` : null}>
            {sleep ? (
              <ul className="rows">
                {[...sleep.nights].reverse().map((n) => (
                  <li key={n.date} className="night">
                    <span className="row-date">{shortDate(n.date)}</span>
                    <span className="row-dim">{n.bedtime} – {n.wake_time}</span>
                    <SleepTrack night={n} />
                    <span className={n.hours < SHORT_NIGHT_HOURS ? "row-num tone-amber" : "row-num"}>
                      {fixed(n.hours)}<small>h</small>
                    </span>
                  </li>
                ))}
              </ul>
            ) : <p className="empty">No sleep logged in this period</p>}
          </Card>

          <Card
            title="Workouts"
            aside={workouts?.workout_count ? `${workouts.workout_count} sessions · ${workouts.total_minutes} min` : null}
          >
            {workouts?.workout_count ? (
              <ul className="rows">
                {[...workouts.workouts].reverse().map((w, i) => (
                  <li key={`${w.date}-${i}`} className="workout">
                    <span className="row-date">{shortDate(w.date)}</span>
                    <span>{w.name} <span className="row-dim">· {w.type}</span></span>
                    <span className="row-num">{w.duration_minutes}<small>min</small></span>
                    <span className="row-num">{w.avg_hr ?? "–"}<small>bpm</small></span>
                  </li>
                ))}
              </ul>
            ) : <p className="empty">No workouts logged in this period</p>}
          </Card>
        </div>
      )}
    </section>
  );
}
