import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type {
  CreditNote,
  CreditNoteCreate,
  CreditNoteSummary,
  DebitNote,
  DebitNoteCreate,
  DebitNoteSummary,
  Page,
} from "./types";

/** Milestone 8: credit notes (customer returns) and debit notes (returns to a supplier). */

export function useCreditNotes(invoiceId: number | null) {
  return useQuery({
    queryKey: ["credit-notes", invoiceId],
    enabled: invoiceId !== null,
    queryFn: () => api<Page<CreditNoteSummary>>(`/credit-notes?invoice_id=${invoiceId}`),
  });
}

export function useCreateCreditNote() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CreditNoteCreate) =>
      api<CreditNote>("/credit-notes", { method: "POST", body: json(body) }),
    onSuccess: async () => {
      for (const key of ["credit-notes", "invoice", "stock", "statement", "dues"]) {
        await client.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export function useDebitNotes(purchaseId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ["debit-notes", purchaseId],
    enabled: enabled && purchaseId !== null,
    queryFn: () => api<Page<DebitNoteSummary>>(`/debit-notes?purchase_id=${purchaseId}`),
  });
}

export function useCreateDebitNote() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: DebitNoteCreate) =>
      api<DebitNote>("/debit-notes", { method: "POST", body: json(body) }),
    onSuccess: async () => {
      for (const key of ["debit-notes", "stock", "statement", "dues", "purchases"]) {
        await client.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}
