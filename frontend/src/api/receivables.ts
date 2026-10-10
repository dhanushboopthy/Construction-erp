import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type {
  Receivables,
  ReceivablesOwner,
  WorkingCapital,
  Writeoff,
  WriteoffCreate,
} from "./types";

/** FM5: receivables by due date, bad-debt write-offs and working capital. */

export function useReceivables() {
  return useQuery({
    queryKey: ["receivables"],
    queryFn: () => api<Receivables | ReceivablesOwner>("/reports/receivables"),
  });
}

export function useWriteoffs() {
  return useQuery({
    queryKey: ["write-offs"],
    queryFn: () => api<Writeoff[]>("/write-offs"),
  });
}

export function useCreateWriteoff() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: WriteoffCreate) =>
      api<Writeoff>("/write-offs", { method: "POST", body: json(body) }),
    onSuccess: async () => {
      for (const key of ["write-offs", "receivables", "pnl", "dues", "working-capital"])
        await client.invalidateQueries({ queryKey: [key] });
    },
  });
}

/** `trend` off for the Today card, which needs one month only. */
export function useWorkingCapital(
  period: string,
  options: { trend?: boolean; enabled?: boolean } = {},
) {
  const trend = options.trend ?? true;
  return useQuery({
    queryKey: ["working-capital", period, trend],
    enabled: (options.enabled ?? true) && /^\d{4}-\d{2}$/.test(period),
    queryFn: () => api<WorkingCapital>(`/reports/working-capital?period=${period}&trend=${trend}`),
  });
}
