/** ISO date (YYYY-MM-DD) shifted by whole days, in calendar terms (no time zone surprises). */
export function addDays(iso: string, days: number): string {
  const [y = 1970, m = 1, d = 1] = iso.split("-").map(Number);
  const shifted = new Date(Date.UTC(y, m - 1, d + days));
  return shifted.toISOString().slice(0, 10);
}

/** First and last day of a month given as "YYYY-MM". */
export function monthBounds(month: string): [string, string] {
  const [y = 1970, m = 1] = month.split("-").map(Number);
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const mm = String(m).padStart(2, "0");
  return [`${y}-${mm}-01`, `${y}-${mm}-${String(last).padStart(2, "0")}`];
}

/** The year the financial year (April to March) holding `iso` starts in. */
export function fyStartYear(iso: string): number {
  const [y = 1970, m = 1] = iso.split("-").map(Number);
  return m >= 4 ? y : y - 1;
}

/** First and last day of the financial year starting in April of `startYear`, e.g. 2026-27. */
export function fyBounds(startYear: number): [string, string] {
  return [`${startYear}-04-01`, `${startYear + 1}-03-31`];
}

/** "2026-27" for the financial year starting in 2026. */
export function fyLabel(startYear: number): string {
  return `${startYear}-${String((startYear + 1) % 100).padStart(2, "0")}`;
}
