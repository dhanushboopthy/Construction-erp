import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { SubscriptionBanner } from "@/components/SubscriptionBanner";
import { COUNTER, mockApi, OWNER, session } from "@/test/mockApi";

import type { RenewalOverview } from "./types";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => {
  vi.unstubAllGlobals();
  delete window.Razorpay;
});

const YEAR = {
  price_id: 12,
  plan_id: 4,
  plan_code: "BUSINESS",
  plan_name: "Business",
  plan_description: "",
  duration_value: 1,
  duration_unit: "year" as const,
  price: "11800.00",
  currency: "INR",
  is_current_plan: false,
  would_run_until: "2027-11-05T10:00:00Z",
};
const MONTH = {
  ...YEAR,
  price_id: 11,
  duration_unit: "month" as const,
  price: "1180.00",
  would_run_until: "2026-12-05T10:00:00Z",
};

const OVERVIEW: RenewalOverview = {
  online_renewal: true,
  plan_code: "TRIAL",
  plan_name: "Trial",
  status: "expired",
  access_state: "read_only",
  expires_at: "2026-10-30T10:00:00Z",
  days_left: -6,
  options: [MONTH, YEAR],
};

const ORDER = {
  id: 1,
  razorpay_order_id: "order_ABC",
  key_id: "rzp_test_public",
  amount: "11800.00",
  amount_paise: 1180000,
  currency: "INR",
  name: "Duolink",
  description: "Business, 1 year",
  company_name: "Acme",
};

describe("Plan & billing", () => {
  it("lets a read-only owner pay: the server names the amount and verifies the answer", async () => {
    const user = userEvent.setup();
    const opened: Record<string, unknown>[] = [];
    window.Razorpay = class {
      constructor(private options: Record<string, unknown>) {
        opened.push(options);
      }
      on() {}
      open() {
        (this.options.handler as (a: unknown) => void)({
          razorpay_order_id: "order_ABC",
          razorpay_payment_id: "pay_1",
          razorpay_signature: "sig",
        });
      }
    } as unknown as typeof window.Razorpay;
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /tenant": () => ({
        body: {
          slug: "acme",
          status: "active",
          name: "Acme",
          tagline: "t",
          access_state: "read_only",
          online_renewal: true,
        },
      }),
      "GET /subscription": () => ({ body: OVERVIEW }),
      "POST /subscription/orders": () => ({ status: 201, body: ORDER }),
      "POST /subscription/verify": () => ({
        body: {
          applied: true,
          plan_name: "Business",
          status: "active",
          access_state: "full",
          expires_at: "2027-11-05T10:00:00Z",
          days_left: 365,
        },
      }),
    });
    renderAt("/plan");

    expect(await screen.findByText("Ended on")).toBeVisible();
    expect(screen.getByText("Ended (read-only)")).toBeVisible();
    await user.click(await screen.findByRole("radio", { name: /Business, 1 year/ }));
    const pay = screen.getByRole("button", { name: "Pay ₹11,800.00 with Razorpay" });
    expect(pay).toBeEnabled(); // payable even while the company is read-only
    await user.click(pay);

    expect(
      await screen.findByText(/now runs until 5 Nov 2027, and you can save changes again/),
    ).toBeVisible();
    // Only the price goes to the server; the amount Checkout shows is the server's.
    expect(calls.find((c) => c.path === "/subscription/orders")?.body).toEqual({ price_id: 12 });
    expect(opened[0]).toMatchObject({
      key: "rzp_test_public",
      amount: 1180000,
      order_id: "order_ABC",
    });
    expect(calls.find((c) => c.path === "/subscription/verify")?.body).toEqual({
      razorpay_order_id: "order_ABC",
      razorpay_payment_id: "pay_1",
      razorpay_signature: "sig",
    });
  });

  it("verifies nothing when Checkout is closed without paying", async () => {
    const user = userEvent.setup();
    window.Razorpay = class {
      constructor(private options: { modal: { ondismiss: () => void } }) {}
      on() {}
      open() {
        this.options.modal.ondismiss();
      }
    } as unknown as typeof window.Razorpay;
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /subscription": () => ({ body: OVERVIEW }),
      "POST /subscription/orders": () => ({ status: 201, body: ORDER }),
    });
    renderAt("/plan");
    await user.click(await screen.findByRole("button", { name: /^Pay ₹1,180.00/ }));
    await vi.waitFor(() => expect(calls.some((c) => c.path === "/subscription/orders")).toBe(true));
    expect(calls.some((c) => c.path === "/subscription/verify")).toBe(false);
  });

  it("shows a refused payment plainly", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(OWNER),
      "GET /subscription": () => ({ body: OVERVIEW }),
      "POST /subscription/orders": () => ({
        status: 502,
        body: { code: "RAZORPAY_ERROR", message: "Razorpay could not be reached.", field: null },
      }),
    });
    renderAt("/plan");
    await user.click(await screen.findByRole("button", { name: /^Pay ₹1,180.00/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Razorpay could not be reached.");
  });

  it("says Contact Duolink while online renewal is not set up", async () => {
    mockApi({
      ...session(OWNER),
      "GET /subscription": () => ({
        body: { ...OVERVIEW, online_renewal: false, options: [] },
      }),
    });
    renderAt("/plan");
    expect(await screen.findByText("Contact Duolink to renew.")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Pay/ })).toBeNull();
  });

  it("tells another role to ask the owner, without asking the server for prices", async () => {
    const { calls } = mockApi({ ...session(COUNTER) });
    renderAt("/plan");
    expect(await screen.findByText("Ask your owner to renew the Duolink plan.")).toBeVisible();
    expect(calls.some((c) => c.path === "/subscription")).toBe(false);
  });
});

describe("SubscriptionBanner with online renewal", () => {
  const base = { slug: "acme", status: "active" as const, name: "Acme", tagline: "t" };

  it("links to the Plan & billing page once Duolink has set it up", () => {
    render(
      <MemoryRouter>
        <SubscriptionBanner
          tenant={{
            ...base,
            access_state: "read_only",
            online_renewal: true,
            expires_at: "2026-11-12T10:00:00Z",
            days_left: -3,
          }}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Renew online." })).toHaveAttribute("href", "/plan");
    expect(screen.queryByText(/Contact Duolink/)).toBeNull();
  });
});
