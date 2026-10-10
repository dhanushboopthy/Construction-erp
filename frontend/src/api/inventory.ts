import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type {
  FifoAge,
  InventoryAnalytics,
  NrvReport,
  Shrinkage,
  Writedown,
  WritedownCreate,
} from "./types";

/** FM6: stock analysis, stock value against the market, cement age and weight shortages. */

export function useInventoryAnalytics() {
  return useQuery({
    queryKey: ["inventory-analytics"],
    queryFn: () => api<InventoryAnalytics>("/inventory/analytics"),
  });
}

export function useFifoAge() {
  return useQuery({
    queryKey: ["inventory-fifo"],
    queryFn: () => api<FifoAge>("/inventory/fifo-age"),
  });
}

export function useNrv() {
  return useQuery({ queryKey: ["inventory-nrv"], queryFn: () => api<NrvReport>("/inventory/nrv") });
}

export function useWritedowns() {
  return useQuery({
    queryKey: ["inventory-writedowns"],
    queryFn: () => api<Writedown[]>("/inventory/writedowns"),
  });
}

export function useCreateWritedown() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: WritedownCreate) =>
      api<Writedown>("/inventory/writedowns", { method: "POST", body: json(body) }),
    onSuccess: async () => {
      for (const key of [
        "inventory-nrv",
        "inventory-writedowns",
        "inventory-analytics",
        "pnl",
        "stock",
      ])
        await client.invalidateQueries({ queryKey: [key] });
    },
  });
}

export function useShrinkage(dateFrom: string, dateTo: string) {
  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  return useQuery({
    queryKey: ["inventory-shrinkage", dateFrom, dateTo],
    queryFn: () => api<Shrinkage>(`/inventory/shrinkage?${params.toString()}`),
  });
}
