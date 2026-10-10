/** ISO date (YYYY-MM-DD) shifted by whole days, in calendar terms (no time zone surprises). */
export function addDays(iso: string, days: number): string {
  const [y = 1970, m = 1, d = 1] = iso.split("-").map(Number);
  const shifted = new Date(Date.UTC(y, m - 1, d + days));
  return shifted.toISOString().slice(0, 10);
}
