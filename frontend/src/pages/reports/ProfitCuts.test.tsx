import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import type { User } from "@/api/types";
import { COUNTER, G1, mockApi, OWNER, S1, session } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const ACCOUNTANT: User = { ...OWNER, id: 3, username: "accounts", role: "accountant" };
const S2 = { ...S1, id: 2, code: "S2", name: "Shop 2" };

const KPIS = [
  {
    code: "profit_per_ton",
    name: "Profit per ton",
    formula: "Gross profit of lines sold by weight ÷ tons",
    meaning: "What each ton of steel earns.",
    example: "₹6,000 on 10 t = ₹600 a ton",
    sources: "sales_line",
    owner_only: true,
    refresh: "live",
    good: "up",
    unit: "₹",
  },
  {
    code: "itc_at_risk",
    name: "ITC at risk",
    formula: "Input tax in books, not in GSTR-2B",
    meaning: "Input tax you cannot claim until the supplier files.",
    example: "₹9,000",
    sources: "purchase",
    owner_only: false,
    refresh: "monthly",
    good: "down",
    unit: "₹",
  },
];

const ROW = {
  net_sales: "112000.00",
  cogs: "100000.00",
  freight: "3000.00",
  gross_profit: "9000.00",
  margin_pct: "8.04",
  share_pct: "59.28",
  tons: "2.000",
  units: "0.000",
  unit_label: null,
  profit_per_ton: "4500.00",
  profit_per_unit: null,
  margin_per_base_unit: "4.5000",
};
const CUTS = {
  period: "2026-10",
  by: "brand",
  date_from: "2026-10-01",
  date_to: "2026-10-31",
  location_id: null,
  rows: [
    { key: "Tata", ...ROW },
    {
      key: "No brand",
      ...ROW,
      net_sales: "58282.70",
      cogs: "57100.00",
      freight: "0.00",
      gross_profit: "1182.70",
      margin_pct: "2.03",
      share_pct: "7.79",
      tons: "1.000",
      profit_per_ton: "1000.00",
      units: "6.000",
      unit_label: "bag",
      profit_per_unit: "30.45",
    },
  ],
  net_sales: "170282.70",
  cogs: "157100.00",
  freight: "3000.00",
  gross_profit_before_loss: "10182.70",
  stock_lost: "1000.00",
  gross_profit: "9182.70",
  tons: "3.000",
  profit_per_ton: "3333.33",
  variable_expenses: "0.00",
  contribution_per_ton: null,
  enough_data: true,
  data_note: "Some sales were by the bag or piece, so one contribution per ton would mislead.",
};

function routes(
  user: User,
  extra: Record<string, (b: unknown, u: URL) => { status?: number; body?: unknown }> = {},
  shops = [S1, G1],
) {
  return {
    ...session(user),
    "GET /locations": () => ({ body: shops }),
    "GET /reports/today": () => ({ body: { as_of: "2026-10-10" } }),
    "GET /kpis/definitions": () => ({ body: KPIS }),
    "GET /reports/profitability": () => ({ body: CUTS }),
    ...extra,
  };
}

describe("Profit per ton", () => {
  it("shows each brand's profit per ton and ties back to the profit and loss", async () => {
    mockApi(routes(OWNER));
    renderAt("/reports/profit-cuts");
    const table = await screen.findByRole("table", { name: "Profit by cut" });
    const tata = within(table).getByRole("row", { name: /Tata/ });
    expect(within(tata).getByText("4,500.00")).toBeVisible();
    expect(within(tata).getByText("59.28")).toBeVisible();
    const none = within(table).getByRole("row", { name: /No brand/ });
    expect(within(none).getByText("6 bag")).toBeVisible();
    expect(within(none).getByText("30.45")).toBeVisible();
    expect(within(table).getByText("−1,000.00")).toBeVisible();
    expect(within(table).getByText("9,182.70")).toBeVisible();
    expect(screen.getByText("₹3,333.33")).toBeVisible();
    expect(screen.getByText(/one contribution per ton would mislead/)).toBeVisible();
  });

  it("re-asks the API when the cut or the shop changes", async () => {
    const user = userEvent.setup();
    const asked: string[] = [];
    mockApi(
      routes(
        OWNER,
        {
          "GET /reports/profitability": (_b, url) => {
            asked.push(url.search);
            return { body: CUTS };
          },
        },
        [S1, S2],
      ),
    );
    renderAt("/reports/profit-cuts");
    await screen.findByRole("table", { name: "Profit by cut" });
    expect(asked.at(-1)).toBe("?by=brand&period=2026-10");
    await user.selectOptions(screen.getByLabelText("Group by"), "user");
    await user.selectOptions(screen.getByLabelText("Shop"), "2");
    await vi.waitFor(() => expect(asked.at(-1)).toBe("?by=user&period=2026-10&location_id=2"));
  });

  it("has no shop picker with one shop", async () => {
    mockApi(routes(OWNER, {}, [S1]));
    renderAt("/reports/profit-cuts");
    await screen.findByRole("table", { name: "Profit by cut" });
    expect(screen.queryByLabelText("Shop")).toBeNull();
  });

  it("says there is not enough data instead of showing zero", async () => {
    mockApi(
      routes(OWNER, {
        "GET /reports/profitability": () => ({
          body: {
            ...CUTS,
            rows: [],
            profit_per_ton: null,
            enough_data: false,
            data_note: "Not enough data yet: no bills in this month.",
          },
        }),
      }),
    );
    renderAt("/reports/profit-cuts");
    expect(await screen.findByText(/Not enough data yet/)).toBeVisible();
    expect(screen.queryByRole("table", { name: "Profit by cut" })).toBeNull();
  });

  it("is owner only", async () => {
    mockApi({ ...session(ACCOUNTANT), "GET /locations": () => ({ body: [S1] }) });
    renderAt("/reports/profit-cuts");
    expect(await screen.findByRole("heading", { name: "Reports" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Profit per ton" })).toBeNull();
  });
});

const ROW_RISK = {
  gstin: "33BBBBB1234B1Z5",
  supplier: "Mills",
  number: "B-2",
  bill_date: "2026-10-04",
  taxable: "100000.00",
  itc: "18000.00",
  portal_itc: null,
  at_risk: "18000.00",
};
const RISK = {
  period: "2026-10",
  has_2b: true,
  note: null,
  file_name: "2b.csv",
  missing_itc: "18000.00",
  missing: [ROW_RISK],
  mismatch_itc: "20.00",
  mismatches: [
    { ...ROW_RISK, number: "B-3", itc: "36000.00", portal_itc: "35980.00", at_risk: "20.00" },
  ],
  at_risk_total: "18020.00",
  no_gstin_itc: "0.00",
  payable_estimate: "-153000.00",
  payable_if_unclaimed: "-134980.00",
  payable_to_date: true,
  due_date: "2026-11-20",
};

describe("ITC at risk", () => {
  it("lists bills in the books but not in 2B, and the payable estimate", async () => {
    mockApi(routes(ACCOUNTANT, { "GET /gst/itc-at-risk": () => ({ body: RISK }) }));
    renderAt("/reports/itc-risk");
    const missing = await screen.findByRole("table", { name: "In our books, not in GSTR-2B" });
    expect(within(missing).getByText("B-2")).toBeVisible();
    expect(screen.getAllByText("₹18,020.00").length).toBeGreaterThan(0);
    const mismatch = screen.getByRole("table", {
      name: "In both, but the supplier reported less tax",
    });
    expect(within(mismatch).getByText("35,980.00")).toBeVisible();
    expect(screen.getByText(/Due on 2026-11-20/)).toBeVisible();
    expect(screen.getByText("GST payable, so far this month")).toBeVisible();
  });

  it("shows a note, not a made-up figure, when no 2B is imported", async () => {
    mockApi(
      routes(OWNER, {
        "GET /gst/itc-at-risk": () => ({
          body: {
            ...RISK,
            has_2b: false,
            note: "No GSTR-2B imported for this month",
            missing_itc: null,
            missing: [],
            mismatch_itc: null,
            mismatches: [],
            at_risk_total: null,
            payable_if_unclaimed: null,
          },
        }),
      }),
    );
    renderAt("/reports/itc-risk");
    expect(await screen.findByText(/No GSTR-2B imported for this month/)).toBeVisible();
    expect(screen.getByText("Not known until GSTR-2B is imported.")).toBeVisible();
    expect(screen.queryByRole("table", { name: "In our books, not in GSTR-2B" })).toBeNull();
  });

  it("is not offered to counter staff", async () => {
    mockApi({ ...session(COUNTER), "GET /locations": () => ({ body: [S1] }) });
    renderAt("/reports/itc-risk");
    expect(await screen.findByRole("heading", { name: "Reports" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "ITC at risk" })).toBeNull();
  });
});
