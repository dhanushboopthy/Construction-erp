import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type { ShortcutItem, ShortcutsOut } from "./types";

/** A user's own keyboard shortcuts (only what they changed; the defaults live in the app). */

const KEY = ["my-shortcuts"];

export function useMyShortcuts(enabled = true) {
  return useQuery({
    queryKey: KEY,
    enabled,
    queryFn: () => api<ShortcutsOut>("/me/shortcuts"),
    staleTime: Infinity,
  });
}

export function useSaveShortcuts() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (items: ShortcutItem[]) =>
      api<ShortcutsOut>("/me/shortcuts", { method: "PUT", body: json({ items }) }),
    onSuccess: (saved) => client.setQueryData(KEY, saved),
  });
}
