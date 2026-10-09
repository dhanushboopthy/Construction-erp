import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import {
  COMPONENTS,
  COUNTER,
  G1,
  mockApi,
  OWNER,
  PREVIEW,
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

const STAFF_PURCHASE = {
  id: 1,
  number: "S1P/26-27/00001",
  supplier_id: 40,
  supplier_name: "Steel Mills",
  location_id: 1,
  location_code: "S1",
  bill_no: "B-1",
  bill_date: "2026-10-08",
  due_date: null,
  mode: "stock",
  status: "posted",
  note: null,
  lines: [
    {
      id: 1,
      line_no: 1,
      item_id: 10,
      item_name: "TMT bar 12 mm Fe500D",
      unit: "ton",
      quantity: "10.000",
      received_quantity: "10.000",
      billed_qty: "10000.000",
      received_qty: "10000.000",
      base_unit: "kg",
    },
  ],
};

describe("Purchases", () => {
  it("shows counter staff the bill without any money or cost", async () => {
    const user = userEvent.setup();
    mockApi({ ...session(COUNTER), "GET /purchases": () => ({ body: page([STAFF_PURCHASE]) }) });
    renderAt("/purchases");
    await user.click(await screen.findByRole("button", { name: "S1P/26-27/00001" }));
    const detail = await screen.findByRole("complementary", { name: "S1P/26-27/00001" });
    expect(within(detail).getByText("10000 kg")).toBeVisible();
    expect(screen.queryByText(/We owe/)).toBeNull();
    expect(screen.queryByText(/Landed cost/)).toBeNull();
  });

  it("shows the owner the landed cost while keying, then saves the bill", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /items": () => ({ body: page([TMT_ITEM]) }),
      "GET /parties": () => ({ body: page([SUPPLIER]) }),
      "GET /locations": () => ({ body: [S1, G1] }),
      "GET /cost-components": () => ({ body: COMPONENTS }),
      "POST /purchases/preview": () => ({ body: PREVIEW }),
      "POST /purchases": () => ({
        status: 201,
        body: { ...STAFF_PURCHASE, supplier_payable: "649000.00" },
      }),
      "GET /purchases": () => ({ body: page([]) }),
    });
    renderAt("/purchases/new");

    await user.click(await screen.findByRole("button", { name: "Save purchase" }));
    expect(screen.getByText("Pick the supplier.")).toBeVisible();
    expect(screen.getByText("Pick an item.")).toBeVisible();
    expect(calls.some((c) => c.path === "/purchases" && c.method === "POST")).toBe(false);

    await user.selectOptions(screen.getByLabelText("Supplier"), "40");
    await user.selectOptions(screen.getByLabelText("Goods arrive at"), "1");
    await user.type(screen.getByLabelText("Supplier's bill no."), "B-1");
    await user.selectOptions(screen.getByLabelText("Item 1"), "10");
    expect(screen.getByLabelText("Unit")).toHaveValue("ton");
    await user.type(screen.getByLabelText("Billed qty"), "10");
    await user.type(screen.getByLabelText(/Rate per ton/), "55000");
    await user.click(screen.getByRole("button", { name: "Add charge to line 1" }));
    await user.selectOptions(screen.getByLabelText("Charge 1"), "1");
    expect(screen.getByLabelText("Amount (₹)")).toHaveValue("250");

    // The server computes landed cost; the screen only shows it.
    expect(await screen.findByText("₹55.665", {}, { timeout: 3000 })).toBeVisible();
    expect(screen.getByText("₹6,49,000.00")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Save purchase" }));
    expect(await screen.findByText("Saved as S1P/26-27/00001.")).toBeVisible();
    const sent = calls.find((c) => c.method === "POST" && c.path === "/purchases")?.body as {
      lines: { rate: string; quantity: string; unit: string; charges: unknown[] }[];
    };
    expect(sent.lines[0]).toMatchObject({
      unit: "ton",
      quantity: "10",
      rate: "55000",
      charges: [{ component_id: 1, amount: "250", on_supplier_bill: false }],
    });
  });

  it("adds the next line when Enter is pressed in the rate box", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(COUNTER),
      "GET /items": () => ({ body: page([TMT_ITEM]) }),
      "GET /parties": () => ({ body: page([SUPPLIER]) }),
      "GET /locations": () => ({ body: [S1] }),
      "GET /cost-components": () => ({ body: COMPONENTS }),
    });
    renderAt("/purchases/new");
    await user.type(await screen.findByLabelText(/Rate per/), "55000{Enter}");
    expect(screen.getByLabelText("Item 2")).toBeVisible();
    // Counter staff key the bill but get no landed-cost panel.
    expect(screen.queryByText("Landed cost")).toBeNull();
  });
});

describe("Returns to the supplier", () => {
  const OWNER_PURCHASE = {
    ...STAFF_PURCHASE,
    goods_value: "550000.00",
    gst_amount: "99000.00",
    charges_total: "0.00",
    supplier_payable: "649000.00",
    lines: [
      {
        ...STAFF_PURCHASE.lines[0],
        rate: "55000.0000",
        gst_rate: "18.00",
        goods_value: "550000.00",
        gst_amount: "99000.00",
        charges_total: "0.00",
        total_cost: "550000.00",
        unit_cost: "55.0000",
        costs: [],
      },
    ],
  };

  it("lets only the owner send goods back, with a debit note", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /purchases": () => ({ body: page([OWNER_PURCHASE]) }),
      "GET /debit-notes": () => ({ body: page([]) }),
      "POST /debit-notes": () => ({
        status: 201,
        body: { id: 2, number: "S1D/26-27/00001", grand_total: "129800.00", lines: [] },
      }),
    });
    renderAt("/purchases");
    await user.click(await screen.findByRole("button", { name: "S1P/26-27/00001" }));
    const panel = await screen.findByRole("complementary", { name: "S1P/26-27/00001" });
    await user.click(within(panel).getByRole("button", { name: "Return to supplier" }));
    await user.type(within(panel).getByLabelText(/quantity back \(ton\)/), "2");
    await user.type(within(panel).getByLabelText("Reason"), "Rusted bars");
    await user.click(within(panel).getByRole("button", { name: "Save debit note" }));
    expect(await screen.findByText(/Debit note S1D\/26-27\/00001 for ₹1,29,800.00/)).toBeVisible();
    expect(calls.find((c) => c.method === "POST" && c.path === "/debit-notes")?.body).toEqual({
      purchase_id: 1,
      reason: "Rusted bars",
      lines: [{ line_id: 1, quantity: "2" }],
    });
  });

  it("does not offer returns to counter staff", async () => {
    const user = userEvent.setup();
    mockApi({ ...session(COUNTER), "GET /purchases": () => ({ body: page([STAFF_PURCHASE]) }) });
    renderAt("/purchases");
    await user.click(await screen.findByRole("button", { name: "S1P/26-27/00001" }));
    const panel = await screen.findByRole("complementary", { name: "S1P/26-27/00001" });
    expect(within(panel).queryByRole("button", { name: "Return to supplier" })).toBeNull();
  });
});
