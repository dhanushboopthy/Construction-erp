import type { CheckoutAnswer, RenewalOrder } from "./types";

/** Razorpay's own script. It is loaded only when an owner chooses to pay, never with the app. */
export const CHECKOUT_SRC = "https://checkout.razorpay.com/v1/checkout.js";

interface CheckoutOptions {
  key: string;
  order_id: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  prefill?: Record<string, string>;
  handler: (answer: CheckoutAnswer) => void;
  modal: { ondismiss: () => void };
}

interface CheckoutInstance {
  open: () => void;
  on: (
    event: "payment.failed",
    callback: (failure: { error?: { description?: string } }) => void,
  ) => void;
}

declare global {
  interface Window {
    Razorpay?: new (options: CheckoutOptions) => CheckoutInstance;
  }
}

function loadScript(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = CHECKOUT_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () =>
      reject(new Error("Razorpay Checkout could not be loaded. Check your connection."));
    document.head.append(script);
  });
}

/**
 * Opens Razorpay Checkout for an order the server made. The amount and the key come from the
 * server's answer. Resolves with Razorpay's signed answer, or null if the owner closed it.
 */
export async function payWithCheckout(order: RenewalOrder): Promise<CheckoutAnswer | null> {
  await loadScript();
  const Razorpay = window.Razorpay;
  if (!Razorpay) throw new Error("Razorpay Checkout is not available.");
  return new Promise((resolve, reject) => {
    const checkout = new Razorpay({
      key: order.key_id,
      order_id: order.razorpay_order_id,
      amount: order.amount_paise,
      currency: order.currency,
      name: order.name,
      description: order.description,
      prefill: { name: order.company_name },
      handler: resolve,
      modal: { ondismiss: () => resolve(null) },
    });
    checkout.on("payment.failed", (failure) =>
      reject(new Error(failure.error?.description ?? "The payment did not go through.")),
    );
    checkout.open();
  });
}
