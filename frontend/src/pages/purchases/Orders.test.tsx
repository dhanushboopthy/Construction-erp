import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import type { User } from "@/api/types";
import {
  COMPONENTS,
  COUNTER,
  mockApi,
  OWNER,
  page,
  S1,
  session,
  SUPPLIER,
  TMT_ITEM,
} from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const ACCOUNTANT: User = { ...OWNER, id: 3, username: "accounts", role: "accountant" };
const CEMENT = {
  ...TMT_ITEM,
  id: 11,
  name: "Cement PPC",
  category: "cement" as const,
  base_unit: "bag",
  base_whole_only: true,
  gst_rate: "28.00",
  units: [],
};

const LINE = {
  id: 5,
  line_no: 1,
  item_id: 10,
  item_name: "TMT bar 12 mm Fe500D",
  unit: "ton",
  quantity: "10.000",
  base_qty: "10000.000",
  base_unit: "kg",
  received_qty: "9800.000",
  billed_qty: "0.000",
};
const STAFF_ORDER = {
  id: 3,
  number: "S1O/26-27/00001",
  supplier_id: 40,
  supplier_name: "Steel Mills",
  location_id: 1,
  location_code: "S1",
  order_date: "2026-10-08",
  expected_date: null,
  note: null,
  status: "open",
  lines: [LINE],
  receipts: [
    {
      id: 1,
      number: "S1G/26-27/00001",
      receipt_date: "2026-10-09",
      note: null,
      lines: [],
    },
  ],
  bills: [],
};
const OWNER_ORDER = {
  ...STAFF_ORDER,
  value: "550000.00",
  lines: [{ ...LINE, rate: "55000.0000", value: "550000.00" }],
};

const KPIS = [
  {
    code: "ppv",
    name: "Purchase price variance",
    formula: "Σ (bill rate - order rate) x quantity",
    meaning: "Money paid above the order rate.",
    example: "₹5,000 over",
    sources: "purchase_line",
    owner_only: true,
    refresh: "live",
    good: "down",
    unit: "₹",
  },
  {
    code: "fill_rate",
    name: "Fill rate",
    formula: "Supplied ÷ asked for",
    meaning: "How often a customer gets what they ask for.",
    example: "90 ÷ 100 = 90 %",
    sources: "sales_line, lost_sale",
    owner_only: false,
    refresh: "live",
    good: "up",
    unit: "%",
  },
];

describe("Purchase orders", () => {
  it("shows the owner rates and value, and counter staff quantities only", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(OWNER),
      "GET /locations": () => ({ body: [S1] }),
      "GET /items": () => ({ body: page([TMT_ITEM]) }),
      "GET /parties": () => ({ body: page([SUPPLIER]) }),
      "GET /purchase-orders": () => ({ body: [OWNER_ORDER] }),
    });
    renderAt("/purchases/orders");
    const table = await screen.findByRole("table", { name: "Purchase orders" });
    expect(await within(table).findByText("5,50,000.00")).toBeVisible();
    await user.click(within(table).getByRole("button", { name: "S1O/26-27/00001" }));
    expect(await screen.findByText(/55,000.00 per ton/)).toBeVisible();
  });

  it("lets a counter user record goods received but not see a rate", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(COUNTER),
      "GET /locations": () => ({ body: [S1] }),
      "GET /purchase-orders": () => ({ body: [STAFF_ORDER] }),
      "POST /purchase-orders/3/receipts": () => ({
        status: 201,
        body: { number: "S1G/26-27/00002" },
      }),
    });
    renderAt("/purchases/orders");
    await user.click(await screen.findByRole("button", { name: "S1O/26-27/00001" }));
    expect(screen.queryByText(/per ton/)).toBeNull();
    expect(screen.queryByLabelText("Supplier")).toBeNull(); // only the owner places orders
    await user.type(screen.getByLabelText(/Arrived: TMT bar/), "0.2");
    await user.click(screen.getByRole("button", { name: "Record goods received" }));
    expect(await screen.findByText(/S1G\/26-27\/00002 recorded/)).toBeVisible();
    const sent = calls.find((c) => c.method === "POST" && c.path === "/purchase-orders/3/receipts");
    expect(sent?.body).toEqual({ lines: [{ order_line_id: 5, quantity: "0.2" }] });
  });

  it("places an order for the owner", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /locations": () => ({ body: [S1] }),
      "GET /items": () => ({ body: page([TMT_ITEM]) }),
      "GET /parties": () => ({ body: page([SUPPLIER]) }),
      "GET /purchase-orders": () => ({ body: [] }),
      "POST /purchase-orders": () => ({ status: 201, body: OWNER_ORDER }),
    });
    renderAt("/purchases/orders");
    await screen.findByRole("option", { name: "Steel Mills" });
    await user.click(screen.getByRole("button", { name: "Place order" }));
    expect(await screen.findByText(/Pick the supplier/)).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Supplier"), "40");
    await user.selectOptions(screen.getByLabelText("Goods go to"), "1");
    await user.selectOptions(screen.getByLabelText("Item 1"), "10");
    await user.type(screen.getByLabelText("Quantity"), "10");
    await user.type(screen.getByLabelText(/Agreed rate per ton/), "55000");
    await user.click(screen.getByRole("button", { name: "Place order" }));
    expect(await screen.findByText("S1O/26-27/00001 placed.")).toBeVisible();
    const sent = calls.find((c) => c.method === "POST" && c.path === "/purchase-orders");
    expect(sent?.body).toMatchObject({
      supplier_id: 40,
      location_id: 1,
      lines: [{ item_id: 10, unit: "ton", quantity: "10", rate: "55000" }],
    });
  });
});

describe("Bill against an order", () => {
  function entryRoutes(post: (body: unknown) => { status?: number; body?: unknown }) {
    return {
      ...session(COUNTER),
      "GET /locations": () => ({ body: [S1] }),
      "GET /items": () => ({ body: page([TMT_ITEM, CEMENT]) }),
      "GET /parties": () => ({ body: page([SUPPLIER]) }),
      "GET /cost-components": () => ({ body: COMPONENTS }),
      "GET /purchase-orders": () => ({ body: [STAFF_ORDER] }),
      "GET /purchases": () => ({ body: page([]) }),
      "POST /purchases": post,
      "POST /approvals": () => ({ status: 201, body: { id: 77 } }),
    };
  }

  it("asks for the owner's PIN when the bill differs from its order, then saves with it", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    const { calls } = mockApi(
      entryRoutes(() => {
        attempts += 1;
        return attempts === 1
          ? {
              status: 409,
              body: {
                code: "MATCH_EXCEPTION",
                message:
                  "This bill does not match its order. TMT: The bill is for more than was received.",
                field: "purchase_order_id",
                requires_owner_approval: true,
              },
            }
          : { status: 201, body: { number: "S1P/26-27/00001" } };
      }),
    );
    renderAt("/purchases/new");
    await screen.findByRole("option", { name: "Steel Mills" });
    await screen.findByRole("option", { name: TMT_ITEM.name });
    await user.selectOptions(screen.getByLabelText("Supplier"), "40");
    await user.selectOptions(screen.getByLabelText("Goods arrive at"), "1");
    await user.selectOptions(await screen.findByLabelText("Against order"), "3");
    await user.type(screen.getByLabelText("Supplier's bill no."), "B-1");
    await user.selectOptions(screen.getByLabelText("Item 1"), "10");
    await user.type(screen.getByLabelText("Billed qty"), "10");
    await user.type(screen.getByLabelText(/Rate per ton/), "55000");
    await user.click(screen.getByRole("button", { name: "Save purchase" }));

    expect(
      await screen.findByText(/Owner approval needed to save a bill that differs from its order/),
    ).toBeVisible();
    expect(screen.getByText(/more than was received/)).toBeVisible();
    await user.type(screen.getByLabelText("Owner PIN"), "4821");
    await user.type(screen.getByLabelText("Reason"), "Short weight agreed with supplier");
    await user.click(screen.getByRole("button", { name: "Approve with PIN" }));

    await vi.waitFor(() => expect(attempts).toBe(2));
    const posts = calls.filter((c) => c.method === "POST" && c.path === "/purchases");
    expect(posts[0]?.body).toMatchObject({ purchase_order_id: 3, approval_ids: [] });
    expect(posts[1]?.body).toMatchObject({ purchase_order_id: 3, approval_ids: [77] });
    const asked = calls.find((c) => c.path === "/approvals");
    expect(asked?.body).toMatchObject({ action: "po_mismatch", pin: "4821" });
  });

  it("offers the week made for cement only", async () => {
    const user = userEvent.setup();
    mockApi(entryRoutes(() => ({ status: 201, body: { number: "S1P/26-27/00002" } })));
    renderAt("/purchases/new");
    await screen.findByRole("option", { name: "Cement PPC" });
    await user.selectOptions(screen.getByLabelText("Item 1"), "10");
    expect(screen.queryByLabelText("Week made (on the bag)")).toBeNull();
    await user.selectOptions(screen.getByLabelText("Item 1"), "11");
    expect(screen.getByLabelText("Week made (on the bag)")).toBeVisible();
    await user.type(screen.getByLabelText("Week made (on the bag)"), "30");
    await user.click(screen.getByRole("button", { name: "Save purchase" }));
    expect(await screen.findByText("Give the week and its year, or neither.")).toBeVisible();
  });
});

describe("Order matches", () => {
  const REPORT = {
    date_from: "2026-09-10",
    date_to: "2026-10-10",
    qty_tolerance_pct: "1.00",
    rate_tolerance_pct: "0.50",
    bills_checked: 2,
    lines_checked: 2,
    exceptions: 1,
    ppv_total: "5000.00",
    rows: [
      {
        purchase_id: 2,
        purchase_number: "S1P/26-27/00002",
        bill_no: "B-2",
        bill_date: "2026-10-09",
        order_number: "S1O/26-27/00001",
        supplier_name: "Steel Mills",
        item_name: "TMT bar 12 mm Fe500D",
        base_unit: "kg",
        ordered_qty: "10000.000",
        received_qty: "9950.000",
        billed_qty: "10000.000",
        qty_over_received_pct: "0.50",
        order_rate: "55.0000",
        bill_rate: "55.5000",
        rate_variance_pct: "0.91",
        ppv: "5000.00",
        ok: false,
        reasons: ["The rate is higher than the order rate."],
        approved: false,
        entered_by_owner: true,
      },
    ],
  };

  it("lists bills out of tolerance with the PPV, for the owner only", async () => {
    mockApi({
      ...session(OWNER),
      "GET /locations": () => ({ body: [S1] }),
      "GET /reports/today": () => ({ body: { as_of: "2026-10-10" } }),
      "GET /kpis/definitions": () => ({ body: KPIS }),
      "GET /reports/match-exceptions": () => ({ body: REPORT }),
    });
    renderAt("/reports/order-match");
    const table = await screen.findByRole("table", { name: "Order match exceptions" });
    expect(within(table).getByText(/higher than the order rate/)).toBeVisible();
    expect(within(table).getByText("(entered by the owner)")).toBeVisible();
    expect(screen.getAllByText("₹5,000.00").length).toBeGreaterThan(0);
    expect(screen.getByText(/2 bills against an order, 1 out of tolerance/)).toBeVisible();
  });

  it("is not offered to the accountant", async () => {
    mockApi({ ...session(ACCOUNTANT), "GET /locations": () => ({ body: [S1] }) });
    renderAt("/reports/order-match");
    expect(await screen.findByRole("heading", { name: "Reports" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Order matches" })).toBeNull();
  });
});

describe("Lost sales", () => {
  const ENTRY = {
    id: 1,
    location_id: 1,
    location_code: "S1",
    entry_date: "2026-10-10",
    item_id: 11,
    item_name: "Cement PPC",
    unit: "bag",
    quantity: "10.000",
    base_qty: "10.000",
    base_unit: "bag",
    note: "Shelf empty",
    entered_by: "Counter, Shop 1",
    entered_at: "2026-10-10T05:00:00Z",
  };
  const FILL_ROW = {
    item_id: 11,
    item_name: "Cement PPC",
    base_unit: "bag",
    supplied_qty: "90.000",
    lost_qty: "10.000",
    requested_qty: "100.000",
    fill_rate_pct: "90.00",
    lost_value: null as string | null,
  };
  const FILL = {
    period: "2026-10",
    date_from: "2026-10-01",
    date_to: "2026-10-31",
    location_id: null,
    lines_supplied: 1,
    lines_lost: 1,
    line_fill_rate_pct: "50.00",
    lost_value: null as string | null,
    rows: [FILL_ROW],
  };

  function routes(user: User, fill = FILL, entry: object = ENTRY, extra = {}) {
    return {
      ...session(user),
      "GET /locations": () => ({ body: [S1] }),
      "GET /items": () => ({ body: page([CEMENT]) }),
      "GET /reports/today": () => ({ body: { as_of: "2026-10-10" } }),
      "GET /kpis/definitions": () => ({ body: KPIS }),
      "GET /lost-sales": () => ({ body: [entry] }),
      "GET /reports/fill-rate": () => ({ body: fill }),
      ...extra,
    };
  }

  it("lets counter staff log an ask in one step and shows quantities only", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi(
      routes(COUNTER, FILL, ENTRY, {
        "POST /lost-sales": () => ({ status: 201, body: ENTRY }),
      }),
    );
    renderAt("/stock/lost-sales");
    await screen.findByRole("table", { name: "Fill rate by item" });
    expect(screen.getByText("90.00 %")).toBeVisible();
    expect(screen.queryByText(/Lost \(₹\)/)).toBeNull();
    expect(screen.queryByText(/Sales lost, at market rate/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "Log it" }));
    expect(await screen.findByText("Pick the item the customer asked for.")).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Asked for"), "11");
    await user.type(screen.getByLabelText("How much"), "10");
    await user.type(screen.getByLabelText("Note (optional)"), "Shelf empty");
    await user.click(screen.getByRole("button", { name: "Log it" }));
    expect(await screen.findByText("Logged: 10 bag of Cement PPC.")).toBeVisible();
    const sent = calls.find((c) => c.method === "POST" && c.path === "/lost-sales");
    expect(sent?.body).toEqual({
      location_id: 1,
      item_id: 11,
      quantity: "10",
      unit: "bag",
      note: "Shelf empty",
    });
  });

  it("shows the owner what the lost sales were worth", async () => {
    mockApi(
      routes(
        OWNER,
        { ...FILL, lost_value: "3804.50", rows: [{ ...FILL_ROW, lost_value: "3804.50" }] },
        { ...ENTRY, value: "3804.50" },
      ),
    );
    renderAt("/stock/lost-sales");
    const log = await screen.findByRole("table", { name: "Lost sales log" });
    expect(await within(log).findByText("3,804.50")).toBeVisible();
    expect(await screen.findByText("₹3,804.50")).toBeVisible();
  });

  it("is not for the accountant", async () => {
    mockApi({ ...session(ACCOUNTANT), "GET /locations": () => ({ body: [S1] }) });
    renderAt("/stock/lost-sales");
    expect(await screen.findByRole("heading", { name: "Stock" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Lost sales" })).toBeNull();
  });
});
