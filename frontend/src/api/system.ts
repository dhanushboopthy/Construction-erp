import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "./client";
import type { SystemStatus, VerifyResult } from "./types";

/** Milestone 14: is the system healthy, and do the books add up. */
export function useSystemStatus() {
  return useQuery({
    queryKey: ["system", "status"],
    queryFn: () => api<SystemStatus>("/system/status"),
  });
}

export function useVerify() {
  return useMutation({
    mutationFn: (full: boolean) =>
      api<VerifyResult>(`/system/verify?full=${full}`, { method: "POST" }),
  });
}
