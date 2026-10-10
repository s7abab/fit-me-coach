import type { LastNight, Overview as OverviewData } from "@/lib/api";
import { hoursMinutes, shortDate, signed, thousands } from "@/lib/format";
import type { Tone } from "@/lib/status";

function Tile({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      {children}
    </div>
  );
}

function Empty({ label, text }: { label: string; text: string }) {
  return (
    <Tile label={label}>
      <div className="tile-value">–</div>
      <div className="meter" aria-hidden="true" />
      <div className="tile-sub">{text}</div>
    </Tile>
  );
}

/** One thin bar per day, scaled to the tallest. The last bar with a value is today. */
function Bars({ values, today }: { values: (number | null)[]; today: number }) {
  const max = Math.max(1, ...values.map((v) => v ?? 0));
  return (
    <div className="bars" aria-hidden="true">
      {values.map((v, i) => (
        <span key={i} className={i === today ? "is-today" : undefined} style={{ height: `${Math.max(8, ((v ?? 0) / max) * 100)}%` }} />
      ))}
    </div>
  );
}

function Meter({ percent, tone = "ok" }: { percent: number; tone?: Tone }) {
  return (
    <div className={`meter tone-${tone}`} aria-hidden="true">
      <span style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} />
    </div>
  );
}

function CardioTile({ cardio }: { cardio: OverviewData["cardio"] }) {
  if (!cardio) return <Empty label="Weekly cardio" text="No zone minutes yet" />;
  const reached = cardio.week_minutes >= cardio.target_minutes;
  return (
    <Tile label="Weekly cardio">
      <div className="tile-value">{cardio.week_minutes}<span>min</span></div>
      <Meter percent={(cardio.week_minutes / cardio.target_minutes) * 100} />
      <div className="tile-sub">
        {reached ? <b className="tone-ok">Goal reached</b> : `of ${cardio.target_minutes} zone min`}
      </div>
    </Tile>
  );
}

function StepsTile({ steps }: { steps: OverviewData["steps"] }) {
  if (!steps) return <Empty label="Steps" text="No steps yet" />;
  return (
    <Tile label="Steps · today">
      <div className="tile-value">{thousands(steps.today)}</div>
      <Bars values={steps.days.map((d) => d.steps)} today={steps.days.length - 1} />
      <div className="tile-sub">7-day avg {thousands(steps.avg_7d)}</div>
    </Tile>
  );
}

function SleepTile({ sleep, today }: { sleep: LastNight | null; today: string }) {
  if (!sleep) return <Empty label="Sleep" text="No sleep logged" />;
  const [hours, minutes] = hoursMinutes(sleep.minutes);
  const stages = [
    { name: "Deep", minutes: sleep.deep_minutes },
    { name: "REM", minutes: sleep.rem_minutes },
    { name: "Light", minutes: sleep.light_minutes },
    { name: "Awake", minutes: sleep.awake_minutes },
  ].filter((s) => s.minutes);
  const summary = stages.map((s) => `${s.name} ${hoursMinutes(s.minutes!).join("h ")}m`).join(", ");
  const delta = sleep.normal_hours != null ? sleep.minutes / 60 - sleep.normal_hours : null;
  return (
    <Tile label={sleep.date === today ? "Last night" : `Sleep · ${shortDate(sleep.date)}`}>
      <div className="tile-value">{hours}<span>h</span> {minutes}<span>m</span></div>
      {stages.length > 1 ? (
        <div className="stages" role="img" aria-label={summary} title={summary}>
          {stages.map((s) => <span key={s.name} className={`stage-${s.name.toLowerCase()}`} style={{ flexGrow: s.minutes! }} />)}
        </div>
      ) : <Meter percent={(sleep.minutes / 480) * 100} />}
      <div className="tile-sub">
        {delta != null ? <><b>{signed(delta, 1)}</b> vs {sleep.normal_hours!.toFixed(1)} h</> : `${sleep.bedtime} – ${sleep.wake_time}`}
      </div>
    </Tile>
  );
}

export default function Overview({ overview }: { overview: OverviewData }) {
  // The API's "today" is the last day in the steps list; fall back to the browser's date
  const today = overview.steps?.days.at(-1)?.date ?? new Date().toLocaleDateString("en-CA");
  return (
    <div className="tiles">
      <CardioTile cardio={overview.cardio} />
      <StepsTile steps={overview.steps} />
      <SleepTile sleep={overview.sleep} today={today} />
    </div>
  );
}
