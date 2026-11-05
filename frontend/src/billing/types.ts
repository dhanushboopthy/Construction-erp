// Milestone 30 (online renewal). Written by hand until the API types are regenerated.
// These are Duolink's prices and the company's own payments to Duolink, owner only.

export type SubscriptionState = "trial" | "active" | "expired" | "cancelled";

export interface RenewalOption {
  price_id: number;
  plan_id: number;
  plan_code: string;
  plan_name: string;
  plan_description: string;
  duration_value: number;
  duration_unit: "day" | "month" | "year";
  /** Rupees as text, e.g. "11800.00". */
  price: string;
  currency: string;
  is_current_plan: boolean;
  would_run_until: string;
}

export interface RenewalOverview {
  online_renewal: boolean;
  plan_code: string;
  plan_name: string;
  status: SubscriptionState;
  access_state: "full" | "read_only";
  expires_at: string | null;
  days_left: number | null;
  options: RenewalOption[];
}

export interface RenewalOrder {
  id: number;
  razorpay_order_id: string;
  /** Razorpay's public key id, which Checkout needs. Never a secret. */
  key_id: string;
  amount: string;
  amount_paise: number;
  currency: string;
  name: string;
  description: string;
  company_name: string;
}

/** What Razorpay Checkout hands back after a payment. */
export interface CheckoutAnswer {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

export interface RenewalResult {
  applied: boolean;
  plan_name: string;
  status: SubscriptionState;
  access_state: "full" | "read_only";
  expires_at: string | null;
  days_left: number | null;
}
