import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type {
  Conversion,
  ImportResult,
  Item,
  ItemCreate,
  ItemOwner,
  ItemUpdate,
  Page,
  Party,
  PartyCreate,
  PartyUpdate,
  Site,
  SiteCreate,
  SiteUpdate,
} from "./types";

/** Milestone 2: item master, parties and sites. */

export type ItemRow = Item | ItemOwner;

export function useItems(q: string, category: string) {
  const params = new URLSearchParams({ limit: "200", include_inactive: "true" });
  if (q) params.set("q", q);
  if (category) params.set("category", category);
  return useQuery({
    queryKey: ["items", q, category],
    queryFn: () => api<Page<ItemRow>>(`/items?${params.toString()}`),
  });
}

export function useCreateItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ItemCreate) =>
      api<ItemOwner>("/items", { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["items"] }),
  });
}

export function useUpdateItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: ItemUpdate }) =>
      api<ItemOwner>(`/items/${id}`, { method: "PATCH", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["items"] }),
  });
}

export function useImportItems() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ file, dryRun }: { file: File; dryRun: boolean }) => {
      const form = new FormData();
      form.append("file", file);
      return api<ImportResult>(`/items/import?dry_run=${dryRun}`, { method: "POST", body: form });
    },
    onSuccess: (result) => {
      if (!result.dry_run) void client.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function convertQuantity(
  itemId: number,
  quantity: string,
  fromUnit: string,
  toUnit: string,
): Promise<Conversion> {
  const params = new URLSearchParams({ quantity, from_unit: fromUnit, to_unit: toUnit });
  return api<Conversion>(`/items/${itemId}/convert?${params.toString()}`);
}

export function useParties(q: string, kind: string) {
  const params = new URLSearchParams({ limit: "200", include_inactive: "true" });
  if (q) params.set("q", q);
  if (kind) params.set("kind", kind);
  return useQuery({
    queryKey: ["parties", q, kind],
    queryFn: () => api<Page<Party>>(`/parties?${params.toString()}`),
  });
}

export function useCreateParty() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: PartyCreate) => api<Party>("/parties", { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["parties"] }),
  });
}

export function useUpdateParty() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: PartyUpdate }) =>
      api<Party>(`/parties/${id}`, { method: "PATCH", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["parties"] }),
  });
}

export function useAddSite() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ partyId, body }: { partyId: number; body: SiteCreate }) =>
      api<Site>(`/parties/${partyId}/sites`, { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["parties"] }),
  });
}

export function useUpdateSite() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: SiteUpdate }) =>
      api<Site>(`/sites/${id}`, { method: "PATCH", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["parties"] }),
  });
}
