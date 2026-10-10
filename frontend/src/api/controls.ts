import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type {
  AuditAction,
  AuditLogRow,
  BankAccount,
  BankStatement,
  ExceptionReport,
  Page,
  PeriodChecklist,
  PeriodLock,
  PeriodLockSet,
  Reconciliation,
} from "./types";

/** FM7: the period lock, bank statements and the owner's exception report. */

export function usePeriodLock() {
  return useQuery({ queryKey: ["period-lock"], queryFn: () => api<PeriodLock>("/period-lock") });
}

export function useSetPeriodLock() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: PeriodLockSet) =>
      api<PeriodLock>("/period-lock", { method: "PUT", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["period-lock"] }),
  });
}

export function useChecklist(period: string) {
  return useQuery({
    queryKey: ["period-lock", "checklist", period],
    enabled: /^\d{4}-\d{2}$/.test(period),
    queryFn: () => api<PeriodChecklist>(`/period-lock/checklist?period=${period}`),
  });
}

export function useBankAccounts() {
  return useQuery({
    queryKey: ["bank", "accounts"],
    queryFn: () => api<BankAccount[]>("/bank/accounts"),
  });
}

export function useCreateBankAccount() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string }) =>
      api<BankAccount>("/bank/accounts", { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["bank"] }),
  });
}

export function useStatements() {
  return useQuery({
    queryKey: ["bank", "statements"],
    queryFn: () => api<BankStatement[]>("/bank/statements"),
  });
}

export function useUploadStatement() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ accountId, file }: { accountId: number; file: File }) => {
      const form = new FormData();
      form.set("bank_account_id", String(accountId));
      form.set("file", file);
      return api<BankStatement>("/bank/statements", { method: "POST", body: form });
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["bank"] }),
  });
}

export function useReconciliation(dateFrom: string, dateTo: string) {
  return useQuery({
    queryKey: ["bank", "reconciliation", dateFrom, dateTo],
    enabled: dateFrom !== "" && dateTo !== "",
    queryFn: () =>
      api<Reconciliation>(`/bank/reconciliation?date_from=${dateFrom}&date_to=${dateTo}`),
  });
}

export function useExceptions(dateFrom: string, dateTo: string) {
  return useQuery({
    queryKey: ["exceptions", dateFrom, dateTo],
    enabled: dateFrom !== "" && dateTo !== "",
    queryFn: () =>
      api<ExceptionReport>(`/reports/exceptions?date_from=${dateFrom}&date_to=${dateTo}`),
  });
}

export interface AuditFilter {
  entity: string;
  action: AuditAction | "";
  userId: string;
  since: string;
  until: string;
  offset: number;
}

export function useAuditLog(f: AuditFilter, limit = 50) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(f.offset) });
  if (f.entity) params.set("entity", f.entity);
  if (f.action) params.set("action", f.action);
  if (f.userId) params.set("user_id", f.userId);
  if (f.since) params.set("since", `${f.since}T00:00:00+05:30`);
  if (f.until) {
    const end = new Date(`${f.until}T00:00:00+05:30`);
    end.setDate(end.getDate() + 1); // the whole of the last day
    params.set("until", end.toISOString());
  }
  return useQuery({
    queryKey: ["audit-log", f, limit],
    queryFn: () => api<Page<AuditLogRow>>(`/audit-log?${params}`),
  });
}
