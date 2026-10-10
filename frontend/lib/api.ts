export type Night = {
  date: string;
  hours: number;
  bedtime: string;
  wake_time: string;
  deep_minutes: number | null;
  rem_minutes: number | null;
};

export type Sleep = {
  period_nights: number;
  avg_hours: number | null;
  avg_bedtime: string;
  nights_under_6h: number;
  baseline_avg_hours_before_period: number | null;
  nights: Night[];
};

export type Day = {
  date: string;
  steps: number | null;
  active_minutes: number | null;
  resting_hr: number | null;
  hrv_ms: number | null;
};

export type Metrics = {
  period_days: number;
  avg_steps: number | null;
  avg_resting_hr: number | null;
  avg_hrv_ms: number | null;
  baseline_before_period: {
    avg_resting_hr: number | null;
    avg_hrv_ms: number | null;
    avg_steps: number | null;
  };
  days: Day[];
};

export type Workout = {
  date: string;
  weekday: string;
  name: string;
  type: string;
  duration_minutes: number;
  avg_hr: number | null;
};

export type Workouts = {
  period_days: number;
  workout_count: number;
  total_minutes: number;
  count_by_type: Record<string, number>;
  workouts: Workout[];
};

export type Profile = {
  name: string;
  age: number | null;
  sex: string | null;
  height_cm: number | null;
  weight_kg: number | null;
  goal: string | null;
};

// Each tool returns {error: "..."} instead of data when the period is empty
type OrError<T> = T | { error: string };

export type Dashboard = {
  profile: OrError<Profile>;
  sleep: OrError<Sleep>;
  metrics: OrError<Metrics>;
  workouts: Workouts;
};

export type Source = { n: number; title: string; page: number | null; url: string | null };

export type AskResponse = {
  answer: string;
  sources: Source[];
  safety: "ok" | "red_flag";
  conversation_id: number;
  tool_calls: { tool: string; args: Record<string, unknown> }[];
  latency_ms: number;
};

export function ok<T extends object>(value: OrError<T>): T | null {
  return "error" in value ? null : value;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : null;
    throw new Error(detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

export function getDashboard(days: number, signal?: AbortSignal) {
  return request<Dashboard>(`/dashboard?days=${days}`, { signal });
}

export function ask(question: string, conversationId: number | null) {
  return request<AskResponse>("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, conversation_id: conversationId ?? undefined }),
  });
}
