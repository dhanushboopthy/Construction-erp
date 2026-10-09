import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, page, PARTY, S1, session, TMT_ITEM } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const WALK_IN = {
  ...PARTY,
  id: 21,
  name: "Walk-in customer",
  gstin: null,
  credit_allowed: false,
  credit_limit: null,
  sites: [],
};

const PREVIEW_OK = {
  place_of_supply: "33",
  supply_kind: "intra_state",
  supply_type: "B2C",
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
      stock_available: "5000.000",
      stock_after: "4000.000",
      problems: [],
    },
  ],
};

const SAVED = {
  id: 7,
  number: "S1/26-27/00001",
  invoice_date: "2026-10-09",
  party_id: 21,
  party_name: "Walk-in customer",
  location_id: 1,
  location_code: "S1",
  supply_type: "B2C",
  grand_total: "66080.00",
  status: "posted",
};

function routes() {
  return {
    "GET /items": () => ({ body: page([TMT_ITEM]) }),
    "GET /parties": () => ({ body: page([WALK_IN, PARTY]) }),
    "GET /locations": () => ({ body: [S1] }),
    "GET /invoices": () => ({ body: page([]) }),
  };
}

describe("Billing", () => {
  it("shows the server's rate and totals, and counter staff never type a price", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(COUNTER),
      ...routes(),
      "POST /invoices/preview": () => ({ body: PREVIEW_OK }),
      "POST /invoices": () => ({ status: 201, body: { ...SAVED, lines: [] } }),
    });
    renderAt("/sales/new");

    await screen.findByRole("option", { name: "TMT bar 12 mm Fe500D" });
    await user.selectOptions(screen.getByLabelText("Item 1"), "10");
    // Counter staff never type a price; a discount is asked for and the owner approves with a PIN.
    expect(screen.queryByLabelText(/Rate/)).toBeNull();
    await user.type(screen.getByLabelText("Quantity"), "1");
    expect(await screen.findByText("₹66,080.00", {}, { timeout: 3000 })).toBeVisible();
    expect(screen.getByText(/₹56 per kg/)).toBeVisible();
    expect(screen.getByText(/4000 kg left/)).toBeVisible();
    expect(screen.getByText(/CGST \+ SGST/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Save bill" }));
    await vi.waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.path === "/invoices")).toBe(true),
    );
    const save = calls.find((c) => c.method === "POST" && c.path === "/invoices");
    expect(save?.headers["idempotency-key"]).toMatch(/[0-9a-f-]{36}/);
    expect(save?.body).toMatchObject({
      party_id: 21,
      location_id: 1,
      lines: [{ item_id: 10, quantity: "1", source: "shop", discount: null }],
    });
  });

  it("explains a problem under the line and does not let the bill be saved", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(COUNTER),
      ...routes(),
      "POST /invoices/preview": () => ({
        body: {
          ...PREVIEW_OK,
          can_save: false,
          lines: [
            { ...PREVIEW_OK.lines[0], problems: ["Only 100 kg of TMT bar 12 mm Fe500D at S1."] },
          ],
        },
      }),
    });
    renderAt("/sales/new");
    await screen.findByRole("option", { name: "TMT bar 12 mm Fe500D" });
    await user.selectOptions(screen.getByLabelText("Item 1"), "10");
    await user.type(screen.getByLabelText("Quantity"), "500");
    expect(await screen.findByText(/Only 100 kg/, {}, { timeout: 3000 })).toBeVisible();
    expect(screen.getByRole("button", { name: "Save bill" })).toBeDisabled();
  });

  it("lets the owner discount a line, with a reason", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      ...routes(),
      "POST /invoices/preview": () => ({ body: PREVIEW_OK }),
    });
    renderAt("/sales/new");
    await screen.findByRole("option", { name: "TMT bar 12 mm Fe500D" });
    await user.selectOptions(screen.getByLabelText("Item 1"), "10");
    await user.type(screen.getByLabelText("Quantity"), "1");
    await user.type(screen.getByLabelText("Discount (₹)"), "500");
    await user.type(screen.getByLabelText("Reason for discount"), "bulk");
    await vi.waitFor(
      () => {
        const last = calls.filter((c) => c.path === "/invoices/preview").at(-1)?.body as {
          lines: { discount: string | null; discount_reason: string | null }[];
        };
        expect(last?.lines[0]).toMatchObject({ discount: "500", discount_reason: "bulk" });
      },
      { timeout: 3000 },
    );
  });

  it("lists bills and opens one with its print button", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(OWNER),
      "GET /invoices": () => ({ body: page([SAVED]) }),
      "GET /credit-notes": () => ({ body: page([]) }),
      "GET /invoices/7": () => ({
        body: {
          ...SAVED,
          financial_year: "26-27",
          site_id: null,
          bill_to_name: "Walk-in customer",
          bill_to_address: "",
          bill_to_gstin: null,
          ship_to_name: null,
          ship_to_address: null,
          ship_to_gstin: null,
          place_of_supply: "33",
          supply_kind: "intra_state",
          due_date: "2026-10-09",
          taxable_value: "56000.00",
          cgst: "5040.00",
          sgst: "5040.00",
          igst: "0.00",
          round_off: "0.00",
          pending_balance_at_billing: "0.00",
          vehicle_no: null,
          remark: null,
          profit: "1000.00",
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
              discount: "0.00",
              discount_reason: null,
              taxable: "56000.00",
              gst_rate: "18.00",
              cgst: "5040.00",
              sgst: "5040.00",
              igst: "0.00",
              line_total: "66080.00",
              fulfilment_source: "shop",
              source_location_id: 1,
              stock_after: "4000.000",
              returned_qty: "0.000",
              cost_per_unit: "55.0000",
              profit: "1000.00",
            },
          ],
        },
      }),
    });
    renderAt("/sales");
    await user.click(await screen.findByRole("button", { name: "S1/26-27/00001" }));
    const panel = await screen.findByRole("complementary", { name: "S1/26-27/00001" });
    expect(within(panel).getByRole("button", { name: "Print A4 bill" })).toBeVisible();
    expect(within(panel).getByText("Profit on this bill: ₹1,000.00")).toBeVisible();
  });
});
