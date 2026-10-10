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
  period: "2026-10",
  date_from: "2026-10-01",
  date_to: "2026-10-31",
  location_id: null,
  lines: 2,
  unpriced: 1,
  cut: "2000.00",
  raised: "0.00",
  net: "2000.00",
  discounts: "500.00",
  leakage: "2500.00",
  realisation_pct: "96.77",
  by_user: [
    {
      user_id: 1,
      user_name: "Shop Owner",
      lines: 2,
      cut: "2000.00",
      raised: "0.00",
      net: "2000.00",
      discounts: "500.00",
    },
  ],
  rows: [
    {
      invoice_id: 7,
      invoice_number: "S1/26-27/00007",
      invoice_date: "2026-10-09",
      location_id: 1,
      item_name: "TMT bar 12 mm Fe500D",
      user_id: 1,
      user_name: "Shop Owner",
      base_qty: "1000",
      base_unit: "kg",
      list_rate: "62.000000",
      billed_rate: "60.000000",
      effect: "2000.00",
      reason: "matching a competitor",
    },
  ],
};

const KPIS = [
  {
    code: "discount_leakage",
    name: "Discount leakage",
    formula: "Σ (list rate - billed rate) x quantity",
    meaning: "Money given away by cutting a price at the counter.",
    example: "1,000 kg TMT billed ₹60 against ₹62 listed = ₹2,000",
    sources: "sales_line",
    owner_only: true,
    refresh: "live",
    good: "down",
    unit: "₹",
  },
];

describe("Price overrides report", () => {
  it("shows the owner who set prices by hand, why, and the rupees given away", async () => {
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /locations": () => ({ body: [S1] }),
      "GET /reports/today": () => ({ body: { as_of: "2026-10-10" } }),
      "GET /kpis/definitions": () => ({ body: KPIS }),
      "GET /reports/rate-overrides": () => ({ body: REPORT }),
    });
    renderAt("/reports/overrides");
    const lines = await screen.findByRole("table", { name: "Hand-priced lines" });
    expect(within(lines).getByText("matching a competitor")).toBeVisible();
    expect(within(lines).getByText("S1/26-27/00007")).toBeVisible();
    expect(within(lines).getByText("₹2,000.00")).toBeVisible();
    const people = screen.getByRole("table", { name: "Price overrides by person" });
    expect(within(people).getByText("Shop Owner")).toBeVisible();
    expect(screen.getByText("₹2,500.00")).toBeVisible();
    expect(screen.getByText("96.77%")).toBeVisible();
    expect(screen.getByText(/1 hand-priced line had no rate/)).toBeVisible();
    expect(calls.some((c) => c.path === "/reports/rate-overrides")).toBe(true);
  });

  it("is not offered to counter staff", async () => {
    mockApi({
      ...session(COUNTER),
      "GET /locations": () => ({ body: [S1] }),
    });
    renderAt("/reports/overrides");
    expect(await screen.findByRole("heading", { name: "Reports" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Price overrides" })).toBeNull();
    expect(screen.queryByRole("table", { name: "Hand-priced lines" })).toBeNull();
  });

  it("says plainly when nobody set a price by hand", async () => {
    mockApi({
      ...session(OWNER),
      "GET /locations": () => ({ body: [S1] }),
      "GET /reports/today": () => ({ body: { as_of: "2026-10-10" } }),
      "GET /kpis/definitions": () => ({ body: KPIS }),
      "GET /reports/rate-overrides": () => ({
        body: {
          ...REPORT,
          lines: 0,
          unpriced: 0,
          cut: "0.00",
          discounts: "0.00",
          leakage: "0.00",
          realisation_pct: null,
          by_user: [],
          rows: [],
        },
      }),
    });
    renderAt("/reports/overrides");
    expect(await screen.findByText("No hand-set prices or discounts this month.")).toBeVisible();
    expect(screen.getByText(/Not enough data yet/)).toBeVisible();
  });
});
