import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, G1, mockApi, OWNER, PARTY, page, S1, session, TMT_ITEM } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const DRAFT = {
  id: 1,
  kind: "stock",
  status: "draft",
  as_of: "2026-10-09",
  item_id: 10,
  item_name: "TMT bar 12 mm Fe500D",
  base_unit: "kg",
  location_id: 1,
  location_code: "S1",
  quantity: "4000.000",
  unit_cost: "55.0000",
  party_id: null,
  site_id: null,
  amount: null,
  note: null,
  posted_at: null,
};

describe("Opening balances", () => {
  it("adds a stock row, then posts only after a second confirmation", async () => {
    const user = userEvent.setup();
    const rows: object[] = [];
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /opening": () => ({ body: rows }),
      "GET /items": () => ({ body: page([TMT_ITEM]) }),
      "GET /locations": () => ({ body: [S1, G1] }),
      "POST /opening": (body) => {
        rows.push({ ...DRAFT, ...(body as object) });
        return { status: 201, body: DRAFT };
      },
      "POST /opening/post": () => ({ body: { posted: 1, stock_rows: 1, party_rows: 0 } }),
    });
    renderAt("/settings/opening");

    expect(await screen.findByText("Nothing entered for this step yet.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Add row" }));
    expect(await screen.findByText("Pick the item and the place it is kept.")).toBeVisible();

    await user.selectOptions(screen.getByLabelText("Item"), "10");
    await user.selectOptions(screen.getByLabelText("Kept at"), "1");
    await user.type(screen.getByLabelText(/Quantity/), "4000");
    await user.type(screen.getByLabelText(/Cost per/), "55");
    await user.click(screen.getByRole("button", { name: "Add row" }));
    expect(await screen.findByText("Added TMT bar 12 mm Fe500D.")).toBeVisible();
    expect(calls.find((c) => c.method === "POST" && c.path === "/opening")?.body).toMatchObject({
      kind: "stock",
      item_id: 10,
      location_id: 1,
      quantity: "4000",
      unit_cost: "55",
    });

    // The first click only asks; nothing is posted yet.
    await user.click(await screen.findByRole("button", { name: "Post 1 entry" }));
    expect(calls.some((c) => c.path === "/opening/post")).toBe(false);
    expect(screen.getByText(/This cannot be undone/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Not yet" }));
    expect(calls.some((c) => c.path === "/opening/post")).toBe(false);

    await user.click(screen.getByRole("button", { name: "Post 1 entry" }));
    await user.click(screen.getByRole("button", { name: "Yes, post 1 entry" }));
    expect(await screen.findByText("Posted 1 entry to the ledger.")).toBeVisible();
    expect(calls.find((c) => c.path === "/opening/post")?.body).toEqual({ kinds: ["stock"] });
  });

  it("enters a customer due for a site", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /opening": () => ({ body: [] }),
      "GET /parties": () => ({ body: page([PARTY]) }),
      "POST /opening": () => ({ status: 201, body: DRAFT }),
    });
    renderAt("/settings/opening");

    await user.click(await screen.findByRole("button", { name: "2. Customers owe us" }));
    await user.selectOptions(await screen.findByLabelText("Customer"), "20");
    await user.selectOptions(screen.getByLabelText("Site"), "30");
    await user.type(screen.getByLabelText("Amount (₹)"), "12500.50");
    await user.click(screen.getByRole("button", { name: "Add row" }));
    await screen.findByText("Added Ravi Builders.");
    expect(calls.find((c) => c.method === "POST" && c.path === "/opening")?.body).toMatchObject({
      kind: "receivable",
      party_id: 20,
      site_id: 30,
      amount: "12500.50",
    });
  });
});

describe("Stock screen", () => {
  const rows = [
    {
      item_id: 10,
      name: "TMT bar 12 mm Fe500D",
      category: "tmt",
      base_unit: "kg",
      quantity: "10000.000",
      locations: [
        { location_id: 1, code: "S1", name: "Shop 1", quantity: "4000.000" },
        { location_id: 3, code: "G1", name: "Godown", quantity: "6000.000" },
      ],
    },
  ];

  it("shows the owner cost and value", async () => {
    mockApi({
      ...session(OWNER),
      "GET /locations": () => ({ body: [S1, G1] }),
      "GET /stock": () => ({
        body: rows.map((r) => ({ ...r, avg_cost: "55.9000", value: "559000.00" })),
      }),
    });
    renderAt("/stock");
    const table = await screen.findByRole("table");
    expect(within(table).getByText("10000")).toBeVisible();
    expect(within(table).getByText("55.9")).toBeVisible();
    expect(within(table).getAllByText("5,59,000.00").length).toBeGreaterThan(0);
  });

  it("shows counter staff quantities only", async () => {
    mockApi({
      ...session(COUNTER),
      "GET /locations": () => ({ body: [S1, G1] }),
      "GET /stock": () => ({ body: rows }),
    });
    renderAt("/stock");
    const table = await screen.findByRole("table");
    expect(within(table).getByText("10000")).toBeVisible();
    expect(screen.queryByText(/Avg cost/)).toBeNull();
    expect(screen.queryByText(/Stock value/)).toBeNull();
  });
});
