import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "@/api/client";

import type { NewTicket, TicketDetail, TicketList } from "./types";

export const UNREAD_POLL_MS = 60_000;

const keys = {
  all: ["support"] as const,
  list: (status: string) => ["support", "list", status] as const,
  one: (id: number) => ["support", "ticket", id] as const,
  unread: ["support", "unread"] as const,
};

export function useTickets(status: string) {
  return useQuery({
    queryKey: keys.list(status),
    queryFn: () => api<TicketList>(`/support/tickets${status ? `?status=${status}` : ""}`),
    placeholderData: keepPreviousData,
  });
}

export function useTicket(id: number) {
  return useQuery({
    queryKey: keys.one(id),
    queryFn: () => api<TicketDetail>(`/support/tickets/${id}`),
  });
}

/** How many tickets have an answer from Duolink not yet read. Asked again every minute. */
export function useUnreadTickets() {
  return useQuery({
    queryKey: keys.unread,
    queryFn: () => api<{ unread: number }>("/support/tickets/unread-count"),
    refetchInterval: UNREAD_POLL_MS,
    retry: false,
  });
}

function useAfterChange() {
  const client = useQueryClient();
  return (detail: TicketDetail) => {
    client.setQueryData(keys.one(detail.id), detail);
    void client.invalidateQueries({ queryKey: keys.all });
  };
}

export function useCreateTicket() {
  const after = useAfterChange();
  return useMutation({
    mutationFn: (body: NewTicket) =>
      api<TicketDetail>("/support/tickets", { method: "POST", body: json(body) }),
    onSuccess: after,
  });
}

export function useReplyToTicket(id: number) {
  const after = useAfterChange();
  return useMutation({
    mutationFn: (body: string) =>
      api<TicketDetail>(`/support/tickets/${id}/reply`, {
        method: "POST",
        body: json({ body }),
      }),
    onSuccess: after,
  });
}

export function useCloseTicket(id: number) {
  const after = useAfterChange();
  return useMutation({
    mutationFn: () => api<TicketDetail>(`/support/tickets/${id}/close`, { method: "POST" }),
    onSuccess: after,
  });
}
