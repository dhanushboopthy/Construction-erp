import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type {
  Adjustment,
  AdjustmentBook,
  AdjustmentBookOwner,
  AdjustmentCreate,
  AdjustmentOwner,
  ItcReversal,
} from "./types";

/** FM2: stock adjustments with a reason, and the ITC to reverse on goods lost. */

export function useAdjustments(locationId: string, dateFrom: string, dateTo: string) {
  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  if (locationId) params.set("location_id", locationId);
  return useQuery({
    queryKey: ["stock-adjustments", locationId, dateFrom, dateTo],
    queryFn: () => api<AdjustmentBook | AdjustmentBookOwner>(`/stock-adjustments?${params}`),
  });
}

export function useCreateAdjustment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: AdjustmentCreate) =>
      api<Adjustment | AdjustmentOwner>("/stock-adjustments", {
        method: "POST",
        body: json(body),
      }),
    onSuccess: async () => {
      for (const k of ["stock-adjustments", "stock", "pnl", "itc-reversal"])
        await client.invalidateQueries({ queryKey: [k] });
    },
  });
}

export function useItcReversal(period: string) {
  return useQuery({
    queryKey: ["itc-reversal", period],
    enabled: /^\d{4}-\d{2}$/.test(period),
    queryFn: () => api<ItcReversal>(`/reports/itc-reversal?period=${period}`),
  });
}
