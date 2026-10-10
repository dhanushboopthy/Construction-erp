import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type {
  Closing,
  ClosingCreate,
  ClosingPreview,
  Cut,
  ItcAtRisk,
  Page,
  ProfitGroup,
  Profitability,
  ProfitReport,
  SegmentReport,
  Today,
} from "./types";

/** Milestone 12: Today figures, daily closing, profit and segment reports. */

export function useToday() {
  return useQuery({ queryKey: ["today"], queryFn: () => api<Today>("/reports/today") });
}

export function useClosingPreview(locationId: string, date: string) {
  return useQuery({
    queryKey: ["closing", "preview", locationId, date],
    enabled: locationId !== "" && date !== "",
    queryFn: () =>
      api<ClosingPreview>(`/closings/preview?location_id=${locationId}&closing_date=${date}`),
  });
}

export function useClosings() {
  return useQuery({
    queryKey: ["closing", "list"],
    queryFn: () => api<Page<Closing>>("/closings?limit=30"),
  });
}

export function useCloseDay() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ClosingCreate) =>
      api<Closing>("/closings", { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["closing"] }),
  });
}

export function useReopenDay() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      api<Closing>(`/closings/${id}/reopen`, { method: "POST", body: json({ reason }) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["closing"] }),
  });
}

export function useProfit(group: ProfitGroup, from: string, to: string) {
  return useQuery({
    queryKey: ["profit", group, from, to],
    enabled: from !== "" && to !== "",
    queryFn: () =>
      api<ProfitReport>(`/reports/profit?group=${group}&date_from=${from}&date_to=${to}`),
  });
}

export function useSegments(startYear: number | null) {
  return useQuery({
    queryKey: ["segments", startYear],
    queryFn: () =>
      api<SegmentReport>(
        `/reports/sales-by-segment${startYear === null ? "" : `?start_year=${startYear}`}`,
      ),
  });
}

/** FM8: profit for a month by brand, shop, user, item or customer (owner). */
export function useProfitability(period: string, by: Cut, locationId: string) {
  const where = locationId ? `&location_id=${locationId}` : "";
  return useQuery({
    queryKey: ["profitability", period, by, locationId],
    enabled: /^\d{4}-\d{2}$/.test(period),
    queryFn: () => api<Profitability>(`/reports/profitability?by=${by}&period=${period}${where}`),
  });
}

/** FM8: input tax in our books that GSTR-2B does not show (owner, accountant). */
export function useItcAtRisk(period: string) {
  return useQuery({
    queryKey: ["itc-at-risk", period],
    enabled: /^\d{4}-\d{2}$/.test(period),
    queryFn: () => api<ItcAtRisk>(`/gst/itc-at-risk?period=${period}`),
  });
}
