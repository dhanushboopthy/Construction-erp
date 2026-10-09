import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type { OpenBills, PaymentCreate, PaymentOut } from "./types";

/** Milestone 7: receipts from customers (and payments to suppliers). */

export function usePayments() {
  return useQuery({ queryKey: ["payments"], queryFn: () => api<PaymentOut[]>("/payments") });
}

export function useOpenBills(partyId: number | null, account: "receivable" | "payable") {
  return useQuery({
    queryKey: ["open-bills", partyId, account],
    enabled: partyId !== null,
    queryFn: () => api<OpenBills>(`/parties/${partyId}/open-bills?account=${account}`),
  });
}

export function useRecordPayment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ body, key }: { body: PaymentCreate; key: string }) =>
      api<PaymentOut>("/payments", {
        method: "POST",
        body: json(body),
        headers: { "Idempotency-Key": key },
      }),
    onSuccess: async () => {
      for (const k of ["payments", "open-bills", "statement", "dues"])
        await client.invalidateQueries({ queryKey: [k] });
    },
  });
}
