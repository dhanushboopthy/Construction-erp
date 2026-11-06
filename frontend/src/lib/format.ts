/**
 * Display helpers. Money arrives from the API as decimal strings and is formatted as text,
 * never turned into a JavaScript number (ADR 0002).
 */

const IST = "Asia/Kolkata";

/** "10000.00" -> "10,000.00" using Indian digit grouping (lakh, crore). */
export function formatMoney(value: string): string {
  const negative = value.startsWith("-");
  const [whole = "0", fraction = "00"] = value.replace("-", "").split(".");
  const last3 = whole.slice(-3);
  const rest = whole.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  const grouped = rest ? `${rest},${last3}` : last3;
  return `${negative ? "-" : ""}${grouped}.${fraction.padEnd(2, "0").slice(0, 2)}`;
}

/** Timestamp in shop time, e.g. "9 Oct 2026, 4:30 pm". */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: IST,
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(iso));
}

/** The clock time in shop time on a 24-hour clock, e.g. "16:40". */
export function formatClock(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: IST,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(iso));
}

/** Time left as words: "3 h 20 min", "45 min", "under a minute". */
export function formatTimeLeft(seconds: number): string {
  const minutes = Math.floor(Math.max(0, seconds) / 60);
  if (minutes < 1) return "under a minute";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest} min`;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

/** A date in shop time, e.g. "9 Oct 2026". Dates ("2026-10-09") are not shifted by the time zone. */
export function formatDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "UTC",
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(`${iso.slice(0, 10)}T00:00:00Z`));
}

const DECIMAL = /^\d+(\.\d{1,2})?$/;

/** True when `value` is a non-negative amount with at most two decimals. */
export function isAmount(value: string): boolean {
  return DECIMAL.test(value.trim());
}

/** "20.000000" -> "20", "1.2500" -> "1.25": decimals from the API without trailing zeros. */
export function trimDecimal(value: string): string {
  return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

export const plural = (n: number, one: string, many: string = `${one}s`) =>
  `${n} ${n === 1 ? one : many}`;
