import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, page, PARTY, S1, session, TMT_ITEM } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const PREVIEW = {
  place_of_supply: "33",
  supply_kind: "intra_state",
  supply_type: "B2B",
  pending_balance: "0.00",
  taxable_value: "56000.00",
  cgst: "5040.00",
  sgst: "5040.00",
  igst: "0.00",
  round_off: "0.00",
  grand_total: "66080.00",
  paid_now: "0.00",
  balance_due: "66080.00",
  invoice_problems: [],
  needs_owner: false,
  approvals_needed: [],
  can_save: true,
  lines: [
    {
      item_id: 10,
      description: "TMT bar 12 mm Fe500D",
      unit: "ton",
      quantity: "1.000",
      base_qty: "1000.000",
      base_unit: "kg",
      rate: "56.000000",
      rate_source: "market",
      discount: "0.00",
      taxable: "56000.00",
      gst_rate: "18.00",
      tax: "10080.00",
      line_total: "66080.00",
      fulfilment_source: "shop",
      stock_available: null,
      stock_after: null,
      problems: [],
    },
  ],
};

const QUOTE = {
  id: 4,
  kind: "quotation",
  number: "S1Q/26-27/00001",
  quote_date: "2026-10-28",
  valid_until: null,
  party_id: PARTY.id,
  party_name: PARTY.name,
  location_id: 1,
  location_code: "S1",
  grand_total: "66080.00",
  invoice_id: null,
  invoice_number: null,
  site_id: null,
  bill_to_gstin: null,
  ship_to_name: null,
  place_of_supply: "33",
  supply_kind: "intra_state",
  supply_type: "B2B",
  taxable_value: "56000.00",
  cgst: "5040.00",
  sgst: "5040.00",
  igst: "0.00",
  round_off: "0.00",
  remark: null,
  lines: [
    {
      id: 1,
      line_no: 1,
      item_id: 10,
      description: "TMT bar 12 mm Fe500D",
      hsn: "72142090",
      unit: "ton",
      quantity: "1.000",
      base_qty: "1000.000",
      base_unit: "kg",
      rate: "56.000000",
      rate_source: "market",
      rate_override_reason: null,
      discount: "0.00",
      discount_reason: null,
      taxable: "56000.00",
      gst_rate: "18.00",
      cgst: "5040.00",
      sgst: "5040.00",
      igst: "0.00",
      line_total: "66080.00",
    },
  ],
};

function routes() {
  return {
    "GET /items": () => ({ body: page([TMT_ITEM]) }),
    "GET /parties": () => ({ body: page([PARTY]) }),
    "GET /locations": () => ({ body: [S1] }),
  };
}

describe("Quotations and proforma invoices", () => {
  it("saves a quotation without payments, through the quotation endpoints", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(COUNTER),
      ...routes(),
      "POST /quotes/preview": () => ({ body: PREVIEW }),
      "POST /quotes": () => ({ status: 201, body: QUOTE }),
      "GET /quotes": () => ({ body: page([QUOTE]) }),
      "GET /quotes/4": () => ({ body: QUOTE }),
    });
    renderAt("/sales/new");

    await screen.findByRole("option", { name: "TMT bar 12 mm Fe500D" });
    await user.selectOptions(screen.getByLabelText("Document"), "quotation");
    expect(screen.getByRole("heading", { name: "New quotation" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Add payment" })).toBeNull();
    expect(screen.queryByLabelText("Taken from")).toBeNull();
    await user.selectOptions(screen.getByLabelText("Customer"), String(PARTY.id));
    await user.selectOptions(screen.getByLabelText("Item 1"), "10");
    await user.type(screen.getByLabelText("Quantity"), "1");
    expect(await screen.findByText("₹66,080.00", {}, { timeout: 3000 })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Save quotation" }));

    expect(await screen.findByRole("complementary", { name: "S1Q/26-27/00001" })).toBeVisible();
    expect(calls.some((c) => c.method === "POST" && c.path === "/invoices")).toBe(false);
    const sent = calls.find((c) => c.method === "POST" && c.path === "/quotes")?.body;
    expect(sent).toMatchObject({
      kind: "quotation",
      party_id: PARTY.id,
      lines: [{ item_id: 10, quantity: "1", source: "shop" }],
    });
    expect(sent).not.toHaveProperty("payments");
  });

  it("makes the bill from a quotation and links it", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(COUNTER),
      ...routes(),
      "GET /quotes": () => ({ body: page([QUOTE]) }),
      "GET /quotes/4": () => ({ body: QUOTE }),
      "POST /invoices/preview": () => ({ body: PREVIEW }),
      "POST /invoices": () => ({
        status: 201,
        body: { ...QUOTE, id: 9, number: "S1/26-27/00009", lines: [] },
      }),
      "GET /invoices": () => ({ body: page([]) }),
      "GET /credit-notes": () => ({ body: page([]) }),
    });
    renderAt("/sales/quotes?open=4");

    const panel = await screen.findByRole("complementary", { name: "S1Q/26-27/00001" });
    await user.click(within(panel).getByRole("button", { name: "Make the bill" }));
    expect(await screen.findByText(/Billing quotation S1Q\/26-27\/00001/)).toBeVisible();
    await vi.waitFor(() => expect(screen.getByLabelText("Item 1")).toHaveValue("10"));
    expect(screen.queryByLabelText("Document")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Save bill" }));
    await vi.waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.path === "/invoices")).toBe(true),
    );
    expect(calls.find((c) => c.method === "POST" && c.path === "/invoices")?.body).toMatchObject({
      quote_id: 4,
      party_id: PARTY.id,
      lines: [{ item_id: 10, quantity: "1", unit: "ton" }],
    });
  });

  it("shows which bill a quotation became, and offers no second bill", async () => {
    mockApi({
      ...session(COUNTER),
      "GET /quotes": () => ({ body: page([]) }),
      "GET /quotes/4": () => ({
        body: { ...QUOTE, invoice_id: 9, invoice_number: "S1/26-27/00009" },
      }),
    });
    renderAt("/sales/quotes?open=4");
    const panel = await screen.findByRole("complementary", { name: "S1Q/26-27/00001" });
    expect(within(panel).getByRole("button", { name: "S1/26-27/00009" })).toBeVisible();
    expect(within(panel).queryByRole("button", { name: "Make the bill" })).toBeNull();
  });
});
