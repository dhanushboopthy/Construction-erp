import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type { TallyLedgers, TallyPreview } from "./types";

/** FM4: the Tally day-book export (owner and accountant). */

export function useTallyLedgers() {
  return useQuery({
    queryKey: ["tally-ledgers"],
    queryFn: () => api<TallyLedgers>("/tally/ledgers"),
  });
}

export function useSaveTallyLedgers() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { company: string | null; names: Record<string, string> }) =>
      api<TallyLedgers>("/tally/ledgers", { method: "PUT", body: json(body) }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["tally-ledgers"] });
      await client.invalidateQueries({ queryKey: ["tally-preview"] });
    },
  });
}

export function useTallyPreview(dateFrom: string, dateTo: string) {
  const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
  return useQuery({
    queryKey: ["tally-preview", dateFrom, dateTo],
    enabled: dateFrom !== "" && dateTo !== "" && dateFrom <= dateTo,
    queryFn: () => api<TallyPreview>(`/tally/preview?${params.toString()}`),
  });
}
