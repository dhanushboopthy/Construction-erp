import { useMutation } from "@tanstack/react-query";

import { api, json } from "./client";
import type { ApprovalAction, ApprovalOut } from "./types";

/** Owner PIN approvals (G18). */
export function useRequestApproval() {
  return useMutation({
    mutationFn: (body: {
      pin: string;
      action: ApprovalAction;
      reason: string;
      party_id: number | null;
    }) => api<ApprovalOut>("/approvals", { method: "POST", body: json(body) }),
  });
}

export function useSetPin() {
  return useMutation({
    mutationFn: (body: { current_password: string; pin: string }) =>
      api<undefined>("/auth/pin", { method: "POST", body: json(body) }),
  });
}
