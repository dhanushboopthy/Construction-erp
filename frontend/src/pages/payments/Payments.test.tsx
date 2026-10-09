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

const OPEN = {
  party_id: 20,
  account: "receivable",
  advance: "0.00",
  bills: [
    {
      bill_no: "S1/26-27/00001",
      bill_date: "2026-10-01",
      due_date: null,
      original: "4870.00",
      remaining: "4870.00",
      overdue: false,
    },
    {
      bill_no: "S1/26-27/00002",
      bill_date: "2026-10-05",
      due_date: null,
      original: "4870.00",
      remaining: "4870.00",
      overdue: false,
    },
  ],
};

describe("Payments", () => {
  it("records a receipt aimed at a chosen bill, with an idempotency key", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(COUNTER),
      "GET /payments": () => ({ body: [] }),
      "GET /parties": () => ({ body: page([PARTY]) }),
      "GET /locations": () => ({ body: [S1] }),
      "GET /parties/20/open-bills": () => ({ body: OPEN }),
      "POST /payments": () => ({
        status: 201,
        body: {
          id: 1,
          number: "S1R/26-27/00001",
          direction: "received",
          party_id: 20,
          party_name: "Ravi Builders",
          location_id: 1,
          amount: "4870.00",
          mode: "upi",
          reference: null,
          payment_date: "2026-10-09",
          note: null,
          site_id: null,
          applied: [{ bill_no: "S1/26-27/00002", amount: "4870.00" }],
          advance: "0.00",
        },
      }),
    });
    renderAt("/payments");
    await screen.findByRole("option", { name: "Ravi Builders" });
    await user.click(screen.getByRole("button", { name: "Record receipt" }));
    expect(await screen.findByText("Pick the customer.")).toBeVisible();

    await user.selectOptions(screen.getByLabelText("Customer"), "20");
    await user.type(screen.getByLabelText("Amount received (₹)"), "4870");
    await user.click(await screen.findByRole("checkbox", { name: /S1\/26-27\/00002/ }));
    expect(screen.getByLabelText("Pay on S1/26-27/00002 (₹)")).toHaveValue("4870.00");
    await user.click(screen.getByRole("button", { name: "Record receipt" }));

    expect(await screen.findByText(/Receipt S1R\/26-27\/00001 recorded/)).toBeVisible();
    expect(screen.getByText(/₹4,870.00 to S1\/26-27\/00002/)).toBeVisible();
    const sent = calls.find((c) => c.method === "POST" && c.path === "/payments");
    expect(sent?.headers["idempotency-key"]).toMatch(/[0-9a-f-]{36}/);
    expect(sent?.body).toMatchObject({
      direction: "received",
      party_id: 20,
      amount: "4870",
      mode: "upi",
      allocations: [{ bill_no: "S1/26-27/00002", amount: "4870.00" }],
    });
  });

  it("shows the server's words when the cash limit is reached", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(OWNER),
      "GET /payments": () => ({ body: [] }),
      "GET /parties": () => ({ body: page([PARTY]) }),
      "GET /locations": () => ({ body: [S1] }),
      "GET /parties/20/open-bills": () => ({ body: { ...OPEN, bills: [] } }),
      "POST /payments": () => ({
        status: 409,
        body: {
          code: "CASH_LIMIT_REACHED",
          message:
            "Cash of ₹2,00,000 or more from one customer in a day is not allowed. Take the rest by UPI or bank transfer.",
          field: "amount",
        },
      }),
    });
    renderAt("/payments");
    await screen.findByRole("option", { name: "Ravi Builders" });
    await user.selectOptions(screen.getByLabelText("Customer"), "20");
    await user.selectOptions(screen.getByLabelText("Taken at"), "1");
    await user.selectOptions(screen.getByLabelText("Paid by"), "cash");
    await user.type(screen.getByLabelText("Amount received (₹)"), "250000");
    await user.click(screen.getByRole("button", { name: "Record receipt" }));
    expect(await screen.findByText(/Take the rest by UPI or bank transfer/)).toBeVisible();
    expect(screen.getByText(/kept as an advance/)).toBeVisible();
  });

  it("lets the accountant read receipts but not record them", async () => {
    mockApi({
      ...session({ ...OWNER, role: "accountant", username: "accounts", id: 4 }),
      "GET /payments": () => ({ body: [] }),
    });
    renderAt("/payments");
    expect(await screen.findByText("No receipts yet.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Record receipt" })).toBeNull();
  });
});

describe("Approval PIN", () => {
  it("is saved only when both entries match", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({ ...session(OWNER), "POST /auth/pin": () => ({ status: 204 }) });
    renderAt("/settings/pin");
    await user.type(await screen.findByLabelText("New PIN"), "4821");
    await user.type(screen.getByLabelText("New PIN again"), "4822");
    await user.type(screen.getByLabelText("Your password"), "owner-pass-123");
    await user.click(screen.getByRole("button", { name: "Save PIN" }));
    expect(await screen.findByText("The two PINs are not the same.")).toBeVisible();
    await user.clear(screen.getByLabelText("New PIN again"));
    await user.type(screen.getByLabelText("New PIN again"), "4821");
    await user.click(screen.getByRole("button", { name: "Save PIN" }));
    expect(await screen.findByText("PIN saved.")).toBeVisible();
    expect(calls.find((c) => c.path === "/auth/pin")?.body).toEqual({
      current_password: "owner-pass-123",
      pin: "4821",
    });
  });
});

describe("Owner approval at the counter", () => {
  it("asks for the PIN when a bill needs the owner and then lets it through", async () => {
    const user = userEvent.setup();
    const blocked = {
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
      invoice_problems: [
        "This customer is not approved for credit. Take payment, or ask the owner.",
      ],
      needs_owner: true,
      approvals_needed: ["credit_override"],
      can_save: false,
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
    const { calls } = mockApi({
      ...session(COUNTER),
      "GET /items": () => ({ body: page([TMT_ITEM]) }),
      "GET /parties": () => ({
        body: page([{ ...PARTY, id: 21, name: "Walk-in customer", gstin: null, sites: [] }]),
      }),
      "GET /locations": () => ({ body: [S1] }),
      "POST /invoices/preview": (body) => {
        const approved = ((body as { approval_ids: number[] }).approval_ids ?? []).length > 0;
        return {
          body: approved
            ? {
                ...blocked,
                invoice_problems: [],
                needs_owner: false,
                approvals_needed: [],
                can_save: true,
              }
            : blocked,
        };
      },
      "POST /approvals": () => ({
        status: 201,
        body: {
          id: 5,
          action: "credit_override",
          expires_at: "2026-10-09T12:00:00Z",
          approved_by_name: "Shop Owner",
        },
      }),
    });
    renderAt("/sales/new");
    await screen.findByRole("option", { name: "TMT bar 12 mm Fe500D" });
    await user.selectOptions(screen.getByLabelText("Item 1"), "10");
    await user.type(screen.getByLabelText("Quantity"), "1");

    const prompt = await screen.findByRole(
      "group",
      { name: /Owner approval needed to sell on credit/ },
      { timeout: 3000 },
    );
    expect(screen.getByRole("button", { name: "Save bill" })).toBeDisabled();
    await user.click(within(prompt).getByRole("button", { name: "Approve with PIN" }));
    expect(within(prompt).getByText("The PIN is 4 to 12 digits.")).toBeVisible();
    await user.type(within(prompt).getByLabelText("Owner PIN"), "4821");
    await user.type(within(prompt).getByLabelText("Reason"), "pays on Friday");
    await user.click(within(prompt).getByRole("button", { name: "Approve with PIN" }));

    await vi.waitFor(
      () => expect(screen.getByRole("button", { name: "Save bill" })).toBeEnabled(),
      { timeout: 3000 },
    );
    expect(calls.find((c) => c.path === "/approvals")?.body).toEqual({
      pin: "4821",
      action: "credit_override",
      reason: "pays on Friday",
      party_id: 21,
    });
    const last = calls.filter((c) => c.path === "/invoices/preview").at(-1)?.body as {
      approval_ids: number[];
    };
    expect(last.approval_ids).toEqual([5]);
  });
});
