import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type {
  CustomerRate,
  CustomerRateCreate,
  MarginOut,
  MarketRatesResult,
  RateRow,
  RateRowOwner,
} from "./types";

/** Milestone 5: daily market rates, customer rates and margins (owner screens). */

export type BoardRow = RateRow | RateRowOwner;

export function useRateBoard(on: string) {
  return useQuery({
    queryKey: ["rate-board", on],
    queryFn: () => api<BoardRow[]>(`/rates/market?on=${on}`),
  });
}

export function useSaveRates() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (args: {
      date: string;
      rates: { item_id: number; rate: string; unit: string }[];
      margins: { item_id: number; margin: string; unit: string }[];
    }) => {
      if (args.margins.length > 0) {
        await api<MarginOut[]>("/margins", { method: "PUT", body: json(args.margins) });
      }
      if (args.rates.length === 0) return { saved: 0, warnings: [] } as MarketRatesResult;
      return api<MarketRatesResult>("/rates/market", {
        method: "PUT",
        body: json({ effective_date: args.date, rates: args.rates }),
      });
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["rate-board"] }),
  });
}

export function useCustomerRates() {
  return useQuery({
    queryKey: ["customer-rates"],
    queryFn: () => api<CustomerRate[]>("/customer-rates"),
  });
}

export function useCreateCustomerRate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CustomerRateCreate) =>
      api<CustomerRate>("/customer-rates", { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["customer-rates"] }),
  });
}

export function useEndCustomerRate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number;
      body: { valid_to?: string | null; is_active?: boolean };
    }) => api<CustomerRate>(`/customer-rates/${id}`, { method: "PATCH", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["customer-rates"] }),
  });
}
