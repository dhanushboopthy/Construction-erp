import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, page, session } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const SUMMARY = {
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

const INVOICE = {
  ...SUMMARY,
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
  paid_at_billing: "0.00",
  vehicle_no: null,
  remark: null,
  lines: [
    {
      id: 31,
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
    },
  ],
};

const NOTE = {
  id: 3,
  number: "S1C/26-27/00001",
  note_date: "2026-10-09",
  party_id: 21,
  party_name: "Walk-in customer",
  location_id: 1,
  location_code: "S1",
  reason: "Wrong size",
  grand_total: "33040.00",
  invoice_id: 7,
  invoice_number: "S1/26-27/00001",
  lines: [],
};

function routes(extra = {}) {
  return {
    "GET /invoices": () => ({ body: page([SUMMARY]) }),
    "GET /invoices/7": () => ({ body: INVOICE }),
    "GET /credit-notes": () => ({ body: page([]) }),
    ...extra,
  };
}

async function openBill(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "S1/26-27/00001" }));
  const panel = await screen.findByRole("complementary", { name: "S1/26-27/00001" });
  await user.click(await within(panel).findByRole("button", { name: "Return goods" }));
  return panel;
}

describe("Returns on a sales bill", () => {
  it("sends the quantities and reason, and says what was saved", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(COUNTER),
      ...routes({ "POST /credit-notes": () => ({ status: 201, body: NOTE }) }),
    });
    renderAt("/sales");
    const panel = await openBill(user);

    await user.click(within(panel).getByRole("button", { name: "Save credit note" }));
    expect(within(panel).getByText(/Enter how much comes back/)).toBeVisible();
    await user.type(within(panel).getByLabelText(/quantity back \(ton\)/), "0.5");
    await user.click(within(panel).getByRole("button", { name: "Save credit note" }));
    expect(within(panel).getByText(/Write the reason/)).toBeVisible();
    await user.type(within(panel).getByLabelText("Reason"), "Wrong size");
    await user.click(within(panel).getByRole("button", { name: "Save credit note" }));

    expect(await screen.findByText(/Credit note S1C\/26-27\/00001 for ₹33,040.00/)).toBeVisible();
    expect(calls.find((c) => c.method === "POST" && c.path === "/credit-notes")?.body).toEqual({
      invoice_id: 7,
      reason: "Wrong size",
      lines: [{ line_id: 31, quantity: "0.5" }],
      approval_ids: [],
    });
  });

  it("asks the owner for a PIN when the return window has closed, then sends the approval", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    const { calls } = mockApi({
      ...session(COUNTER),
      ...routes({
        "POST /credit-notes": () => {
          attempts += 1;
          return attempts === 1
            ? {
                status: 409,
                body: {
                  code: "RETURN_WINDOW_CLOSED",
                  message:
                    "This bill is older than 2 days. A return now needs the owner's approval.",
                  field: null,
                  requires_owner_approval: true,
                },
              }
            : { status: 201, body: NOTE };
        },
        "POST /approvals": () => ({
          status: 201,
          body: {
            id: 55,
            action: "late_return",
            expires_at: "2026-10-09T10:00:00Z",
            approved_by_name: "Owner",
          },
        }),
      }),
    });
    renderAt("/sales");
    const panel = await openBill(user);
    await user.type(within(panel).getByLabelText(/quantity back/), "1");
    await user.type(within(panel).getByLabelText("Reason"), "Damaged");
    await user.click(within(panel).getByRole("button", { name: "Save credit note" }));

    expect(
      await within(panel).findByText(/Owner approval needed to take this return/),
    ).toBeVisible();
    await user.type(within(panel).getByLabelText("Owner PIN"), "4821");
    const reasons = within(panel).getAllByLabelText("Reason");
    await user.type(reasons[reasons.length - 1] as HTMLElement, "owner agreed");
    await user.click(within(panel).getByRole("button", { name: "Approve with PIN" }));

    expect(await screen.findByText(/Credit note S1C\/26-27\/00001/)).toBeVisible();
    const sent = calls.filter((c) => c.method === "POST" && c.path === "/credit-notes");
    expect(sent).toHaveLength(2);
    expect(sent[1]?.body).toMatchObject({ approval_ids: [55] });
    expect(calls.find((c) => c.path === "/approvals")?.body).toMatchObject({
      action: "late_return",
      party_id: 21,
    });
  });

  it("shows the server's message when more is returned than was sold", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(OWNER),
      ...routes({
        "POST /credit-notes": () => ({
          status: 422,
          body: {
            code: "RETURN_TOO_MUCH",
            message: "only 1000 can still be returned",
            field: "lines[0].quantity",
          },
        }),
      }),
    });
    renderAt("/sales");
    const panel = await openBill(user);
    await user.type(within(panel).getByLabelText(/quantity back/), "3");
    await user.type(within(panel).getByLabelText("Reason"), "Mistake");
    await user.click(within(panel).getByRole("button", { name: "Save credit note" }));
    expect(
      (await within(panel).findAllByText("only 1000 can still be returned")).length,
    ).toBeGreaterThan(0);
  });
});
