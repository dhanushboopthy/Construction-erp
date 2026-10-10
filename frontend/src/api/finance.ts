import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type {
  CashBook,
  CashEntry,
  CashEntryCreate,
  ExpenseCategory,
  ExpenseCategoryIn,
  ExpenseCategoryUpdate,
  KpiDefinition,
  Pnl,
  RateOverrides,
} from "./types";

/** FM1: cash book, expense heads, profit and loss and the KPI catalogue. */

export function useExpenseCategories(includeInactive = false) {
  return useQuery({
    queryKey: ["expense-categories", includeInactive],
    queryFn: () =>
      api<ExpenseCategory[]>(`/expense-categories?include_inactive=${includeInactive}`),
  });
}

export function useCreateExpenseCategory() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ExpenseCategoryIn) =>
      api<ExpenseCategory>("/expense-categories", { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["expense-categories"] }),
  });
}

export function useUpdateExpenseCategory() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: ExpenseCategoryUpdate }) =>
      api<ExpenseCategory>(`/expense-categories/${id}`, { method: "PATCH", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["expense-categories"] }),
  });
}

export function useCashBook(locationId: string, dateFrom: string, dateTo: string) {
  const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
  if (locationId) params.set("location_id", locationId);
  return useQuery({
    queryKey: ["cash-book", locationId, dateFrom, dateTo],
    enabled: dateFrom !== "" && dateTo !== "",
    queryFn: () => api<CashBook>(`/cash-book?${params.toString()}`),
  });
}

async function refreshMoney(client: ReturnType<typeof useQueryClient>) {
  for (const k of ["cash-book", "closing", "pnl"])
    await client.invalidateQueries({ queryKey: [k] });
}

export function useCreateCashEntry() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CashEntryCreate) =>
      api<CashEntry>("/cash-book", { method: "POST", body: json(body) }),
    onSuccess: () => refreshMoney(client),
  });
}

export function useReverseCashEntry() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      api<CashEntry>(`/cash-book/${id}/reverse`, { method: "POST", body: json({ reason }) }),
    onSuccess: () => refreshMoney(client),
  });
}

export function usePnl(period: string, locationId: string) {
  const params = new URLSearchParams({ period });
  if (locationId) params.set("location_id", locationId);
  return useQuery({
    queryKey: ["pnl", period, locationId],
    enabled: /^\d{4}-\d{2}$/.test(period),
    queryFn: () => api<Pnl>(`/reports/pnl?${params.toString()}`),
  });
}

/** FM3: prices set by hand, by user, with their rupee effect (owner only). */
export function useRateOverrides(period: string, locationId: string) {
  const params = new URLSearchParams({ period });
  if (locationId) params.set("location_id", locationId);
  return useQuery({
    queryKey: ["rate-overrides", period, locationId],
    enabled: /^\d{4}-\d{2}$/.test(period),
    queryFn: () => api<RateOverrides>(`/reports/rate-overrides?${params.toString()}`),
  });
}

export function useKpiDefinitions() {
  return useQuery({
    queryKey: ["kpi-definitions"],
    staleTime: Infinity,
    queryFn: () => api<KpiDefinition[]>("/kpis/definitions"),
  });
}
