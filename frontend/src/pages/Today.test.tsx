import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, S1, session } from "@/test/mockApi";

const ACCOUNTANT: typeof OWNER = {
  ...COUNTER,
  id: 3,
  username: "accounts",
  full_name: "Accounts",
  role: "accountant",
  locations: [],
};

const TODAY = {
  as_of: "2026-10-09",
  items_in_stock: 4,
  customers_owe: "81000.00",
  we_owe: "12000.00",
  sales_today: "3409.00",
  returns_today: "0.00",
  net_sales_today: "2663.15",
  profit_today: "410.00",
};

const BUCKETS = {
  current: "0.00",
  days_1_15: "0.00",
  days_16_30: "0.00",
  days_31_60: "0.00",
  over_60: "0.00",
};

const rec = (over: Record<string, unknown>) => ({
  party_id: 1,
  party_name: "Ravi Traders",
  balance: "10000.00",
  advance: "0.00",
  overdue: "0.00",
  buckets: BUCKETS,
  oldest_due_date: "2026-10-20",
  days_late: null,
  credit_limit: "50000.00",
  utilisation_pct: "20.00",
  dso_days: null,
  last_payment_date: "2026-10-01",
  ...over,
});

const ROWS = [
  rec({ party_id: 1, party_name: "Ravi Traders", balance: "10000.00" }),
  rec({
    party_id: 2,
    party_name: "Sri Lakshmi Builders",
    balance: "30000.00",
    overdue: "30000.00",
    days_late: 12,
    utilisation_pct: "60.00",
    oldest_due_date: "2026-09-27",
  }),
  rec({
    party_id: 3,
    party_name: "Anand Constructions",
    balance: "41000.00",
    utilisation_pct: "82.00",
  }),
  rec({
    party_id: 4,
    party_name: "Walk-in Mason",
    balance: "5000.00",
    credit_limit: null,
    utilisation_pct: null,
    oldest_due_date: null,
    last_payment_date: null,
  }),
  rec({ party_id: 5, party_name: "Big Builders", balance: "70000.00", utilisation_pct: "140.00" }),
  rec({ party_id: 6, party_name: "Settled Co", balance: "0.00" }),
];

const RECEIVABLES = {
  as_of: "2026-10-09",
  total: "156000.00",
  advances: "0.00",
  overdue: "30000.00",
  buckets: BUCKETS,
  rows: ROWS,
};

const STOCK = [
  { item_id: 1, name: "TMT 12 mm", base_unit: "kg", quantity: "0.000" },
  { item_id: 2, name: "Cement 50 kg", base_unit: "bag", quantity: "120.000" },
  { item_id: 3, name: "Binding wire", base_unit: "kg", quantity: "40.000" },
  { item_id: 4, name: "Angle 40 mm", base_unit: "kg", quantity: "10.000" },
];

function routes(
  user: typeof OWNER,
  extra: Record<string, () => { status?: number; body?: unknown }> = {},
) {
  return mockApi({
    ...session(user),
    "GET /tenant": () => ({ body: { name: "Anand Steels", tagline: "Bill fast." } }),
    "GET /reports/today": () => ({
      body:
        user.role === "owner"
          ? TODAY
          : { ...TODAY, profit_today: null, we_owe: user.role === "counter" ? null : TODAY.we_owe },
    }),
    "GET /reports/receivables": () => ({ body: RECEIVABLES }),
    "GET /reports/working-capital": () => ({ status: 404, body: null }),
    "GET /stock": () => ({ body: STOCK }),
    "GET /eway-bills/pending": () => ({ body: [] }),
    "GET /locations": () => ({ body: [S1] }),
    ...extra,
  });
}

function renderAt(path = "/") {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

describe("Today for the owner", () => {
  it("shows the header and one KPI card per figure, each a link", async () => {
    routes(OWNER);
    renderAt();
    expect(await screen.findByRole("heading", { level: 1, name: "Today" })).toBeVisible();
    expect(screen.getByText(/Sales, dues and stock at a glance/)).toBeVisible();
    for (const [name, href] of [
      [/Net sales today/, "/sales"],
      [/Profit today/, "/reports/profit"],
      [/Customers owe/, "/reports/dues"],
      [/We owe suppliers/, "/reports/dues"],
      [/Items in stock/, "/stock"],
    ] as const) {
      expect(await screen.findByRole("link", { name })).toHaveAttribute("href", href);
    }
    expect(screen.getByText("2,663.15")).toBeVisible();
    expect(screen.getByText("410.00")).toBeVisible();
  });

  it("draws the share of dues overdue and of items out of stock as progress bars", async () => {
    routes(OWNER);
    renderAt();
    const overdue = await screen.findByRole("progressbar", {
      name: "Share of what customers owe that is overdue",
    });
    expect(overdue).toHaveAttribute("aria-valuenow", "30000");
    expect(overdue).toHaveAttribute("aria-valuemax", "156000");
    const out = await screen.findByRole("progressbar", {
      name: "Share of items that are out of stock",
    });
    expect(out).toHaveAttribute("aria-valuenow", "1");
    expect(out).toHaveAttribute("aria-valuemax", "4");
  });

  it("lists who owes money, worst first, with a status word for each", async () => {
    routes(OWNER);
    renderAt();
    const table = await screen.findByRole("table", { name: "Customer dues" });
    const rows = within(table)
      .getAllByRole("button")
      .map((b) => b.textContent ?? "");
    // Most overdue first, then most owed; the customer who owes nothing is left out.
    const order = [
      "Sri Lakshmi Builders",
      "Big Builders",
      "Anand Constructions",
      "Ravi Traders",
      "Walk-in Mason",
    ];
    expect(rows).toHaveLength(order.length);
    order.forEach((name, i) => expect(rows[i]).toContain(name));
    expect(within(table).getByText("12 days late")).toBeVisible();
    expect(within(table).getByText("Overdue")).toBeVisible();
    expect(within(table).getByText("Over limit")).toBeVisible();
    expect(within(table).getByText("Near limit")).toBeVisible();
    expect(within(table).getByText("OK")).toBeVisible();
    expect(within(table).getByText("Cash")).toBeVisible();
    expect(within(table).getByText("Cash customer")).toBeVisible();
    expect(within(table).getAllByRole("progressbar")).toHaveLength(4);
    expect(within(table).getByText("70,000.00")).toBeVisible();
    expect(screen.queryByText("Settled Co")).toBeNull();
  });

  it("filters by name and status, keeping both in the URL", async () => {
    const user = userEvent.setup();
    routes(OWNER);
    renderAt();
    await screen.findByRole("table", { name: "Customer dues" });
    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "near_limit");
    expect(window.location.search).toContain("status=near_limit");
    const table = screen.getByRole("table", { name: "Customer dues" });
    expect(within(table).getAllByRole("button")).toHaveLength(1);
    expect(within(table).getByText("Anand Constructions")).toBeVisible();

    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "");
    await user.type(screen.getByRole("searchbox", { name: "Search customers" }), "ravi");
    await waitFor(() => expect(window.location.search).toContain("q=ravi"));
    await waitFor(() => expect(screen.queryByText("Big Builders")).toBeNull());
    expect(screen.getByText("Ravi Traders")).toBeVisible();
  });

  it("opens a customer from its row, by click and by keyboard", async () => {
    const user = userEvent.setup();
    routes(OWNER);
    renderAt();
    const table = await screen.findByRole("table", { name: "Customer dues" });
    await user.click(within(table).getByRole("button", { name: /Sri Lakshmi Builders/ }));
    expect(window.location.pathname).toBe("/parties");
    expect(window.location.search).toBe("?party=2");
  });

  it("links to every due and to the receivables report", async () => {
    routes(OWNER);
    renderAt();
    expect(await screen.findByRole("link", { name: "View all dues" })).toHaveAttribute(
      "href",
      "/reports/receivables",
    );
  });

  it("says nobody owes anything when that is so", async () => {
    routes(OWNER, { "GET /reports/receivables": () => ({ body: { ...RECEIVABLES, rows: [] } }) });
    renderAt();
    expect(await screen.findByText("No customer owes money today.")).toBeVisible();
  });

  it("shows an error with a retry when the dues cannot be loaded", async () => {
    const user = userEvent.setup();
    let fail = true;
    routes(OWNER, {
      "GET /reports/receivables": () =>
        fail ? { status: 500, body: { code: "X", message: "down" } } : { body: RECEIVABLES },
    });
    renderAt();
    expect(await screen.findByText("Customer dues could not be loaded.")).toBeVisible();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Sri Lakshmi Builders")).toBeVisible();
  });
});

describe("Today for the accountant", () => {
  it("shows the overdue amount instead of profit", async () => {
    routes(ACCOUNTANT);
    renderAt();
    expect(await screen.findByRole("link", { name: /^Overdue/ })).toHaveAttribute(
      "href",
      "/reports/receivables",
    );
    expect(screen.queryByText("Profit today")).toBeNull();
    expect(await screen.findByRole("table", { name: "Customer dues" })).toBeVisible();
  });
});

describe("Today for counter staff", () => {
  it("never asks for the receivables report and never shows profit or dues", async () => {
    const { calls } = routes(COUNTER);
    renderAt();
    expect(await screen.findByText("Net sales today")).toBeVisible();
    expect(await screen.findByText("Waiting e-way bills")).toBeVisible();
    expect(await screen.findByText("Items in stock")).toBeVisible();
    await screen.findByRole("heading", { name: "Stock levels" });
    await waitFor(() => expect(calls.some((c) => c.path === "/stock")).toBe(true));

    expect(calls.some((c) => c.path === "/reports/receivables")).toBe(false);
    expect(calls.some((c) => c.path.startsWith("/reports/working-capital"))).toBe(false);
    expect(screen.queryByText("Profit today")).toBeNull();
    expect(screen.queryByText("Customers owe")).toBeNull();
    expect(screen.queryByRole("table", { name: "Customer dues" })).toBeNull();
    expect(screen.queryByText("Customer dues")).toBeNull();
  });

  it("shows the shop name above the title and the waiting e-way bills as a count", async () => {
    routes(COUNTER, {
      "GET /eway-bills/pending": () => ({
        body: [{ invoice_id: 5, number: "INV/5", party_name: "Ravi", grand_total: "125000.00" }],
      }),
    });
    renderAt();
    expect(await screen.findByText("Shop 1")).toBeVisible();
    const card = await screen.findByRole("link", { name: /Waiting e-way bills/ });
    expect(within(card).getByText("1")).toBeVisible();
  });
});
