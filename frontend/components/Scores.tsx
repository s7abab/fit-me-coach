import { useState, type ReactNode } from "react";
import type { LastNight, Overview, Score, Signal } from "@/lib/api";
import { hoursMinutes, shortDate, signed, thousands } from "@/lib/format";
import { SLEEP_GOAL_HOURS, type Tone } from "@/lib/status";

// The four rings: Google Health's three, then steps
type Kind = "readiness" | "cardio" | "sleep" | "steps";

// What one ring shows, whatever it measures
type RingData = {
  title: string;
  figure: ReactNode; // the number in the middle; null for none
  spoken: string; // the same, for screen readers
  wide?: boolean; // the figure is longer than three digits, so it is set smaller to fit the ring
  caption: string; // the word under the number
  percent: number; // how far round the ring is filled
  tone: Tone | "plain" | "none"; // "plain": an amount, neither good nor bad · "none": nothing to judge yet
};

type Row = { name: string; value: string; unit?: string; note?: string; tone?: Tone };

const LEVELS: Record<Score["level"], string> = { low: "Low", moderate: "Moderate", high: "High" };

const SIGNALS: Record<Signal["key"], { name: string; unit: string; digits: number }> = {
  sleep: { name: "Sleep", unit: "h", digits: 1 },
  resting_hr: { name: "Resting HR", unit: "bpm", digits: 0 },
  hrv: { name: "HRV", unit: "ms", digits: 0 },
};

const EMPTY: Record<Kind, string> = {
  readiness: "Needs a few days of sleep and heart data",
  cardio: "No heart rate zone data yet this week",
  sleep: "No sleep recorded yet",
  steps: "No steps recorded yet",
};

/** Readiness is the one score here that is ours: today's sleep and heart readings against the user's normal. */
function readinessRing(score: Score): RingData {
  return {
    title: "Readiness", figure: score.score, spoken: `${score.score} out of 100`, caption: LEVELS[score.level],
    percent: score.score, tone: score.level === "high" ? "ok" : score.level === "moderate" ? "amber" : "red",
  };
}

function readinessRows(score: Score): Row[] {
  return score.signals.map((s) => {
    const { name, unit, digits } = SIGNALS[s.key];
    return {
      name, unit, value: s.value.toFixed(digits), note: `${signed(s.value - s.normal, digits)} vs normal`,
      tone: s.score >= 65 ? "ok" : s.score >= 40 ? "amber" : "red",
    };
  });
}

function duration(minutes: number) {
  const [h, m] = hoursMinutes(minutes);
  return h === "0" ? `${Number(m)}m` : `${h}h ${m}m`;
}

/** Sleep is measured, not scored: how long the user was asleep, as Google Health reports it. */
function sleepRing(sleep: LastNight, today: string): RingData {
  const [h, m] = hoursMinutes(sleep.minutes);
  return {
    title: "Sleep", figure: <>{h}<small>h</small>{m}<small>m</small></>, spoken: `${h} hours ${m} minutes asleep`,
    caption: sleep.date === today ? "asleep" : shortDate(sleep.date), wide: true,
    percent: (sleep.minutes / (SLEEP_GOAL_HOURS * 60)) * 100, tone: "plain",
  };
}

function sleepRows(sleep: LastNight): Row[] {
  const rows: Row[] = [];
  if (sleep.awake_minutes != null) {
    rows.push({ name: "In bed", value: duration(sleep.minutes + sleep.awake_minutes), note: `${sleep.bedtime} – ${sleep.wake_time}` });
  }
  if (sleep.deep_minutes != null && sleep.rem_minutes != null) {
    rows.push({
      name: "Deep + REM", value: duration(sleep.deep_minutes + sleep.rem_minutes),
      note: `deep ${duration(sleep.deep_minutes)} · REM ${duration(sleep.rem_minutes)}`,
    });
  }
  if (sleep.awake_minutes != null) rows.push({ name: "Awake", value: duration(sleep.awake_minutes), note: "during the night" });
  if (!rows.length) rows.push({ name: "Asleep", value: duration(sleep.minutes), note: `${sleep.bedtime} – ${sleep.wake_time}` });
  return rows;
}

/** Cardio load is measured, not scored: minutes with a raised heart rate over the last 7 days, against the weekly goal. */
function cardioRing(cardio: NonNullable<Overview["cardio"]>): RingData {
  const percent = Math.round((cardio.week_minutes / cardio.target_minutes) * 100);
  const reached = percent >= 100;
  return {
    title: "Cardio load", figure: <>{percent}<small>%</small></>, spoken: `${percent} percent`, percent,
    caption: reached ? "Goal met" : "of goal", tone: reached ? "ok" : "plain",
  };
}

function cardioRows(cardio: NonNullable<Overview["cardio"]>): Row[] {
  const left = cardio.target_minutes - cardio.week_minutes;
  return [
    { name: "This week", value: String(cardio.week_minutes), unit: "min", note: "last 7 days" },
    { name: "Today", value: String(cardio.today_minutes ?? 0), unit: "min", note: "so far" },
    left > 0
      ? { name: "To goal", value: String(left), unit: "min", note: `goal ${cardio.target_minutes} min a week` }
      : { name: "Over goal", value: String(-left), unit: "min", note: `goal ${cardio.target_minutes} min a week` },
  ];
}

const STEP_GOAL = 10_000; // Fitbit's default daily goal; the ring fills towards it

function stepsRing(steps: NonNullable<Overview["steps"]>): RingData {
  const today = steps.today ?? 0;
  return {
    title: "Steps", figure: thousands(today), spoken: `${today} steps`, caption: "today", wide: today >= 1000,
    percent: (today / STEP_GOAL) * 100, tone: today >= STEP_GOAL ? "ok" : "plain",
  };
}

function stepsRows(steps: NonNullable<Overview["steps"]>): Row[] {
  const today = steps.today ?? 0;
  const yesterday = steps.days.at(-2)?.steps;
  const left = STEP_GOAL - today;
  return [
    { name: "7-day average", value: thousands(steps.avg_7d), note: "a day" },
    { name: "Yesterday", value: thousands(yesterday), note: "full day" },
    left > 0
      ? { name: "To goal", value: thousands(left), note: `goal ${thousands(STEP_GOAL)} a day` }
      : { name: "Over goal", value: thousands(-left), note: `goal ${thousands(STEP_GOAL)} a day` },
  ];
}

const SIZE = 132;
const STROKE = 10;
const RADIUS = (SIZE - STROKE) / 2;
const LENGTH = 2 * Math.PI * RADIUS;

type RingProps = { title: string; ring: RingData | null; selected: boolean; onSelect: () => void };

/** A ring that fills clockwise from the top. On phones it is also the tab for its details. */
function Ring({ title, ring, selected, onSelect }: RingProps) {
  const fill = ring ? Math.max(0, Math.min(100, ring.percent)) : 0;
  return (
    <button
      type="button" className={`ring tone-${ring?.tone ?? "none"}`} aria-pressed={selected} onClick={onSelect}
      aria-label={ring ? `${title}: ${ring.spoken ? `${ring.spoken}, ` : ""}${ring.caption}` : `${title}: nothing to show yet`}
    >
      <span className="ring-dial">
        <svg viewBox={`0 0 ${SIZE} ${SIZE}`} aria-hidden="true">
          <circle className="ring-track" cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} strokeWidth={STROKE} />
          {fill > 0 && (
            <circle
              className="ring-fill" cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} strokeWidth={STROKE}
              strokeDasharray={`${(fill / 100) * LENGTH} ${LENGTH}`}
              transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
            />
          )}
        </svg>
        <span className="ring-text">
          {ring?.figure !== null && <b className={ring?.wide ? "is-wide" : undefined}>{ring ? ring.figure : "–"}</b>}
          {ring && <span><i />{ring.caption}</span>}
        </span>
      </span>
      <span className="ring-title">{title}</span>
    </button>
  );
}

/** The readings behind a ring. */
function Details({ title, rows, empty, selected }: { title: string; rows: Row[] | null; empty: string | null; selected: boolean }) {
  return (
    <div className="drivers" data-selected={selected}>
      {rows ? (
        <ul aria-label={`Behind your ${title.toLowerCase()}`}>
          {rows.map((row) => (
            <li key={row.name} className={`tone-${row.tone ?? "ok"}`}>
              <i className="driver-dot" />
              <span className="driver-name">{row.name}</span>
              <span className="driver-value">{row.value}{row.unit && <small>{row.unit}</small>}</span>
              <span className="driver-note">{row.note}</span>
            </li>
          ))}
        </ul>
      ) : empty && <p>{empty}</p>}
    </div>
  );
}

export default function Scores({ overview }: { overview: Overview }) {
  const { readiness, calibration, cardio, sleep, steps } = overview;
  const today = overview.steps?.days.at(-1)?.date ?? new Date().toLocaleDateString("en-CA");
  // Phones show one ring's details at a time; start on one that has details to show
  const [selected, setSelected] = useState<Kind>(calibration ? "cardio" : "readiness");

  // Until there is enough history, the readiness ring says "Calibrating" and nothing else
  const calibrating: RingData | null = calibration && {
    title: "Readiness", figure: null, spoken: "", caption: "Calibrating", percent: 0, tone: "none",
  };

  const items: { kind: Kind; title: string; ring: RingData | null; rows: Row[] | null }[] = [
    { kind: "readiness", title: "Readiness", ring: readiness ? readinessRing(readiness) : calibrating, rows: readiness && readinessRows(readiness) },
    { kind: "cardio", title: "Cardio load", ring: cardio && cardioRing(cardio), rows: cardio && cardioRows(cardio) },
    { kind: "sleep", title: "Sleep", ring: sleep && sleepRing(sleep, today), rows: sleep && sleepRows(sleep) },
    { kind: "steps", title: "Steps", ring: steps && stepsRing(steps), rows: steps && stepsRows(steps) },
  ];

  return (
    <div className="scores">
      {items.map((item) => (
        <Ring key={item.kind} title={item.title} ring={item.ring} selected={item.kind === selected} onSelect={() => setSelected(item.kind)} />
      ))}
      {items.map((item) => (
        <Details
          key={item.kind} title={item.title} rows={item.rows} selected={item.kind === selected}
          empty={item.kind === "readiness" && calibration ? null : EMPTY[item.kind]}
        />
      ))}
    </div>
  );
}
