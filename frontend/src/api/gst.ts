import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { Gstr1, Gstr2bResult, Gstr3b } from "./types";

/** Milestone 13: GST return data for the accountant. */

export function useGstr1(period: string) {
  return useQuery({
    queryKey: ["gst", "gstr1", period],
    enabled: period !== "",
    queryFn: () => api<Gstr1>(`/gst/gstr1?period=${period}`),
  });
}

export function useGstr3b(period: string) {
  return useQuery({
    queryKey: ["gst", "gstr3b", period],
    enabled: period !== "",
    queryFn: () => api<Gstr3b>(`/gst/gstr3b?period=${period}`),
  });
}

export function useGstr2b(period: string) {
  return useQuery({
    queryKey: ["gst", "gstr2b", period],
    enabled: period !== "",
    queryFn: () => api<Gstr2bResult>(`/gst/gstr2b?period=${period}`),
  });
}

export function useUpload2b(period: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.set("period", period);
      form.set("file", file);
      return api<unknown>("/gst/gstr2b", { method: "POST", body: form });
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["gst"] }),
  });
}
