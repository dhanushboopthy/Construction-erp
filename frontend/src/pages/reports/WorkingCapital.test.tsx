import { render, screen, within } from "@testing-library/react";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, S1, session } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const REPORT = {
  period: "2026-09",
  date_from: "2026-09-01",
  date_to: "2026-09-30",
  days: 30,
  enough_data: true,
  data_note: null,
  stock_start: "11000000.00",
  stock_end: "13000000.00",
  receivables_start: "4000000.00",
  receivables_end: "5000000.00",
  payables_start: "1500000.00",
  payables_end: "2500000.00",
  advances_start: "3500000.00",
  advances_end: "4500000.00",
  cogs: "19300000.00",
  credit_sales: "6000000.00",
  purchases: "19500000.00",
  collections: "5500000.00",
  dio_days: "18.7",
  dso_days: "22.5",
  dpo_days: "3.1",
  advance_days: "6.2",
  ccc_days: "44.3",
  inventory_turnover: "1.61",
  collection_efficiency_pct: "55.00",
  cash_tied_up: "22500000.00",
  working_capital: "20000000.00",
  trend: [
    {
      period: "2026-09",
      enough_data: true,
      dio_days: "18.7",
      dso_days: "22.5",
      dpo_days: "3.1",
      advance_days: "6.2",
      ccc_days: "44.3",
      cash_tied_up: "22500000.00",
    },
    {
      period: "2026-08",
      enough_data: false,
      dio_days: null,
      dso_days: null,
      dpo_days: null,
      advance_days: null,
      ccc_days: null,
      cash_tied_up: "20000000.00",
    },
  ],
};
const KPIS = ["ccc_days", "dio_days", "dso_days"].map((code) => ({
  code,
  name:
    code === "ccc_days"
      ? "Cash conversion cycle"
      : code === "dio_days"
        ? "Days inventory outstanding"
        : "Days sales outstanding",
  formula: "a + b",
  meaning: "meaning",
  example: "e.g.",
  sources: "ledger",
  owner_only: true,
  refresh: "monthly",
  good: "down",
  unit: "days",
}));

function routes(report: unknown) {
  return {
    ...session(OWNER),
    "GET /locations": () => ({ body: [S1] }),
    "GET /reports/today": () => ({ body: { as_of: "2026-09-30" } }),
    "GET /kpis/definitions": () => ({ body: KPIS }),
    "GET /reports/working-capital": () => ({ body: report }),
  };
}

describe("Working capital", () => {
  it("shows the cycle in days and what is tied up", async () => {
    mockApi(routes(REPORT));
    renderAt("/reports/working-capital");
    expect(await screen.findByText("44.3 days")).toBeVisible();
    expect(screen.getByText("18.7 days")).toBeVisible();
    expect(screen.getByText("22.5 days")).toBeVisible();
    expect(screen.getAllByText("₹2,25,00,000.00").length).toBeGreaterThan(0);
    const balances = screen.getByRole("table", { name: "Balances and flows" });
    expect(within(balances).getByText("₹1,30,00,000.00")).toBeVisible();
    const trend = screen.getByRole("table", { name: "Trend by month" });
    expect(within(trend).getByText("2026-08")).toBeVisible();
    expect(within(trend).getAllByText("—").length).toBeGreaterThan(0);
  });

  it("never invents days when there is too little history", async () => {
    mockApi(
      routes({
        ...REPORT,
        enough_data: false,
        data_note: "Not enough data yet (needs 7 days of bills in the month).",
        dio_days: null,
        dso_days: null,
        dpo_days: null,
        advance_days: null,
        ccc_days: null,
        inventory_turnover: null,
        collection_efficiency_pct: null,
      }),
    );
    renderAt("/reports/working-capital");
    expect(await screen.findByText(/Not enough data yet \(needs 7 days/)).toBeVisible();
    expect(screen.queryByText(/^\d+(\.\d)? days$/)).toBeNull();
  });

  it("is for the owner only", async () => {
    mockApi({ ...session(COUNTER), "GET /locations": () => ({ body: [S1] }) });
    renderAt("/reports/working-capital");
    expect(await screen.findByRole("heading", { name: "Reports" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Working capital" })).toBeNull();
  });
});
