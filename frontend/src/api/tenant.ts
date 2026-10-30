import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { Tenant } from "./types";

const KEY = ["tenant"];

/** The business name, tagline and logo address. Open to anyone, so the sign-in page can use it. */
export function useTenant() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => api<Tenant>("/tenant"),
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
