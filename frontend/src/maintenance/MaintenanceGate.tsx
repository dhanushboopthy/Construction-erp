import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, type ReactNode } from "react";

import { api } from "@/api/client";

import styles from "./Maintenance.module.css";

export interface MaintenanceNotice {
  enabled: boolean;
  message: string | null;
}

/** How often a closed screen asks again whether Duolink has finished (Milestone 24). */
export const MAINTENANCE_RETRY_MS = 30_000;
export const MAINTENANCE_EVENT = "erp:maintenance";

/**
 * Shows a full-page "Back soon" screen while Duolink has put the platform into maintenance, and
 * the app again as soon as it is over. It asks the open `GET /maintenance` every 30 seconds, and
 * at once when any call is answered 503 MAINTENANCE. If the question itself fails, the app is
 * shown: the server, not this screen, refuses the work.
 */
export function MaintenanceGate({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const notice = useQuery({
    queryKey: ["maintenance"],
    queryFn: () => api<MaintenanceNotice>("/maintenance"),
    refetchInterval: MAINTENANCE_RETRY_MS,
    retry: false,
  });

  useEffect(() => {
    const refresh = () => void client.invalidateQueries({ queryKey: ["maintenance"] });
    window.addEventListener(MAINTENANCE_EVENT, refresh);
    return () => window.removeEventListener(MAINTENANCE_EVENT, refresh);
  }, [client]);

  if (!notice.data?.enabled) return children;
  return (
    <main className={styles.screen} aria-labelledby="maintenance-title">
      <h1 id="maintenance-title" className={styles.title}>
        Back soon{notice.data.message ? `: ${notice.data.message}` : ""}
      </h1>
      <p className={styles.note} role="status">
        Duolink is doing maintenance. Your work is safe. This page checks again every 30 seconds.
      </p>
    </main>
  );
}
