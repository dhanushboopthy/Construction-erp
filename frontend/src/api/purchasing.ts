import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type {
  CostComponent,
  CostComponentCreate,
  Page,
  PaymentCreate,
  PaymentOut,
  Purchase,
  PurchaseCreate,
  PurchaseOwner,
  PurchasePreview,
  StockCount,
  StockCountOwner,
  Transfer,
  TransferCreate,
} from "./types";

/** Milestone 4: purchases with landed cost, supplier payments, transfers and stock counts. */

export type PurchaseRow = Purchase | PurchaseOwner;
export type CountRow = StockCount | StockCountOwner;

export function useCostComponents(includeInactive = false) {
  return useQuery({
    queryKey: ["cost-components", includeInactive],
    queryFn: () =>
      api<CostComponent[]>(`/cost-components${includeInactive ? "?include_inactive=true" : ""}`),
  });
}

export function useCreateComponent() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CostComponentCreate) =>
      api<CostComponent>("/cost-components", { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["cost-components"] }),
  });
}

export function useUpdateComponent() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<CostComponent> }) =>
      api<CostComponent>(`/cost-components/${id}`, { method: "PATCH", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["cost-components"] }),
  });
}

export function usePurchases() {
  return useQuery({
    queryKey: ["purchases"],
    queryFn: () => api<Page<PurchaseRow>>("/purchases?limit=200"),
  });
}

export function useCreatePurchase() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: PurchaseCreate) =>
      api<PurchaseRow>("/purchases", { method: "POST", body: json(body) }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["purchases"] });
      await client.invalidateQueries({ queryKey: ["stock"] });
      await client.invalidateQueries({ queryKey: ["statement"] });
    },
  });
}

export function previewPurchase(body: PurchaseCreate): Promise<PurchasePreview> {
  return api<PurchasePreview>("/purchases/preview", { method: "POST", body: json(body) });
}

export function useSupplierPayment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ body, key }: { body: PaymentCreate; key: string }) =>
      api<PaymentOut>("/payments", {
        method: "POST",
        body: json(body),
        headers: { "Idempotency-Key": key },
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["statement"] });
      await client.invalidateQueries({ queryKey: ["dues"] });
    },
  });
}

export function useTransfers() {
  return useQuery({ queryKey: ["transfers"], queryFn: () => api<Transfer[]>("/transfers") });
}

export function useCreateTransfer() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: TransferCreate) =>
      api<Transfer>("/transfers", { method: "POST", body: json(body) }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["transfers"] });
      await client.invalidateQueries({ queryKey: ["stock"] });
    },
  });
}

export function useCounts() {
  return useQuery({ queryKey: ["counts"], queryFn: () => api<CountRow[]>("/stock-counts") });
}

export function useOpenCount() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { location_id: number; item_ids?: number[]; note?: string }) =>
      api<CountRow>("/stock-counts", { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["counts"] }),
  });
}

export function useEnterCounts() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      lines,
    }: {
      id: number;
      lines: { item_id: number; counted_qty: string | null }[];
    }) => api<CountRow>(`/stock-counts/${id}/lines`, { method: "PUT", body: json({ lines }) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["counts"] }),
  });
}

export function usePostCount() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      api<StockCountOwner>(`/stock-counts/${id}/post`, { method: "POST" }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["counts"] });
      await client.invalidateQueries({ queryKey: ["stock"] });
    },
  });
}
