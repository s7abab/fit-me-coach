import type { Metrics, Sleep } from "./api";
import { signed } from "./format";

export type Tone = "ok" | "amber" | "red";

// Thresholds for "below normal" (amber) and "alert" (red). Display only, not medical advice.
export const SHORT_NIGHT_HOURS = 6;
const SLEEP_BELOW_NORMAL_HOURS = 0.5;
const RHR_AMBER_BPM = 3;
const RHR_RED_BPM = 5;
const HRV_AMBER_RATIO = 0.9;
const HRV_RED_RATIO = 0.8;
const STEPS_AMBER_RATIO = 0.8;

const RANK: Record<Tone, number> = { ok: 0, amber: 1, red: 2 };

export function worst(tones: Tone[]): Tone {
  return tones.reduce<Tone>((a, b) => (RANK[b] > RANK[a] ? b : a), "ok");
}

export function latest<T, K extends keyof T>(rows: T[], key: K) {
  for (let i = rows.length - 1; i >= 0; i--) {
    if (rows[i][key] != null) return rows[i] as T & Record<K, NonNullable<T[K]>>;
  }
  return null;
}

/** Short nights in a row, counting back from the most recent night. */
export function shortNightStreak(sleep: Sleep) {
  let streak = 0;
  for (let i = sleep.nights.length - 1; i >= 0 && sleep.nights[i].hours < SHORT_NIGHT_HOURS; i--) streak++;
  return streak;
}

export function sleepTone(hours: number, streak: number, normal: number | null): Tone {
  if (streak >= 3) return "red";
  if (hours < SHORT_NIGHT_HOURS) return "amber";
  return normal != null && hours <= normal - SLEEP_BELOW_NORMAL_HOURS ? "amber" : "ok";
}

export function restingHrTone(bpm: number, normal: number | null): Tone {
  if (normal == null) return "ok";
  const diff = bpm - normal;
  return diff >= RHR_RED_BPM ? "red" : diff >= RHR_AMBER_BPM ? "amber" : "ok";
}

export function hrvTone(ms: number, normal: number | null): Tone {
  if (normal == null) return "ok";
  const ratio = ms / normal;
  return ratio <= HRV_RED_RATIO ? "red" : ratio <= HRV_AMBER_RATIO ? "amber" : "ok";
}

export function stepsTone(steps: number | null, normal: number | null): Tone {
  return steps != null && normal != null && steps < normal * STEPS_AMBER_RATIO ? "amber" : "ok";
}

const TONE_LABEL: Record<Tone, string> = { ok: "On track", amber: "Below your normal", red: "Needs attention" };

/** Where a value sits against the user's normal, as 0-100 along a bar whose middle is "normal". */
export function rangePosition(value: number, normal: number) {
  const SPAN = 0.3; // the bar covers normal ±30%
  const deviation = (value - normal) / normal;
  return 50 + (Math.max(-SPAN, Math.min(SPAN, deviation)) / SPAN) * 50;
}

/** Today's read at the top of the coach view: only what is off, worst first. */
export function buildStatus(sleep: Sleep | null, metrics: Metrics | null) {
  const parts: { text: string; tone: Tone }[] = [];

  if (sleep?.nights.length) {
    const last = sleep.nights[sleep.nights.length - 1];
    const normal = sleep.baseline_avg_hours_before_period;
    const streak = shortNightStreak(sleep);
    const tone = sleepTone(last.hours, streak, normal);
    if (streak >= 2) parts.push({ text: `${streak} short nights in a row`, tone });
    else if (streak === 1) parts.push({ text: `Short night: ${last.hours.toFixed(1)} h`, tone });
    else if (tone !== "ok" && normal != null)
      parts.push({ text: `Sleep ${signed(last.hours - normal, 1)} h vs your normal`, tone });
  }

  if (metrics) {
    const base = metrics.baseline_before_period;
    const rhr = latest(metrics.days, "resting_hr");
    if (rhr && base.avg_resting_hr != null) {
      const tone = restingHrTone(rhr.resting_hr, base.avg_resting_hr);
      if (tone !== "ok")
        parts.push({ text: `Resting HR ${signed(rhr.resting_hr - base.avg_resting_hr)} bpm above your normal`, tone });
    }
    const hrv = latest(metrics.days, "hrv_ms");
    if (hrv && base.avg_hrv_ms != null) {
      const tone = hrvTone(hrv.hrv_ms, base.avg_hrv_ms);
      if (tone !== "ok")
        parts.push({ text: `HRV ${signed(hrv.hrv_ms - base.avg_hrv_ms)} ms below your normal`, tone });
    }
  }

  if (!parts.length) {
    const hasData = Boolean(sleep?.nights.length || metrics);
    return {
      tone: "ok" as Tone,
      label: hasData ? TONE_LABEL.ok : "No data",
      headline: hasData ? "You're within your normal range" : "No data for this period",
      detail: hasData ? "Sleep, resting HR and HRV all look typical for you" : "",
    };
  }
  parts.sort((a, b) => RANK[b.tone] - RANK[a.tone]);
  const tone = worst(parts.map((p) => p.tone));
  return { tone, label: TONE_LABEL[tone], headline: parts[0].text, detail: parts.slice(1).map((p) => p.text).join(" · ") };
}
