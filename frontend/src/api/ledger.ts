import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type {
  Dues,
  LedgerAccount,
  OpeningCreate,
  OpeningKind,
  OpeningRow,
  PostResult,
  Statement,
  StockItem,
  StockItemOwner,
} from "./types";

/** Opening balances, stock and party ledgers (Milestone 3). */

export type StockRow = StockItem | StockItemOwner;

export function useOpening() {
  return useQuery({ queryKey: ["opening"], queryFn: () => api<OpeningRow[]>("/opening") });
}

export function useCreateOpening() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: OpeningCreate) =>
      api<OpeningRow>("/opening", { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["opening"] }),
  });
}

export function useDeleteOpening() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<undefined>(`/opening/${id}`, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["opening"] }),
  });
}

export function usePostOpening() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (kinds: OpeningKind[]) =>
      api<PostResult>("/opening/post", { method: "POST", body: json({ kinds }) }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["opening"] });
      await client.invalidateQueries({ queryKey: ["stock"] });
      await client.invalidateQueries({ queryKey: ["statement"] });
      await client.invalidateQueries({ queryKey: ["dues"] });
    },
  });
}

export function useStock(q: string, locationId: string) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (locationId) params.set("location_id", locationId);
  return useQuery({
    queryKey: ["stock", q, locationId],
    queryFn: () => api<StockRow[]>(`/stock?${params.toString()}`),
  });
}

/** Every item, including those at zero: the dashboard and alerts use it to spot what has run out. */
export function useStockOverview(enabled = true) {
  return useQuery({
    queryKey: ["stock", "overview"],
    enabled,
    queryFn: () => api<StockRow[]>("/stock?include_zero=true"),
  });
}

export function useStatement(partyId: number, siteId?: number) {
  return useQuery({
    queryKey: ["statement", partyId, siteId ?? null],
    queryFn: () =>
      api<Statement>(`/parties/${partyId}/statement${siteId ? `?site_id=${siteId}` : ""}`),
  });
}

export function useDues(account: LedgerAccount) {
  return useQuery({
    queryKey: ["dues", account],
    queryFn: () => api<Dues>(`/reports/dues?account=${account}`),
  });
}
