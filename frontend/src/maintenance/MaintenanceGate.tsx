import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";

import { api } from "@/api/client";

import styles from "./Maintenance.module.css";

export interface MaintenanceNotice {
  enabled: boolean;
  message: string | null;
}

/** How often a closed screen asks again whether Duolink has finished (Milestone 24). */
export const MAINTENANCE_RETRY_MS = 30_000;
export const MAINTENANCE_EVENT = "erp:maintenance";
/** Sent when a call is answered 403 TENANT_RESTORING: this company is being restored (M25). */
export const RESTORING_EVENT = "erp:restoring";

/** Ask a route that needs the company: still 403 TENANT_RESTORING, or has it finished? */
async function stillRestoring(): Promise<boolean> {
  try {
    await api("/auth/me");
    return false;
  } catch (error) {
    const body = (error as { body?: { code?: string } }).body;
    return body?.code === "TENANT_RESTORING";
  }
}

/**
 * Shows a full-page "Back soon" screen while Duolink has put the platform into maintenance, and
 * the app again as soon as it is over. It asks the open `GET /maintenance` every 30 seconds, and
 * at once when any call is answered 503 MAINTENANCE. If the question itself fails, the app is
 * shown: the server, not this screen, refuses the work.
 *
 * A company that is being restored from a backup answers 403 TENANT_RESTORING; the same screen
 * says so and checks again every 30 seconds. Everyone signs in again afterwards.
 */
export function MaintenanceGate({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const [restoring, setRestoring] = useState(false);
  const notice = useQuery({
    queryKey: ["maintenance"],
    queryFn: () => api<MaintenanceNotice>("/maintenance"),
    refetchInterval: MAINTENANCE_RETRY_MS,
    retry: false,
  });

  useEffect(() => {
    const refresh = () => void client.invalidateQueries({ queryKey: ["maintenance"] });
    const onRestoring = () => setRestoring(true);
    window.addEventListener(MAINTENANCE_EVENT, refresh);
    window.addEventListener(RESTORING_EVENT, onRestoring);
    return () => {
      window.removeEventListener(MAINTENANCE_EVENT, refresh);
      window.removeEventListener(RESTORING_EVENT, onRestoring);
    };
  }, [client]);

  useEffect(() => {
    if (!restoring) return;
    const timer = setInterval(() => {
      void stillRestoring().then((still) => {
        if (!still) {
          setRestoring(false);
          void client.invalidateQueries();
        }
      });
    }, MAINTENANCE_RETRY_MS);
    return () => clearInterval(timer);
  }, [restoring, client]);

  if (restoring) {
    return (
      <main className={styles.screen} aria-labelledby="maintenance-title">
        <h1 id="maintenance-title" className={styles.title}>
          Back soon: restoring from a backup
        </h1>
        <p className={styles.note} role="status">
          Duolink is restoring your company&apos;s data from a backup. You will need to sign in
          again afterwards. This page checks again every 30 seconds.
        </p>
      </main>
    );
  }
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
