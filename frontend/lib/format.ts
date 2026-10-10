const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "2026-10-08" -> local Date, without the UTC shift that new Date(string) applies
function parse(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** "2026-10-08" -> "Thu 8" */
export function shortDate(iso: string) {
  const d = parse(iso);
  return `${WEEKDAYS[d.getDay()]} ${d.getDate()}`;
}

/** Date -> "Sat 10 Oct" */
export function headerDate(d: Date) {
  return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

export function fixed(value: number | null | undefined, digits = 1) {
  return value == null ? "–" : value.toFixed(digits);
}

export function thousands(value: number | null | undefined) {
  return value == null ? "–" : Math.round(value).toLocaleString("en-US");
}

/** Signed difference with a real minus sign: "+6", "−0.4" */
export function signed(value: number, digits = 0) {
  const text = Math.abs(value).toFixed(digits);
  if (Number(text) === 0) return `±${text}`;
  return `${value > 0 ? "+" : "−"}${text}`;
}

/** "00:28" -> minutes after midnight */
export function clockMinutes(clock: string) {
  const [h, m] = clock.split(":").map(Number);
  return h * 60 + m;
}
