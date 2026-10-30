import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { Tenant } from "./types";

const KEY = ["tenant"];

/**
 * The company this address (subdomain) belongs to, with its business name, tagline and logo
 * address. Open to anyone, so the sign-in page can use it. No retry: an unknown or closed company
 * answers 404 or 403 at once (ADR 0011).
 */
export function useTenant() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => api<Tenant>("/tenant"),
    retry: false,
    staleTime: 5 * 60_000,
  });
}

/** Owner only. Replaces the logo and updates the sidebar straight away. */
export function useUploadLogo() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api<Tenant>("/tenant/logo", { method: "PUT", body: form });
    },
    onSuccess: (data) => client.setQueryData(KEY, data),
  });
}

/** Owner only. Back to the initials tile. */
export function useRemoveLogo() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<Tenant>("/tenant/logo", { method: "DELETE" }),
    onSuccess: (data) => client.setQueryData(KEY, data),
  });
}
