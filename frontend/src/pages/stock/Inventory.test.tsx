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

const ROW = {
  item_id: 10,
  item_name: "TMT bar 12 mm Fe500D",
  category: "tmt",
  base_unit: "kg",
  on_hand: "23000.000",
  avg_cost: "55.0000",
  value: "1265000.00",
  last_movement: "2026-10-05",
  age_days: 5,
  age_bucket: "0-30",
  days_sold: 3,
  consumption: "165000.00",
  abc: "A",
  fsn: "S",
  avg_daily_sales: "100.000",
  cover_days: "230.0",
  lead_days: 7,
  safety_days: 2,
  reorder_point: "900.000",
  short_by: "0.000",
  reorder_now: false,
};
const CEMENT = {
  ...ROW,
  item_id: 11,
  item_name: "Cement PPC",
  base_unit: "bag",
  on_hand: "160.000",
  abc: "B",
  cover_days: "160.0",
  lead_days: 200,
  reorder_point: "205.000",
  short_by: "45.000",
  reorder_now: true,
};
const OLD = {
  ...ROW,
  item_id: 12,
  item_name: "Old Pipe",
  on_hand: "40.000",
  value: "14000.00",
  age_days: 200,
  age_bucket: "180+",
  fsn: "N",
  abc: null,
  avg_daily_sales: "0.000",
  cover_days: null,
  reorder_point: null,
  short_by: null,
};
const ANALYTICS = {
  as_of: "2026-10-10",
  history_days: 101,
  enough_data: true,
  data_note: null,
  default_lead_days: 7,
  default_safety_days: 2,
  fsn_fast_min_days: 15,
  stock_value: "1335000.00",
  dead_stock_value: "14000.00",
  aging: [
    { bucket: "0-30", value: "1321000.00", items: 2 },
    { bucket: "31-90", value: "0.00", items: 0 },
    { bucket: "91-180", value: "0.00", items: 0 },
    { bucket: "180+", value: "14000.00", items: 1 },
  ],
  rows: [CEMENT, ROW, OLD],
};
const FIFO = {
  as_of: "2026-10-10",
  note: "An estimate: stock is taken to be sold oldest first.",
  items: [
    {
      item_id: 11,
      item_name: "Cement PPC",
      base_unit: "bag",
      on_hand: "160.000",
      oldest_age_days: 100,
      buckets: { "0-30": "100.000", "31-60": "50.000", "61-90": "0", "90+": "10.000" },
      over_90_value: "3500.00",
      layers: [],
    },
  ],
};
const KPIS = [
  "dead_stock_value",
  "reorder_point",
  "nrv",
  "holding_gain_loss",
  "shrinkage_value",
].map((code) => ({
  code,
  name: code,
  formula: "f",
  meaning: "m",
  example: "e",
  sources: "s",
  owner_only: true,
  refresh: "daily",
  good: "down",
  unit: "₹",
}));

function base(user: User, extra: Record<string, () => { status?: number; body?: unknown }> = {}) {
  return {
    ...session(user),
    "GET /locations": () => ({ body: [S1] }),
    "GET /kpis/definitions": () => ({ body: KPIS }),
    ...extra,
  };
}

describe("Stock analysis", () => {
  it("lists what to reorder, how old the stock is and the cement by age", async () => {
    mockApi(
      base(OWNER, {
        "GET /inventory/analytics": () => ({ body: ANALYTICS }),
        "GET /inventory/fifo-age": () => ({ body: FIFO }),
      }),
    );
    renderAt("/stock/analysis");
    const reorder = await screen.findByRole("table", { name: "Items to reorder" });
    expect(within(reorder).getByText("Cement PPC")).toBeVisible();
    expect(within(reorder).getByText("205")).toBeVisible();
    expect(within(reorder).getByText("45")).toBeVisible();
    expect(within(reorder).queryByText("TMT bar 12 mm Fe500D")).toBeNull();
    const age = screen.getByRole("table", { name: "Stock by age" });
    expect(within(age).getByText("Over 180 days")).toBeVisible();
    expect(within(age).getByText("₹14,000.00")).toBeVisible();
    const all = screen.getByRole("table", { name: "Stock analysis" });
    expect(within(all).getByText("Not moving")).toBeVisible();
    expect(within(all).getAllByText("Slow").length).toBeGreaterThan(0);
    const cement = await screen.findByRole("table", { name: "Cement by age" });
    expect(within(cement).getByText("100 days")).toBeVisible();
    expect(within(cement).getByText(/10 \(₹3,500.00\)/)).toBeVisible();
  });

  it("says not enough data yet instead of showing classes it cannot know", async () => {
    mockApi(
      base(OWNER, {
        "GET /inventory/analytics": () => ({
          body: {
            ...ANALYTICS,
            history_days: 6,
            enough_data: false,
            data_note:
              "Not enough data yet (needs 30 days of bills; there are 6). Stock age is shown; classes, cover and reorder points wait.",
            rows: [
              {
                ...ROW,
                abc: null,
                fsn: null,
                cover_days: null,
                reorder_point: null,
                short_by: null,
              },
            ],
          },
        }),
        "GET /inventory/fifo-age": () => ({ body: { ...FIFO, items: [] } }),
      }),
    );
    renderAt("/stock/analysis");
    expect(await screen.findAllByText(/Not enough data yet \(needs 30 days/)).not.toHaveLength(0);
    expect(screen.getByText("Not enough data yet (needs 30 days of bills).")).toBeVisible();
  });

  it("is for the owner only", async () => {
    mockApi(base(COUNTER));
    renderAt("/stock/analysis");
    expect(
      await screen.findByRole("heading", { name: "Not available for your role" }),
    ).toBeVisible();
    expect(screen.queryByRole("link", { name: "Analysis" })).toBeNull();
  });
});

const NRV = {
  as_of: "2026-10-10",
  cost_to_sell_pct: "0.00",
  writedown_enabled: true,
  stock_value: "1279000.00",
  nrv_loss: "23000.00",
  holding_gain_loss: "0.00",
  rows: [
    {
      item_id: 10,
      item_name: "TMT bar 12 mm Fe500D",
      base_unit: "kg",
      on_hand: "23000.000",
      avg_cost: "55.0000",
      value: "1265000.00",
      market_rate: "54.000000",
      market_date: "2026-10-10",
      nrv: "54.0000",
      nrv_loss: "23000.00",
      replacement_cost: "55.0000",
      holding_gain_loss: "0.00",
    },
    {
      item_id: 12,
      item_name: "Old Pipe",
      base_unit: "piece",
      on_hand: "40.000",
      avg_cost: "350.0000",
      value: "14000.00",
      market_rate: null,
      market_date: null,
      nrv: null,
      nrv_loss: "0.00",
      replacement_cost: null,
      holding_gain_loss: null,
    },
  ],
};

describe("Stock value", () => {
  it("shows the loss against the market and lets the owner write it down", async () => {
    const user = userEvent.setup();
    const saved = {
      id: 1,
      number: "S1N/26-27/00001",
      location_id: 1,
      writedown_date: "2026-10-10",
      note: "Market fell",
      total: "23000.00",
      lines: [],
    };
    const { calls } = mockApi(
      base(OWNER, {
        "GET /inventory/nrv": () => ({ body: NRV }),
        "GET /inventory/writedowns": () => ({ body: [] }),
        "POST /inventory/writedowns": () => ({ status: 201, body: saved }),
      }),
    );
    renderAt("/stock/value");
    const table = await screen.findByRole("table", { name: "Stock against the market" });
    expect(within(table).getByText("₹23,000.00")).toBeVisible();
    expect(within(table).getByText("No rate")).toBeVisible();
    expect(screen.getByRole("checkbox", { name: "Write down Old Pipe" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Write down ticked items" }));
    expect(await screen.findByText("Tick the items to write down.")).toBeVisible();
    await user.click(screen.getByRole("checkbox", { name: "Write down TMT bar 12 mm Fe500D" }));
    await user.type(screen.getByLabelText("Note"), "Market fell");
    await user.click(screen.getByRole("button", { name: "Write down ticked items" }));
    expect(await screen.findByText(/Written down: S1N\/26-27\/00001/)).toBeVisible();
    const post = calls.find((c) => c.method === "POST" && c.path === "/inventory/writedowns");
    expect(post?.body).toEqual({ location_id: 1, item_ids: [10], note: "Market fell" });
  });

  it("explains a refusal in the shop's words", async () => {
    const user = userEvent.setup();
    mockApi(
      base(OWNER, {
        "GET /inventory/nrv": () => ({ body: NRV }),
        "GET /inventory/writedowns": () => ({ body: [] }),
        "POST /inventory/writedowns": () => ({
          status: 409,
          body: {
            code: "NOTHING_TO_WRITE_DOWN",
            message: "TMT is not worth less than it cost today.",
          },
        }),
      }),
    );
    renderAt("/stock/value");
    await screen.findByRole("table", { name: "Stock against the market" });
    await user.click(screen.getByRole("checkbox", { name: "Write down TMT bar 12 mm Fe500D" }));
    await user.click(screen.getByRole("button", { name: "Write down ticked items" }));
    expect(await screen.findByText("TMT is not worth less than it cost today.")).toBeVisible();
  });

  it("shows the accountant the loss but no way to write it down, and says when it is off", async () => {
    mockApi(
      base(ACCOUNTANT, {
        "GET /inventory/nrv": () => ({ body: { ...NRV, writedown_enabled: false } }),
        "GET /inventory/writedowns": () => ({ body: [] }),
      }),
    );
    renderAt("/stock/value");
    await screen.findByRole("table", { name: "Stock against the market" });
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("form", { name: "Write stock down" })).toBeNull();
    expect(screen.getByText(/switched off in Settings/)).toBeVisible();
  });
});

describe("Weight shortages", () => {
  it("lists suppliers by what was short and the lines to claim", async () => {
    mockApi(
      base(ACCOUNTANT, {
        "GET /inventory/shrinkage": () => ({
          body: {
            date_from: "2026-07-13",
            date_to: "2026-10-10",
            shortage_value: "420.00",
            suppliers: [
              {
                party_id: 5,
                party_name: "Wire Co",
                lines: 1,
                goods_value: "70000.00",
                shortage_value: "420.00",
                shortage_pct: "0.60",
                short_lines: 1,
              },
            ],
            claims: [
              {
                purchase_number: "S1P/26-27/00004",
                bill_no: "W-1",
                bill_date: "2026-09-05",
                party_name: "Wire Co",
                item_name: "Binding wire",
                base_unit: "kg",
                billed_qty: "1000.000",
                received_qty: "994.000",
                shortage_qty: "6.000",
                loss_pct: "0.60",
                value: "420.00",
              },
            ],
          },
        }),
      }),
    );
    renderAt("/stock/shortages");
    const suppliers = await screen.findByRole("table", { name: "Shortages by supplier" });
    expect(within(suppliers).getByText("Wire Co")).toBeVisible();
    expect(within(suppliers).getByText("0.60%")).toBeVisible();
    const claims = screen.getByRole("table", { name: "Shortage claims" });
    expect(within(claims).getByText("Binding wire")).toBeVisible();
    expect(within(claims).getByText("6 (0.60%)")).toBeVisible();
    expect(screen.getAllByText("₹420.00").length).toBeGreaterThan(0);
  });

  it("is not offered to counter staff", async () => {
    mockApi(base(COUNTER));
    renderAt("/stock/shortages");
    expect(
      await screen.findByRole("heading", { name: "Not available for your role" }),
    ).toBeVisible();
  });
});
