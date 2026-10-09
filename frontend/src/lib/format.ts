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
