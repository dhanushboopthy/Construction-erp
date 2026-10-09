import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type {
  Invoice,
  InvoiceCreate,
  InvoiceOwner,
  InvoicePreview,
  InvoiceSummary,
  Page,
} from "./types";

/** Milestone 6: sales invoices. */

export type InvoiceFull = Invoice | InvoiceOwner;
export type SalesInvoiceFull = InvoiceFull;

export function useInvoices(q: string) {
  const params = new URLSearchParams({ limit: "100" });
  if (q) params.set("q", q);
  return useQuery({
    queryKey: ["invoices", q],
    queryFn: () => api<Page<InvoiceSummary>>(`/invoices?${params.toString()}`),
  });
}

export function useInvoice(id: number | null) {
  return useQuery({
    queryKey: ["invoice", id],
    enabled: id !== null,
    queryFn: () => api<InvoiceFull>(`/invoices/${id}`),
  });
}

export function previewInvoice(body: InvoiceCreate): Promise<InvoicePreview> {
  return api<InvoicePreview>("/invoices/preview", { method: "POST", body: json(body) });
}

export function useCreateInvoice() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ body, key }: { body: InvoiceCreate; key: string }) =>
      api<InvoiceFull>("/invoices", {
        method: "POST",
        body: json(body),
        headers: { "Idempotency-Key": key },
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["invoices"] });
      await client.invalidateQueries({ queryKey: ["stock"] });
      await client.invalidateQueries({ queryKey: ["statement"] });
      await client.invalidateQueries({ queryKey: ["dues"] });
    },
  });
}
