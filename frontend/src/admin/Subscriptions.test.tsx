import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "@/api/queryClient";

import { AdminApp } from "./AdminApp";
import { daysLeftLabel, methodLabel, monthLabel } from "./labels";

const ADMIN = {
  id: 1,
  email: "ops@duolink.app",
  full_name: "Duolink Ops",
  mobile: null,
  role: "super_admin",
  must_change_password: false,
  last_login_at: null,
};
const SUPPORT = { ...ADMIN, id: 2, full_name: "Help Desk", role: "support" };

const price = (id: number, value: number, unit: string, amount: string) => ({
  id,
  duration_value: value,
  duration_unit: unit,
  price: amount,
  currency: "INR",
  is_active: true,
});
const PLAN = {
  id: 2,
  code: "BASIC",
  name: "Basic",
  short_description: "",
  long_description: "",
  max_users: 10,
  max_locations: 3,
  features: [],
  is_active: true,
  is_popular: false,
  sort_order: 2,
  prices: [price(21, 1, "month", "999.90"), price(22, 1, "year", "9999.00")],
  companies: 2,
  created_at: "2026-10-24T09:00:00Z",
  updated_at: "2026-10-24T09:00:00Z",
};
const SUB = {
  id: 5,
  tenant_id: 7,
  tenant_slug: "acme",
  tenant_name: "Acme Steels",
  plan_id: 2,
  plan_code: "BASIC",
  plan_name: "Basic",
  status: "active",
  starts_at: "2026-10-01T00:00:00Z",
  expires_at: "2026-11-12T18:29:59Z",
  days_left: 12,
  needs_review: false,
  duration_value: 1,
  duration_unit: "month",
  price: "999.90",
  cancelled_at: null,
  cancel_reason: null,
};
const LAPSED = {
  ...SUB,
  id: 6,
  tenant_id: 8,
  tenant_slug: "bharat",
  tenant_name: "Bharat Pipes",
  status: "expired",
  days_left: -3,
  expires_at: "2026-10-28T18:29:59Z",
  needs_review: true,
};
const PAYMENT = {
  id: 90,
  subscription_id: 5,
  tenant_id: 7,
  tenant_name: "Acme Steels",
  plan_code: "BASIC",
  plan_name: "Basic",
  amount: "9999.00",
  method: "upi",
  reference: "UTR-12345",
  notes: null,
  paid_at: "2026-10-01T06:30:00Z",
  period_starts_at: "2026-10-01T00:00:00Z",
  period_ends_at: "2027-09-30T18:29:59Z",
  reverses_id: null,
  reversed: false,
  recorded_by: "Duolink Ops",
};
const REVERSAL = {
  ...PAYMENT,
  id: 91,
  amount: "-1500.00",
  reverses_id: 80,
  reversed: false,
  reference: null,
};
const REVERSED = { ...PAYMENT, id: 80, amount: "1500.00", reversed: true, reference: null };
const TOTALS = { received: "11499.00", reversed: "1500.00", net: "9999.00" };

const DASH = {
  companies_by_status: { trial: 1, active: 2, suspended: 0, cancelled: 0 },
  active_subscriptions: 2,
  revenue_month: "123456.50",
  revenue_fy: "2345678.00",
  new_companies_month: 1,
  renewals_month: 3,
  expiring_30: 4,
  trend: Array.from({ length: 12 }, (_, i) => ({
    month: `2026-${String(i + 1).padStart(2, "0")}`,
    revenue: i === 10 ? "123456.50" : "1000.00",
    signups: i,
  })),
  plan_breakdown: [],
  expiring_soon: [],
};
const OVERVIEW = {
  tenants_total: 3,
  tenants_by_status: { trial: 1, active: 2, suspended: 0, cancelled: 0 },
  new_tenants_this_month: 1,
  active_users: 9,
  open_sessions: 4,
  sign_ins_24h: 6,
  sign_ins_7d: 30,
  failed_sign_ins_24h: 0,
  failed_sign_ins_7d: 0,
  trials_ending: [],
};
const TENANT = {
  id: 7,
  slug: "acme",
  name: "Acme Steels",
  status: "active",
  plan: "BASIC",
  plan_id: 2,
  plan_name: "Basic",
  trial_ends_at: null,
  trial_state: "none",
  users: 1,
  max_users: 5,
  locations: 2,
  max_locations: 2,
  bills_30d: 12,
  last_sign_in_at: null,
  created_at: "2026-10-24T09:00:00Z",
  own_max_users: null,
  own_max_locations: null,
  suspended_at: null,
  suspended_reason: null,
  open_sessions: 2,
};

type Route = (url: string, init?: RequestInit) => unknown;
type Call = { url: string; method: string; body?: string };

function stubApi(routes: [RegExp, Route][], admin: object = ADMIN) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      calls.push({ url, method: init?.method ?? "GET", body: init?.body as string | undefined });
      if (url.endsWith("/admin/auth/refresh")) {
        return new Response(
          JSON.stringify({ access_token: "t", token_type: "bearer", expires_in: 1800, admin }),
          { status: 200 },
        );
      }
      const match = routes.find(([pattern]) => pattern.test(url));
      if (!match) return new Response(JSON.stringify({ code: "NOT_FOUND" }), { status: 404 });
      const answer = match[1](url, init);
      if (answer instanceof Response) return answer;
      return new Response(JSON.stringify(answer), { status: 200 });
    }),
  );
  return calls;
}

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<AdminApp client={createQueryClient()} />);
}

const refusal = (code: string, message: string) =>
  new Response(JSON.stringify({ code, message, field: null, request_id: null }), { status: 409 });

const billing: [RegExp, Route][] = [
  [/\/admin\/billing\/dashboard$/, () => DASH],
  [/\/admin\/billing\/plans/, () => [PLAN]],
  [/\/admin\/billing\/subscriptions\/\d+\/renew/, () => SUB],
  [/\/admin\/billing\/subscriptions\/\d+\/cancel/, () => ({ ...SUB, status: "cancelled" })],
  [/\/admin\/billing\/subscriptions/, () => ({ items: [SUB, LAPSED], total: 2 })],
  [/\/admin\/billing\/payments\/\d+\/reverse/, () => REVERSAL],
  [
    /\/admin\/billing\/payments/,
    () => ({ items: [PAYMENT, REVERSAL, REVERSED], total: 3, totals: TOTALS }),
  ],
  [/\/admin\/tenants\/7$/, () => TENANT],
  [/\/admin\/tenants/, () => ({ items: [TENANT], total: 1, limit: 200, offset: 0 })],
  [/\/admin\/overview$/, () => OVERVIEW],
];

afterEach(() => vi.unstubAllGlobals());

describe("billing labels", () => {
  it("writes days left, months and methods in words", () => {
    expect(daysLeftLabel(12)).toBe("12 days left");
    expect(daysLeftLabel(1)).toBe("1 day left");
    expect(daysLeftLabel(0)).toBe("Ends today");
    expect(daysLeftLabel(-3)).toBe("Ended 3 days ago");
    expect(daysLeftLabel(null)).toBe("No end date");
    expect(monthLabel("2026-11")).toBe("Nov 2026");
    expect(methodLabel("upi")).toBe("UPI");
  });
});

describe("Overview revenue (M21)", () => {
  it("shows the revenue figures from the billing dashboard, in rupees", async () => {
    stubApi(billing);
    renderAt("/admin");
    expect(await screen.findByText("Revenue this month")).toBeInTheDocument();
    expect(await screen.findByText("₹1,23,456.50", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText("₹23,45,678.00", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText("Renewals this month")).toBeInTheDocument();
    expect(screen.getByText("Expiring in 30 days")).toBeInTheDocument();
    expect(screen.getByText("New companies this month")).toBeInTheDocument();
    expect(screen.getByText("Active subscriptions")).toBeInTheDocument();
  });

  it("draws the twelve-month charts with a table for the same figures", async () => {
    const user = userEvent.setup();
    stubApi(billing);
    renderAt("/admin");
    const revenue = await screen.findByRole("figure", { name: "Revenue, last 12 months" });
    const bars = within(revenue).getAllByRole("img");
    expect(bars).toHaveLength(12);
    expect(bars[10]).toHaveAttribute("aria-label", "Nov 2026: ₹1,23,456.50");
    await user.hover(bars[10] as HTMLElement);
    expect(within(revenue).getByText("₹1,23,456.50", { selector: "strong" })).toBeInTheDocument();
    await user.click(within(revenue).getByText("Show as a table"));
    const table = within(revenue).getByRole("table", { name: "Revenue, last 12 months" });
    expect(within(table).getAllByRole("row")).toHaveLength(13);
    const signups = await screen.findByRole("figure", { name: "New companies, last 12 months" });
    expect(within(signups).getAllByRole("img")[3]).toHaveAttribute("aria-label", "Apr 2026: 3");
  });

  it("says so when the revenue cannot be loaded, and keeps the rest of the page", async () => {
    stubApi([[/\/admin\/overview$/, () => OVERVIEW]]);
    renderAt("/admin");
    expect(await screen.findByText("Revenue figures could not be loaded.")).toBeInTheDocument();
    expect(await screen.findByText("Active users")).toBeInTheDocument();
  });
});

describe("Subscriptions page (M21)", () => {
  it("lists subscriptions with their state and days left, and filters by status", async () => {
    const user = userEvent.setup();
    const calls = stubApi(billing);
    renderAt("/admin/subscriptions");
    const table = await screen.findByRole("table", { name: "Subscriptions" });
    expect(within(table).getByText("Acme Steels")).toBeInTheDocument();
    expect(within(table).getByText("12 days left")).toBeInTheDocument();
    expect(within(table).getByText("Ended 3 days ago")).toBeInTheDocument();
    expect(within(table).getByText("Expired")).toBeInTheDocument();
    expect(within(table).getByText("Needs review")).toBeInTheDocument();
    expect(within(table).getAllByText("₹999.90", { selector: "td" })).toHaveLength(2);
    await user.selectOptions(screen.getByLabelText("Status"), "expired");
    await user.selectOptions(screen.getByLabelText("Ending within"), "30");
    expect(
      calls.some(
        (c) =>
          c.url.includes("/billing/subscriptions?") &&
          c.url.includes("status=expired") &&
          c.url.includes("expiring_within=30"),
      ),
    ).toBe(true);
  });

  it("reads the filters from the address", async () => {
    const calls = stubApi(billing);
    renderAt("/admin/subscriptions?expiring_within=30");
    await screen.findByRole("table", { name: "Subscriptions" });
    expect(screen.getByLabelText("Ending within")).toHaveValue("30");
    expect(calls.some((c) => c.url.includes("expiring_within=30"))).toBe(true);
  });

  it("lets a Super Admin renew with a listed price, prefilled and sent as text", async () => {
    const user = userEvent.setup();
    const calls = stubApi(billing);
    renderAt("/admin/subscriptions");
    await user.click(await screen.findByRole("button", { name: "Renew Acme Steels" }));
    const dialog = await screen.findByRole("dialog", { name: "Renew Acme Steels" });
    expect(within(dialog).getByLabelText("Amount received")).toHaveValue("999.90");
    await user.selectOptions(within(dialog).getByLabelText("Renew for"), "1 year at ₹9,999.00");
    expect(within(dialog).getByLabelText("Amount received")).toHaveValue("9999.00");
    await user.selectOptions(within(dialog).getByLabelText("Paid by"), "upi");
    await user.type(within(dialog).getByLabelText("Reference"), "UTR-77");
    await user.click(within(dialog).getByRole("button", { name: "Record payment and renew" }));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/subscriptions/5/renew"));
    expect(JSON.parse(post?.body ?? "{}")).toEqual({
      plan_id: 2,
      price_id: 22,
      custom_days: null,
      amount: "9999.00",
      method: "upi",
      reference: "UTR-77",
    });
  });

  it("renews for a custom number of days and checks the amount first", async () => {
    const user = userEvent.setup();
    const calls = stubApi(billing);
    renderAt("/admin/subscriptions");
    await user.click(await screen.findByRole("button", { name: "Renew Acme Steels" }));
    const dialog = await screen.findByRole("dialog", { name: "Renew Acme Steels" });
    await user.selectOptions(
      within(dialog).getByLabelText("Renew for"),
      "A number of days I choose",
    );
    const amount = within(dialog).getByLabelText("Amount received");
    expect(amount).toHaveValue("");
    await user.type(within(dialog).getByLabelText("Number of days"), "45");
    await user.type(amount, "12.345");
    await user.click(within(dialog).getByRole("button", { name: "Record payment and renew" }));
    expect(await within(dialog).findByText(/Enter the amount received/)).toBeInTheDocument();
    await user.clear(amount);
    await user.type(amount, "500");
    await user.click(within(dialog).getByRole("button", { name: "Record payment and renew" }));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/renew"));
    expect(JSON.parse(post?.body ?? "{}")).toMatchObject({
      price_id: null,
      custom_days: 45,
      amount: "500",
    });
  });

  it("shows the server's reason when a renewal is refused", async () => {
    const user = userEvent.setup();
    stubApi([
      [
        /\/subscriptions\/\d+\/renew/,
        () => refusal("PLAN_INACTIVE", "That plan is archived and cannot be sold."),
      ],
      ...billing,
    ]);
    renderAt("/admin/subscriptions");
    await user.click(await screen.findByRole("button", { name: "Renew Acme Steels" }));
    const dialog = await screen.findByRole("dialog", { name: "Renew Acme Steels" });
    await user.click(within(dialog).getByRole("button", { name: "Record payment and renew" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("That plan is archived");
  });

  it("closes the renew dialog with Escape", async () => {
    const user = userEvent.setup();
    stubApi(billing);
    renderAt("/admin/subscriptions");
    await user.click(await screen.findByRole("button", { name: "Renew Acme Steels" }));
    const dialog = await screen.findByRole("dialog", { name: "Renew Acme Steels" });
    await user.type(within(dialog).getByLabelText("Reference"), "{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("asks for a reason before cancelling", async () => {
    const user = userEvent.setup();
    const calls = stubApi(billing);
    renderAt("/admin/subscriptions");
    await user.click(await screen.findByRole("button", { name: "Cancel Acme Steels" }));
    const dialog = await screen.findByRole("alertdialog");
    const confirm = within(dialog).getByRole("button", { name: "Cancel subscription" });
    expect(confirm).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Reason for cancelling"), "Closed the shop");
    await user.click(confirm);
    await vi.waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    const post = calls.find(
      (c) => c.method === "POST" && c.url.endsWith("/subscriptions/5/cancel"),
    );
    expect(JSON.parse(post?.body ?? "{}")).toEqual({ reason: "Closed the shop" });
  });

  it("is read-only for Support: no Renew or Cancel", async () => {
    stubApi(billing, SUPPORT);
    renderAt("/admin/subscriptions");
    await screen.findByRole("table", { name: "Subscriptions" });
    expect(screen.queryByRole("button", { name: /Renew/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Cancel/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Actions" })).not.toBeInTheDocument();
  });

  it("is in the sidebar with Alt shortcuts", async () => {
    const user = userEvent.setup();
    stubApi(billing);
    renderAt("/admin");
    expect(await screen.findByRole("link", { name: /Subscriptions/ })).toHaveAttribute(
      "href",
      "/admin/subscriptions",
    );
    expect(screen.getByRole("link", { name: /Payments/ })).toHaveAttribute(
      "href",
      "/admin/payments",
    );
    await user.keyboard("{Alt>}{7}{/Alt}");
    expect(await screen.findByRole("heading", { name: "Subscriptions" })).toBeInTheDocument();
    await user.keyboard("{Alt>}{8}{/Alt}");
    expect(await screen.findByRole("heading", { name: "Payments" })).toBeInTheDocument();
  });
});

describe("Payments page (M21)", () => {
  it("lists payments with totals, marks reversals, and sends the filters", async () => {
    const user = userEvent.setup();
    const calls = stubApi(billing);
    renderAt("/admin/payments");
    const table = await screen.findByRole("table", { name: "Payments" });
    expect(within(table).getByText("₹9,999.00")).toBeInTheDocument();
    expect(within(table).getByText("UTR-12345")).toBeInTheDocument();
    expect(within(table).getByText("-₹1,500.00")).toBeInTheDocument();
    expect(within(table).getByText("Reversal")).toBeInTheDocument();
    expect(within(table).getByText("Reversed")).toBeInTheDocument();
    expect(screen.getByText("₹11,499.00")).toBeInTheDocument();
    expect(screen.getByText("₹1,500.00", { selector: "dd" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Method"), "UPI");
    await user.type(screen.getByLabelText("From"), "2026-10-01");
    await user.selectOptions(await screen.findByLabelText("Company"), "Acme Steels");
    await vi.waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.url.includes("/billing/payments?") &&
            c.url.includes("method=upi") &&
            c.url.includes("from=2026-10-01") &&
            c.url.includes("tenant_id=7"),
        ),
      ).toBe(true),
    );
  });

  it("reverses a payment with a reason, only on a live payment", async () => {
    const user = userEvent.setup();
    const calls = stubApi(billing);
    renderAt("/admin/payments");
    await screen.findByRole("table", { name: "Payments" });
    // One live payment: the reversal row and the already reversed row offer nothing.
    const buttons = screen.getAllByRole("button", { name: /Reverse payment from/ });
    expect(buttons).toHaveLength(1);
    await user.click(buttons[0] as HTMLElement);
    const dialog = await screen.findByRole("alertdialog");
    const confirm = within(dialog).getByRole("button", { name: "Reverse payment" });
    expect(confirm).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Reason for reversing"), "Cheque bounced");
    await user.click(confirm);
    await vi.waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/payments/90/reverse"));
    expect(JSON.parse(post?.body ?? "{}")).toEqual({ reason: "Cheque bounced" });
  });

  it("shows why a reversal was refused", async () => {
    const user = userEvent.setup();
    stubApi([
      [/\/payments\/\d+\/reverse/, () => refusal("PAYMENT_REVERSED", "Already reversed.")],
      ...billing,
    ]);
    renderAt("/admin/payments");
    await user.click(await screen.findByRole("button", { name: /Reverse payment from/ }));
    const dialog = await screen.findByRole("alertdialog");
    await user.type(within(dialog).getByLabelText("Reason for reversing"), "Entered twice");
    await user.click(within(dialog).getByRole("button", { name: "Reverse payment" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Already reversed.");
  });

  it("is read-only for Support", async () => {
    stubApi(billing, SUPPORT);
    renderAt("/admin/payments");
    await screen.findByRole("table", { name: "Payments" });
    expect(screen.queryByRole("button", { name: /Reverse/ })).not.toBeInTheDocument();
    expect(screen.getByText("₹11,499.00")).toBeInTheDocument();
  });
});

describe("Company Subscription tab (M21)", () => {
  const forCompany: [RegExp, Route][] = [
    [
      /\/admin\/billing\/subscriptions\?/,
      (url) => ({ items: url.includes("tenant_id=7") ? [SUB] : [], total: 1 }),
    ],
    ...billing,
  ];

  it("shows the current subscription and payment history", async () => {
    stubApi(forCompany);
    renderAt("/admin/companies/7?tab=subscription");
    expect(
      await screen.findByRole("heading", { name: "Current subscription" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("12 days left", { exact: false })).toBeInTheDocument();
    const history = await screen.findByRole("table", { name: "Payment history" });
    expect(within(history).getByText("₹9,999.00")).toBeInTheDocument();
    expect(within(history).getAllByText("UPI").length).toBeGreaterThan(0);
    expect(within(history).getByText("UTR-12345")).toBeInTheDocument();
  });

  it("renews from the company page", async () => {
    const user = userEvent.setup();
    const calls = stubApi(forCompany);
    renderAt("/admin/companies/7?tab=subscription");
    await user.click(await screen.findByRole("button", { name: "Renew…" }));
    const dialog = await screen.findByRole("dialog", { name: "Renew Acme Steels" });
    await user.click(within(dialog).getByRole("button", { name: "Record payment and renew" }));
    expect(await screen.findByText("Renewed. The payment is recorded below.")).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/renew"));
    expect(JSON.parse(post?.body ?? "{}")).toMatchObject({
      plan_id: 2,
      price_id: 21,
      amount: "999.90",
    });
  });

  it("gives Support the facts and no renew button", async () => {
    stubApi(forCompany, SUPPORT);
    renderAt("/admin/companies/7?tab=subscription");
    expect(
      await screen.findByRole("heading", { name: "Current subscription" }),
    ).toBeInTheDocument();
    await screen.findByRole("table", { name: "Payment history" });
    expect(screen.queryByRole("button", { name: /Renew/ })).not.toBeInTheDocument();
  });
});
