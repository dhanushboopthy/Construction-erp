import { useEffect } from "react";

import { usePendingEway } from "@/api/compliance";
import { useStockOverview } from "@/api/ledger";

/**
 * What needs attention now: items with no stock anywhere and e-way bills still to be made. The
 * count loads once with the screen (for the sidebar badge and the bell's dot) and is fetched
 * again each time the alerts panel is opened.
 */
export function useAlerts(panelOpen: boolean) {
  const stock = useStockOverview();
  const eway = usePendingEway();
  const { refetch: refetchStock } = stock;
  const { refetch: refetchEway } = eway;

  useEffect(() => {
    if (!panelOpen) return;
    void refetchStock();
    void refetchEway();
  }, [panelOpen, refetchStock, refetchEway]);

  const outOfStock = (stock.data ?? []).filter((s) => Number(s.quantity) <= 0);
  const pending = eway.data ?? [];
  return {
    outOfStock,
    pending,
    count: outOfStock.length + pending.length,
    loading: stock.isLoading || eway.isLoading,
    failed: stock.isError && eway.isError,
  };
}

export type Alerts = ReturnType<typeof useAlerts>;
