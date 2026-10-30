import type { ReceivablesOwner } from "@/api/types";

export type ReceivableRow = ReceivablesOwner["rows"][number];

export type DueStatus = "over_limit" | "overdue" | "near_limit" | "ok" | "cash";

/** Credit used from this share of the limit counts as "near limit". Not in SPEC: confirm with
 * the owner (docs/UI_REFACTOR_PLAN.md, open question 1). Rule B8 itself only blocks above 100%. */
export const NEAR_LIMIT_PCT = 80;

export const DUE_STATUS: Record<
  DueStatus,
  { label: string; tone: "good" | "warn" | "critical" | "neutral" }
> = {
  over_limit: { label: "Over limit", tone: "critical" },
  overdue: { label: "Overdue", tone: "critical" },
  near_limit: { label: "Near limit", tone: "warn" },
  ok: { label: "OK", tone: "good" },
  cash: { label: "Cash", tone: "neutral" },
};

/**
 * Where a customer stands. In order: over the credit limit; any bill past its due date; at or
 * above 80% of the limit; otherwise OK, or Cash when the customer has no credit limit at all.
 * Percentages arrive as decimal strings from the API and are only compared, never added.
 */
export function dueStatus(
  row: Pick<ReceivableRow, "days_late" | "credit_limit" | "utilisation_pct">,
): DueStatus {
  const used = row.utilisation_pct === null ? null : Number(row.utilisation_pct);
  if (used !== null && used > 100) return "over_limit";
  if ((row.days_late ?? 0) > 0) return "overdue";
  if (used !== null && used >= NEAR_LIMIT_PCT) return "near_limit";
  return row.credit_limit === null ? "cash" : "ok";
}

/** Customers who owe money, worst first: most overdue, then most owed. Filtered by name and status. */
export function prepareDues(
  rows: ReceivableRow[],
  filters: { q: string; status: string },
): ReceivableRow[] {
  const needle = filters.q.trim().toLowerCase();
  return rows
    .filter((r) => Number(r.balance) > 0)
    .filter((r) => !needle || r.party_name.toLowerCase().includes(needle))
    .filter((r) => !filters.status || dueStatus(r) === filters.status)
    .sort((a, b) => Number(b.overdue) - Number(a.overdue) || Number(b.balance) - Number(a.balance));
}
