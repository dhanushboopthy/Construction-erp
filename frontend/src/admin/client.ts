import { createClient } from "@/api/client";

import type { AdminTokenResponse } from "./types";

/** The Duolink admin's own client: /api/v1/admin, signed in at /api/v1/admin/auth. Its token
 * is separate from a company user's, and the API refuses one in place of the other. */
export const adminClient = createClient<AdminTokenResponse>({
  base: "/api/v1/admin",
  authPrefix: "/auth/",
});

export const adminApi = adminClient.api;
