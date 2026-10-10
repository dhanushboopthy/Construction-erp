import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type {
  FillRateReport,
  LostSale,
  LostSaleCreate,
  MatchReport,
  OrderCreate,
  PurchaseOrderRow,
  ReceiptCreate,
} from "./types";

/** FM10: purchase orders, goods received, the bill match report, the lost-sales log. */

export function useOrders(openOnly = false, supplierId = "") {
  const params = new URLSearchParams();
  if (openOnly) params.set("open_only", "true");
  if (supplierId) params.set("supplier_id", supplierId);
  return useQuery({
    queryKey: ["orders", openOnly, supplierId],
    queryFn: () => api<PurchaseOrderRow[]>(`/purchase-orders?${params}`),
  });
}

export function useCreateOrder() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: OrderCreate) =>
      api<PurchaseOrderRow>("/purchase-orders", { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["orders"] }),
  });
}

export function useReceiveGoods() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, body }: { orderId: number; body: ReceiptCreate }) =>
      api<{ number: string }>(`/purchase-orders/${orderId}/receipts`, {
        method: "POST",
        body: json(body),
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["orders"] }),
  });
}

export function useMatchReport(dateFrom: string, dateTo: string, all: boolean) {
  return useQuery({
    queryKey: ["match-report", dateFrom, dateTo, all],
    enabled: dateFrom !== "" && dateTo !== "",
    queryFn: () =>
      api<MatchReport>(
        `/reports/match-exceptions?date_from=${dateFrom}&date_to=${dateTo}${all ? "&all_lines=true" : ""}`,
      ),
  });
}

export function useLostSales() {
  return useQuery({ queryKey: ["lost-sales"], queryFn: () => api<LostSale[]>("/lost-sales") });
}

export function useLogLostSale() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: LostSaleCreate) =>
      api<LostSale>("/lost-sales", { method: "POST", body: json(body) }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["lost-sales"] });
      await client.invalidateQueries({ queryKey: ["fill-rate"] });
    },
  });
}

export function useFillRate(period: string) {
  return useQuery({
    queryKey: ["fill-rate", period],
    enabled: /^\d{4}-\d{2}$/.test(period),
    queryFn: () => api<FillRateReport>(`/reports/fill-rate?period=${period}`),
  });
}
