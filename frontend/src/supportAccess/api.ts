import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "@/api/client";
import type {
  AccessGrant,
  AccessOverview,
  GrantCreate,
  SupportVisit,
  SupportVisitEvent,
} from "@/api/types";

/** How often the owner's countdown asks the server again. */
export const ACCESS_POLL_MS = 30_000;

const keys = {
  all: ["support-access"] as const,
  overview: ["support-access", "overview"] as const,
  visits: ["support-access", "visits"] as const,
  events: (id: number) => ["support-access", "events", id] as const,
};

export function useAccessOverview() {
  return useQuery({
    queryKey: keys.overview,
    queryFn: () => api<AccessOverview>("/support-access"),
    refetchInterval: ACCESS_POLL_MS,
  });
}

export function useVisits() {
  return useQuery({
    queryKey: keys.visits,
    queryFn: () => api<SupportVisit[]>("/support-access/sessions"),
    refetchInterval: ACCESS_POLL_MS,
  });
}

export function useVisitEvents(id: number | null) {
  return useQuery({
    queryKey: keys.events(id ?? 0),
    queryFn: () => api<SupportVisitEvent[]>(`/support-access/sessions/${id}/events`),
    enabled: id !== null,
  });
}

export function useGrantAccess() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: GrantCreate) =>
      api<AccessGrant>("/support-access/grants", { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.all }),
  });
}

export function useRevokeAccess() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<AccessGrant>("/support-access/revoke", { method: "POST" }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.all }),
  });
}
