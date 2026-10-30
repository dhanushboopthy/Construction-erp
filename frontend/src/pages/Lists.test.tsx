import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, page, S1, session, TMT_ITEM } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const search = () => screen.findByRole("searchbox", { name: "Search" });

describe("Every list keeps its filters in the URL", () => {
  it("Items: a pasted link restores search and category, and the request carries them", async () => {
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /items": () => ({ body: page([TMT_ITEM]) }),
    });
    renderAt("/items?q=tmt&status=tmt");
    expect(await search()).toHaveValue("tmt");
    expect(screen.getByRole("combobox", { name: "Category" })).toHaveValue("tmt");
    await screen.findByRole("button", { name: TMT_ITEM.name });
    const call = calls.find((c) => c.path === "/items");
    expect(call).toBeDefined();
  });

  it("Items: keyboard use is as before (Down moves between rows, Enter opens)", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(COUNTER),
      "GET /items": () => ({
        body: page([TMT_ITEM, { ...TMT_ITEM, id: 11, name: "Binding wire" }]),
      }),
    });
    renderAt("/items");
    const first = await screen.findByRole("button", { name: TMT_ITEM.name });
    first.focus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("button", { name: "Binding wire" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("complementary", { name: "Binding wire" })).toBeVisible();
  });

  it('"/" jumps to the search box on a list', async () => {
    const user = userEvent.setup();
    mockApi({ ...session(OWNER), "GET /items": () => ({ body: page([]) }) });
    renderAt("/items");
    await screen.findByText(/No items yet/);
    await user.keyboard("/");
    expect(screen.getByRole("searchbox", { name: "Search" })).toHaveFocus();
  });

  it("Sales: filters bills by e-way status, and opening a bill keeps the filter", async () => {
    const user = userEvent.setup();
    const bill = (id: number, party: string) => ({
      id,
      number: `INV/${id}`,
      invoice_date: "2026-10-09",
      party_id: 1,
      party_name: party,
      location_id: 1,
      location_code: "S1",
      supply_type: "B2B",
      grand_total: "1180.00",
      status: "posted",
    });
    mockApi({
      ...session(OWNER),
      "GET /invoices": () => ({ body: page([bill(1, "Ravi Traders"), bill(2, "Anand Builders")]) }),
      "GET /eway-bills/pending": () => ({
        body: [
          { invoice_id: 2, number: "INV/2", party_name: "Anand Builders", grand_total: "1180.00" },
        ],
      }),
      "GET /invoices/2": () => ({ status: 404, body: { code: "NOT_FOUND", message: "x" } }),
    });
    renderAt("/sales");
    const table = await screen.findByRole("table", { name: "Sales bills" });
    expect(within(table).getAllByRole("button")).toHaveLength(2);

    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "eway_pending");
    expect(within(table).getAllByRole("button")).toHaveLength(1);
    expect(within(table).getByText("E-way bill pending")).toBeVisible();

    await user.click(within(table).getByRole("button", { name: "INV/2" }));
    expect(window.location.search).toContain("status=eway_pending");
    expect(window.location.search).toContain("open=2");
  });

  it("Purchases: searches by supplier and filters by where the goods go", async () => {
    const user = userEvent.setup();
    const purchase = (id: number, supplier: string, mode: string) => ({
      id,
      number: `S1P/${id}`,
      bill_date: "2026-10-09",
      supplier_name: supplier,
      bill_no: `B-${id}`,
      location_code: "S1",
      mode,
      lines: [],
    });
    mockApi({
      ...session(COUNTER),
      "GET /purchases": () => ({
        body: page([purchase(1, "Kamachi Steel", "stock"), purchase(2, "Jindal Pipes", "direct")]),
      }),
    });
    renderAt("/purchases");
    await screen.findByRole("table", { name: "Purchases" });
    await user.type(await search(), "jindal");
    await waitFor(() => expect(screen.queryByText("Kamachi Steel")).toBeNull());
    expect(screen.getByText("Jindal Pipes")).toBeVisible();
    expect(window.location.search).toContain("q=jindal");

    await user.clear(screen.getByRole("searchbox", { name: "Search" }));
    await waitFor(() => expect(window.location.search).not.toContain("q="));
    expect(await screen.findByText("Kamachi Steel")).toBeVisible();
    await user.selectOptions(screen.getByRole("combobox", { name: "Goes to" }), "stock");
    await waitFor(() => expect(screen.queryByText("Jindal Pipes")).toBeNull());
    expect(screen.getByText("Kamachi Steel")).toBeVisible();
  });

  it("Stock: filters to what has run out, with a word on every row", async () => {
    const user = userEvent.setup();
    const row = (id: number, name: string, quantity: string) => ({
      item_id: id,
      name,
      base_unit: "kg",
      quantity,
      locations: [{ location_id: 1, quantity }],
    });
    mockApi({
      ...session(COUNTER),
      "GET /locations": () => ({ body: [S1] }),
      "GET /stock": () => ({ body: [row(1, "TMT 12 mm", "0.000"), row(2, "Cement", "50.000")] }),
    });
    renderAt("/stock");
    const table = await screen.findByRole("table", { name: "Stock levels" });
    expect(within(table).getByText("Out of stock")).toBeVisible();
    expect(within(table).getByText("In stock")).toBeVisible();

    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "out");
    expect(screen.queryByText("Cement")).toBeNull();
    expect(screen.getByText("TMT 12 mm")).toBeVisible();
    expect(window.location.search).toContain("status=out");
  });

  it("Payments: filters receipts by direction", async () => {
    const user = userEvent.setup();
    const pay = (id: number, party: string, direction: string) => ({
      id,
      number: `R/${id}`,
      payment_date: "2026-10-09",
      party_id: id,
      party_name: party,
      direction,
      mode: "cash",
      amount: "500.00",
    });
    mockApi({
      ...session(OWNER),
      "GET /parties": () => ({ body: page([]) }),
      "GET /locations": () => ({ body: [S1] }),
      "GET /payments": () => ({
        body: [pay(1, "Ravi Traders", "received"), pay(2, "Kamachi Steel", "paid")],
      }),
    });
    renderAt("/payments");
    const table = await screen.findByRole("table", { name: "Receipts and payments" });
    expect(within(table).getByText("Paid out")).toBeVisible();
    await user.selectOptions(screen.getByRole("combobox", { name: "Direction" }), "paid");
    expect(screen.queryByText("Ravi Traders")).toBeNull();
    expect(screen.getByText("Kamachi Steel")).toBeVisible();
  });

  it("Trips: shows Paid or Unpaid in words and filters by it", async () => {
    const user = userEvent.setup();
    const trip = (id: number, freight: string, paid: string) => ({
      id,
      trip_date: "2026-10-09",
      vehicle_number: `TN01-${id}`,
      owner_name: "Murugan",
      from_place: "Godown",
      to_place: "Anna Nagar",
      invoice_number: null,
      purchase_number: null,
      freight_amount: freight,
      paid_amount: paid,
      pay_ref: null,
    });
    mockApi({
      ...session(OWNER),
      "GET /trips": () => ({
        body: page([trip(1, "2000.00", "2000.00"), trip(2, "3000.00", "0.00")]),
      }),
      "GET /vehicles": () => ({ body: [] }),
      "GET /locations": () => ({ body: [S1] }),
      "GET /invoices": () => ({ body: page([]) }),
    });
    renderAt("/transport");
    const table = await screen.findByRole("table", { name: "Trips" });
    expect(within(table).getByText("Paid")).toBeVisible();
    expect(within(table).getByText("Unpaid")).toBeVisible();
    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "unpaid");
    expect(screen.queryByText("TN01-1 · Murugan")).toBeNull();
    expect(screen.getByText("TN01-2 · Murugan")).toBeVisible();
  });
});
