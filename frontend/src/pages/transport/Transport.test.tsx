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

const ACCOUNTANT = { ...OWNER, id: 3, username: "accounts", role: "accountant" as const };
const VEHICLE = {
  id: 5,
  number: "TN09AB1234",
  owner_name: "Murugan Transport",
  phone: null,
  is_own: false,
  party_id: 60,
  is_active: true,
};
const TRIP = {
  id: 9,
  trip_date: "2026-10-09",
  vehicle_id: 5,
  vehicle_number: "TN09AB1234",
  owner_name: "Murugan Transport",
  location_id: 1,
  invoice_id: 7,
  invoice_number: "S1/26-27/00001",
  purchase_id: null,
  purchase_number: null,
  from_place: "Hosur mill",
  to_place: "Chennai site",
  freight_amount: "3000.00",
  paid_amount: "1000.00",
  pay_ref: "TRIP-9",
  note: null,
};

describe("Transport", () => {
  it("lets the owner add a vehicle and a trip, and tells them where freight is owed", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /vehicles": () => ({ body: [VEHICLE] }),
      "GET /trips": () => ({ body: page([TRIP]) }),
      "GET /invoices": () => ({
        body: page([{ id: 7, number: "S1/26-27/00001", party_name: "Ravi Builders" }]),
      }),
      "GET /locations": () => ({ body: [S1] }),
      "POST /trips": () => ({ status: 201, body: TRIP }),
      "POST /vehicles": () => ({ status: 201, body: { ...VEHICLE, number: "TN01XY0001" } }),
    });
    renderAt("/transport");

    expect(await screen.findByText("Hosur mill to Chennai site")).toBeVisible();
    expect(screen.getByText("TRIP-9")).toBeVisible();
    const form = screen.getByRole("form", { name: "Add trip" });
    await user.click(within(form).getByRole("button", { name: "Save trip" }));
    expect(within(form).getByText("Pick the vehicle.")).toBeVisible();
    await user.selectOptions(within(form).getByLabelText("Vehicle"), "5");
    await user.selectOptions(within(form).getByLabelText("For sales bill"), "7");
    await user.type(within(form).getByLabelText("From"), "Hosur mill");
    await user.type(within(form).getByLabelText("To"), "Chennai site");
    await user.type(within(form).getByLabelText("Freight (₹)"), "3000");
    await user.click(within(form).getByRole("button", { name: "Save trip" }));
    expect(
      await screen.findByText(/Freight ₹3,000.00 is owed to Murugan Transport \(TRIP-9\)/),
    ).toBeVisible();
    expect(calls.find((c) => c.method === "POST" && c.path === "/trips")?.body).toMatchObject({
      vehicle_id: 5,
      invoice_id: 7,
      freight_amount: "3000",
    });

    await user.click(screen.getByRole("link", { name: "Vehicles" }));
    const add = await screen.findByRole("form", { name: "Add vehicle" });
    await user.type(within(add).getByLabelText("Vehicle number"), "TN01XY0001");
    await user.type(within(add).getByLabelText("Owner name"), "Ramu");
    await user.click(within(add).getByRole("button", { name: "Add vehicle" }));
    expect(await screen.findByText("Vehicle TN01XY0001 added.")).toBeVisible();
  });

  it("shows the accountant trips without any way to change them", async () => {
    mockApi({
      ...session(ACCOUNTANT),
      "GET /vehicles": () => ({ body: [VEHICLE] }),
      "GET /trips": () => ({ body: page([TRIP]) }),
      "GET /invoices": () => ({ body: page([]) }),
      "GET /locations": () => ({ body: [S1] }),
    });
    renderAt("/transport");
    expect(await screen.findByText("Hosur mill to Chennai site")).toBeVisible();
    expect(screen.queryByRole("form", { name: "Add trip" })).toBeNull();
  });

  it("is not available to counter staff", async () => {
    mockApi({ ...session(COUNTER) });
    renderAt("/transport");
    expect(await screen.findByText("Not available for your role")).toBeVisible();
  });

  it("flags direct sales that are not linked, with profit for linked ones", async () => {
    mockApi({
      ...session(OWNER),
      "GET /reports/drop-ship": () => ({
        body: {
          unlinked: 1,
          profit_total: "5000.00",
          rows: [
            {
              invoice_id: 7,
              invoice_number: "S1/26-27/00001",
              invoice_date: "2026-10-09",
              customer: "Ravi Builders",
              sales_line_id: 1,
              item_name: "TMT bar 12 mm Fe500D",
              base_qty: "2000.000",
              base_unit: "kg",
              taxable: "112000.00",
              purchase_number: "S1P/26-27/00004",
              supplier_name: "Steel Mills",
              goods_cost: "104000.00",
              freight: "3000.00",
              profit: "5000.00",
            },
            {
              invoice_id: 8,
              invoice_number: "S1/26-27/00002",
              invoice_date: "2026-10-09",
              customer: "Ravi Builders",
              sales_line_id: 2,
              item_name: "TMT bar 12 mm Fe500D",
              base_qty: "1000.000",
              base_unit: "kg",
              taxable: "56000.00",
              purchase_number: null,
              supplier_name: null,
              goods_cost: null,
              freight: "0.00",
              profit: null,
            },
          ],
        },
      }),
    });
    renderAt("/transport/direct");
    expect(await screen.findByText(/1 direct sale not linked/)).toBeVisible();
    expect(screen.getByText("Not linked")).toBeVisible();
    expect(screen.getByText(/Profit on linked direct sales: ₹5,000.00/)).toBeVisible();
  });
});

describe("Direct line on a bill", () => {
  it("offers the open supplier purchases and sends the chosen one", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /items": () => ({ body: page([TMT_ITEM]) }),
      "GET /parties": () => ({ body: page([PARTY]) }),
      "GET /locations": () => ({ body: [S1] }),
      "GET /drop-ship/open-purchases": () => ({
        body: [
          {
            purchase_line_id: 44,
            purchase_number: "S1P/26-27/00004",
            supplier_name: "Steel Mills",
            bill_no: "DS-1",
            bill_date: "2026-10-08",
            item_id: 10,
            item_name: "TMT bar 12 mm Fe500D",
            free_qty: "5000.000",
            base_unit: "kg",
          },
        ],
      }),
      "POST /invoices/preview": () => ({
        body: {
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
          lines: [],
        },
      }),
    });
    renderAt("/sales/new");
    await screen.findByRole("option", { name: "TMT bar 12 mm Fe500D" });
    await user.selectOptions(screen.getByLabelText("Customer"), String(PARTY.id));
    await user.selectOptions(screen.getByLabelText("Item 1"), "10");
    await user.type(screen.getByLabelText("Quantity"), "1");
    await user.selectOptions(screen.getByLabelText("Taken from"), "direct");
    await user.selectOptions(await screen.findByLabelText("Supplier purchase"), "44");
    await vi.waitFor(
      () => {
        const last = calls.filter((c) => c.path === "/invoices/preview").at(-1)?.body as {
          lines: { source: string; purchase_line_id: number | null }[];
        };
        expect(last?.lines[0]).toMatchObject({ source: "direct", purchase_line_id: 44 });
      },
      { timeout: 3000 },
    );
  });
});
