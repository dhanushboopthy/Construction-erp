import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type { Attachment, AttachmentKind, AttachmentRef, Scheme, SchemeCreate } from "./types";

/** Milestone 11: weighbridge slips and delivery proof (B17), supplier target schemes (B15). */

export function useAttachments(refType: AttachmentRef, refId: number) {
  return useQuery({
    queryKey: ["attachments", refType, refId],
    queryFn: () => api<Attachment[]>(`/attachments?ref_type=${refType}&ref_id=${refId}`),
  });
}

export function useUploadAttachment(refType: AttachmentRef, refId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ file, kind, note }: { file: File; kind: AttachmentKind; note: string }) => {
      const form = new FormData();
      form.set("ref_type", refType);
      form.set("ref_id", String(refId));
      form.set("kind", kind);
      if (note) form.set("note", note);
      form.set("file", file);
      return api<Attachment>("/attachments", { method: "POST", body: form });
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["attachments", refType, refId] }),
  });
}

export function useSchemes(alertsOnly = false, enabled = true) {
  return useQuery({
    queryKey: ["schemes", alertsOnly],
    enabled,
    queryFn: () => api<Scheme[]>(`/schemes?alerts_only=${alertsOnly}`),
  });
}

export function useCreateScheme() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: SchemeCreate) =>
      api<Scheme>("/schemes", { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["schemes"] }),
  });
}

export function useBookRebate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<Scheme>(`/schemes/${id}/book-rebate`, { method: "POST" }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["schemes"] });
      await client.invalidateQueries({ queryKey: ["statement"] });
      await client.invalidateQueries({ queryKey: ["dues"] });
    },
  });
}
