import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, page, session } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

const SUMMARY = {
  id: 7,
  number: "S1/26-27/00001",
  invoice_date: "2026-10-09",
  party_id: 21,
  party_name: "Ravi Builders",
  location_id: 1,
  location_code: "S1",
  supply_type: "B2B",
  grand_total: "168609.00",
  status: "posted",
};

const INVOICE = {
  ...SUMMARY,
  financial_year: "26-27",
  site_id: 3,
  bill_to_name: "Ravi Builders",
  bill_to_address: "Chennai",
  bill_to_gstin: "33AAPFU0939F1Z2",
  ship_to_name: "Chennai site",
  ship_to_address: "Anna Nagar",
  ship_to_gstin: null,
  place_of_supply: "33",
  supply_kind: "intra_state",
  due_date: "2026-10-09",
  taxable_value: "142663.15",
  cgst: "12972.84",
  sgst: "12972.84",
  igst: "0.00",
  round_off: "0.17",
  pending_balance_at_billing: "0.00",
  paid_at_billing: "0.00",
  vehicle_no: null,
  remark: null,
  lines: [],
};

const NEEDED = {
  invoice_id: 7,
  required: true,
  threshold: "100000.00",
  live: null,
  history: [],
};

const BILL = {
  id: 1,
  invoice_id: 7,
  invoice_number: "S1/26-27/00001",
  number: "391012345678",
  status: "generated",
  source: "gsp",
  vehicle_no: null,
  distance_km: 120,
  valid_until: "2026-10-10",
  generated_at: "2026-10-09T10:00:00Z",
  cancelled_at: null,
  cancel_reason: null,
  can_cancel: true,
};

const base = {
  "GET /invoices": () => ({ body: page([SUMMARY]) }),
  "GET /invoices/7": () => ({ body: INVOICE }),
  "GET /credit-notes": () => ({ body: page([]) }),
  "GET /eway-bills/pending": () => ({ body: [] }),
  "GET /invoices/7/einvoice": () => ({
    body: { invoice_id: 7, enabled: false, required: false, einvoice: null },
  }),
};

async function openBill(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "S1/26-27/00001" }));
  const panel = await screen.findByRole("complementary", { name: "S1/26-27/00001" });
  return within(await within(panel).findByRole("group", { name: /E-way bill/ }));
}

describe("E-way bill on a bill", () => {
  it("says it is needed, checks the pincodes, and makes the bill", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(COUNTER),
      ...base,
      "GET /invoices/7/eway-bill": () => ({ body: NEEDED }),
      "POST /invoices/7/eway-bill": () => ({ status: 201, body: BILL }),
    });
    renderAt("/sales");
    const eway = await openBill(user);
    expect(await eway.findByText(/Needed: this bill is above ₹1,00,000.00/)).toBeVisible();

    await user.click(eway.getByRole("button", { name: "Make e-way bill" }));
    expect(eway.getByText(/Enter the distance in km/)).toBeVisible();
    await user.type(eway.getByLabelText("Distance (km)"), "120");
    await user.type(eway.getByLabelText("From pincode"), "600001");
    await user.type(eway.getByLabelText("To pincode"), "6000");
    await user.click(eway.getByRole("button", { name: "Make e-way bill" }));
    expect(eway.getByText("Pincodes have six digits.")).toBeVisible();
    await user.type(eway.getByLabelText("To pincode"), "40");
    await user.type(eway.getByLabelText("Vehicle (optional)"), "TN09AB1234");
    await user.click(eway.getByRole("button", { name: "Make e-way bill" }));

    expect(await eway.findByText("E-way bill made.")).toBeVisible();
    expect(
      calls.find((c) => c.method === "POST" && c.path === "/invoices/7/eway-bill")?.body,
    ).toEqual({
      distance_km: 120,
      from_pincode: "600001",
      to_pincode: "600040",
      vehicle_no: "TN09AB1234",
    });
    expect(window.localStorage.getItem("erp.shopPincode")).toBe("600001");
  });

  it("shows the GSP's problem and lets the user try again", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(OWNER),
      ...base,
      "GET /invoices/7/eway-bill": () => ({ body: NEEDED }),
      "POST /invoices/7/eway-bill": () => ({
        status: 502,
        body: {
          code: "GSP_TIMEOUT",
          message: "The GSP did not answer in time Try again in a minute.",
          field: null,
        },
      }),
    });
    renderAt("/sales");
    const eway = await openBill(user);
    await user.type(await eway.findByLabelText("Distance (km)"), "50");
    await user.type(eway.getByLabelText("From pincode"), "600001");
    await user.type(eway.getByLabelText("To pincode"), "600040");
    await user.click(eway.getByRole("button", { name: "Make e-way bill" }));
    expect(await eway.findByRole("alert")).toHaveTextContent(/did not answer in time/);
    expect(eway.getByRole("button", { name: "Make e-way bill" })).toBeEnabled();
  });

  it("shows a live bill and only offers cancel to the owner", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(COUNTER),
      ...base,
      "GET /invoices/7/eway-bill": () => ({ body: { ...NEEDED, live: BILL, history: [BILL] } }),
    });
    renderAt("/sales");
    const eway = await openBill(user);
    expect(await eway.findByText("391012345678")).toBeVisible();
    expect(eway.getByRole("button", { name: "Update vehicle" })).toBeVisible();
    expect(eway.queryByRole("button", { name: "Cancel e-way bill" })).toBeNull();
  });

  it("offers the IRN when e-invoicing is on", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      ...base,
      "GET /invoices/7/eway-bill": () => ({ body: { ...NEEDED, live: BILL, history: [BILL] } }),
      "GET /invoices/7/einvoice": () => ({
        body: { invoice_id: 7, enabled: true, required: true, einvoice: null },
      }),
      "POST /invoices/7/einvoice": () => ({ status: 201, body: {} }),
    });
    renderAt("/sales");
    const eway = await openBill(user);
    await user.click(await eway.findByRole("button", { name: "Make IRN" }));
    expect(eway.getByText(/Fill both pincodes/)).toBeVisible();
    expect(calls.some((c) => c.path === "/invoices/7/einvoice" && c.method === "POST")).toBe(false);
  });
});
