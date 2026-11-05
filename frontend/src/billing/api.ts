import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "@/api/client";

import type { CheckoutAnswer, RenewalOrder, RenewalOverview, RenewalResult } from "./types";

const OVERVIEW = ["subscription"] as const;

/** Owner only. The plan, its end, and the prices that can be paid online now. */
export function useRenewalOverview(enabled = true) {
  return useQuery({
    queryKey: OVERVIEW,
    queryFn: () => api<RenewalOverview>("/subscription"),
    retry: false,
    enabled,
  });
}

/** Ask the server for a Razorpay order. Only the price is sent: the amount is the server's. */
export function useCreateOrder() {
  return useMutation({
    mutationFn: (priceId: number) =>
      api<RenewalOrder>("/subscription/orders", {
        method: "POST",
        body: json({ price_id: priceId }),
      }),
  });
}

/** Hand Checkout's signed answer to the server. On success the whole app sees the new plan:
 * the banner and every save button come from `GET /tenant`, so that is read again. */
export function useVerifyPayment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (answer: CheckoutAnswer) =>
      api<RenewalResult>("/subscription/verify", { method: "POST", body: json(answer) }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: OVERVIEW });
      void client.invalidateQueries({ queryKey: ["tenant"] });
    },
  });
}
