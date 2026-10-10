import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type {
  EInvoiceCreate,
  EInvoiceStatus,
  EwayBill,
  EwayCreate,
  EwayManual,
  EwayStatus,
  EwayVehicleUpdate,
  PendingEway,
} from "./types";

/** Milestone 10: e-way bills and e-invoices (IRN) through the GSP. */

export function useEwayStatus(invoiceId: number) {
  return useQuery({
    queryKey: ["eway", invoiceId],
    queryFn: () => api<EwayStatus>(`/invoices/${invoiceId}/eway-bill`),
  });
}

export function usePendingEway(enabled = true) {
  return useQuery({
    queryKey: ["eway", "pending"],
    enabled,
    queryFn: () => api<PendingEway[]>("/eway-bills/pending"),
  });
}

function useEwayMutation<T>(run: (invoiceId: number, body: T) => Promise<EwayBill>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ invoiceId, body }: { invoiceId: number; body: T }) => run(invoiceId, body),
    onSuccess: () => client.invalidateQueries({ queryKey: ["eway"] }),
  });
}

export const useCreateEway = () =>
  useEwayMutation<EwayCreate>((id, body) =>
    api<EwayBill>(`/invoices/${id}/eway-bill`, { method: "POST", body: json(body) }),
  );

export const useManualEway = () =>
  useEwayMutation<EwayManual>((id, body) =>
    api<EwayBill>(`/invoices/${id}/eway-bill/manual`, { method: "POST", body: json(body) }),
  );

export const useEwayVehicle = () =>
  useEwayMutation<EwayVehicleUpdate>((id, body) =>
    api<EwayBill>(`/invoices/${id}/eway-bill/vehicle`, { method: "POST", body: json(body) }),
  );

export const useCancelEway = () =>
  useEwayMutation<{ reason: string }>((id, body) =>
    api<EwayBill>(`/invoices/${id}/eway-bill/cancel`, { method: "POST", body: json(body) }),
  );

export function useEinvoiceStatus(invoiceId: number) {
  return useQuery({
    queryKey: ["einvoice", invoiceId],
    queryFn: () => api<EInvoiceStatus>(`/invoices/${invoiceId}/einvoice`),
  });
}

export function useCreateEinvoice() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ invoiceId, body }: { invoiceId: number; body: EInvoiceCreate }) =>
      api<unknown>(`/invoices/${invoiceId}/einvoice`, { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["einvoice"] }),
  });
}

export function useCancelEinvoice() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ invoiceId, reason }: { invoiceId: number; reason: string }) =>
      api<unknown>(`/invoices/${invoiceId}/einvoice/cancel`, {
        method: "POST",
        body: json({ reason }),
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["einvoice"] }),
  });
}
