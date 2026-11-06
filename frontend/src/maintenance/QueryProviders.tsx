import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { MaintenanceGate } from "./MaintenanceGate";

/** The company app's data layer, behind the "Back soon" gate (Milestone 24): while Duolink is in
 * maintenance nothing below it is shown, so no screen runs into the 503s. */
export function QueryProviders({ client, children }: { client: QueryClient; children: ReactNode }) {
  return (
    <QueryClientProvider client={client}>
      <MaintenanceGate>{children}</MaintenanceGate>
    </QueryClientProvider>
  );
}
