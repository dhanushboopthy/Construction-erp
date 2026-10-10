import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import type { User } from "@/api/types";
import { COUNTER, mockApi, OWNER, S1, session } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const ACCOUNTANT: User = { ...OWNER, id: 3, username: "accounts", role: "accountant" };

const BUCKETS = {
  current: "0.00",
  days_1_15: "2000.00",
  days_16_30: "3000.00",
  days_31_60: "5000.00",
  over_60: "10000.00",
};
const ROW = {
  party_id: 9,
  party_name: "Larry",
  balance: "10000.00",
  advance: "0.00",
  overdue: "10000.00",
  buckets: { ...BUCKETS, days_1_15: "0.00", days_16_30: "0.00", days_31_60: "0.00" },
  oldest_due_date: "2026-07-02",
  days_late: 100,
  credit_limit: null,
  utilisation_pct: null,
  dso_days: null,
  last_payment_date: null,
};
const REPORT = {
  as_of: "2026-10-10",
  total: "20000.00",
  advances: "0.00",
  overdue: "20000.00",
  buckets: BUCKETS,
  rows: [ROW],
};
const OWNER_REPORT = {
  ...REPORT,
  provision: "5580.00",
  provision_pct: {
    current: "0.00",
    days_1_15: "1.00",
    days_16_30: "2.00",
    days_31_60: "10.00",
    over_60: "50.00",
  },
};
const KPIS = [
  {
    code: "overdue_receivables",
    name: "Overdue receivables",
    formula: "Σ open bills past their due date",
    meaning: "Money customers should already have paid you.",
    example: "₹95,000 past due on 20 Oct",
    sources: "sales_invoice.due_date",
    owner_only: false,
    refresh: "live",
    good: "down",
    unit: "₹",
  },
];

function routes(
  user: User,
  report: unknown,
  extra: Record<string, () => { status?: number; body?: unknown }> = {},
) {
  return {
    ...session(user),
    "GET /locations": () => ({ body: [S1] }),
    "GET /reports/today": () => ({ body: { as_of: "2026-10-10" } }),
    "GET /kpis/definitions": () => ({ body: KPIS }),
    "GET /reports/receivables": () => ({ body: report }),
    "GET /write-offs": () => ({ body: [] }),
    ...extra,
  };
}

describe("Receivables", () => {
  it("ages what customers owe from the due date and shows the owner the provision", async () => {
    mockApi(routes(OWNER, OWNER_REPORT));
    renderAt("/reports/receivables");
    const buckets = await screen.findByRole("table", { name: "Overdue by due date" });
    expect(within(buckets).getByText("Over 60 days late")).toBeVisible();
    expect(within(buckets).getByText("₹10,000.00")).toBeVisible();
    expect(within(buckets).getByText("50.00%")).toBeVisible();
    expect(screen.getAllByText("₹5,580.00").length).toBeGreaterThan(0);
    const customers = screen.getByRole("table", { name: "Customers and what they owe" });
    expect(within(customers).getByText("Larry")).toBeVisible();
    expect(within(customers).getByText("100")).toBeVisible();
  });

  it("shows the accountant the aging but neither the provision nor the write-off form", async () => {
    mockApi(routes(ACCOUNTANT, REPORT));
    renderAt("/reports/receivables");
    await screen.findByRole("table", { name: "Overdue by due date" });
    expect(screen.queryByText(/Provision/)).toBeNull();
    expect(screen.queryByRole("form", { name: "Write off a bad debt" })).toBeNull();
  });

  it("is not offered to counter staff", async () => {
    mockApi({ ...session(COUNTER), "GET /locations": () => ({ body: [S1] }) });
    renderAt("/reports/receivables");
    expect(await screen.findByRole("heading", { name: "Reports" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Receivables" })).toBeNull();
    expect(screen.queryByRole("table", { name: "Overdue by due date" })).toBeNull();
  });

  it("lets the owner write off a bad debt with a reason", async () => {
    const user = userEvent.setup();
    const saved = {
      id: 1,
      number: "S1W/26-27/00001",
      location_id: 1,
      party_id: 9,
      party_name: "Larry",
      writeoff_date: "2026-10-10",
      amount: "4000.00",
      balance_before: "10000.00",
      reason: "Contractor untraceable",
      created_by_name: "Shop Owner",
    };
    const { calls } = mockApi(
      routes(OWNER, OWNER_REPORT, { "POST /write-offs": () => ({ status: 201, body: saved }) }),
    );
    renderAt("/reports/receivables");
    await screen.findByRole("table", { name: "Overdue by due date" });
    await user.click(screen.getByRole("button", { name: "Write off" }));
    expect(await screen.findByText("Choose the customer.")).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Customer"), "9");
    await user.type(screen.getByLabelText("Amount to write off (₹)"), "4000");
    await user.click(screen.getByRole("button", { name: "Write off" }));
    expect(await screen.findByText("Give a reason, so the books say why.")).toBeVisible();
    await user.type(screen.getByLabelText("Reason"), "Contractor untraceable");
    await user.click(screen.getByRole("button", { name: "Write off" }));
    expect(await screen.findByText(/Written off: S1W\/26-27\/00001/)).toBeVisible();
    const post = calls.find((c) => c.method === "POST" && c.path === "/write-offs");
    expect(post?.body).toEqual({
      location_id: 1,
      party_id: 9,
      amount: "4000",
      reason: "Contractor untraceable",
    });
  });

  it("explains a refusal in the shop's words", async () => {
    const user = userEvent.setup();
    mockApi(
      routes(OWNER, OWNER_REPORT, {
        "POST /write-offs": () => ({
          status: 409,
          body: { code: "WRITEOFF_TOO_MUCH", message: "Larry does not owe that much." },
        }),
      }),
    );
    renderAt("/reports/receivables");
    await screen.findByRole("table", { name: "Overdue by due date" });
    await user.selectOptions(screen.getByLabelText("Customer"), "9");
    await user.type(screen.getByLabelText("Amount to write off (₹)"), "99999");
    await user.type(screen.getByLabelText("Reason"), "gone");
    await user.click(screen.getByRole("button", { name: "Write off" }));
    expect(await screen.findByText("Larry does not owe that much.")).toBeVisible();
  });
});
