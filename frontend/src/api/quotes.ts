import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type { InvoicePreview, Page, Quote, QuoteCreate, QuoteKind, QuoteSummary } from "./types";

/** Quotations and proforma invoices: priced like a bill, no stock or account effect. */

export const QUOTE_LABEL: Record<QuoteKind, string> = {
  quotation: "Quotation",
  proforma: "Proforma invoice",
};

export function useQuotes(kind: QuoteKind | "", q: string) {
  const params = new URLSearchParams({ limit: "100" });
  if (kind) params.set("kind", kind);
  if (q) params.set("q", q);
  return useQuery({
    queryKey: ["quotes", kind, q],
    queryFn: () => api<Page<QuoteSummary>>(`/quotes?${params.toString()}`),
  });
}

export function useQuote(id: number | null) {
  return useQuery({
    queryKey: ["quote", id],
    enabled: id !== null,
    queryFn: () => api<Quote>(`/quotes/${id}`),
  });
}

export function previewQuote(body: QuoteCreate): Promise<InvoicePreview> {
  return api<InvoicePreview>("/quotes/preview", { method: "POST", body: json(body) });
}

export function useCreateQuote() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: QuoteCreate) => api<Quote>("/quotes", { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["quotes"] }),
  });
}
