import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import type { Tenant } from "./types";

/** The business name and tagline for the sidebar. Any signed-in role may read it. */
export function useTenant() {
  return useQuery({
    queryKey: ["tenant"],
    queryFn: () => api<Tenant>("/tenant"),
    staleTime: 5 * 60_000,
  });
}
