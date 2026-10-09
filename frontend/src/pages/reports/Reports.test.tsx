import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, S1, session } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const ACCOUNTANT = { ...OWNER, id: 3, username: "accounts", role: "accountant" as const };

const FIGURES = {
  location_id: 1,
  location_code: "S1",
  closing_date: "2026-10-09",
  invoices_count: 2,
  first_invoice: "S1/26-27/00001",
  last_invoice: "S1/26-27/00002",
  taxable: "3000.00",
  cgst: "270.00",
  sgst: "270.00",
  igst: "0.00",
  round_off: "0.00",
  sales_total: "3540.00",
  credit_given: "2340.00",
  returns_count: 0,
  returns_total: "0.00",
  receipts: { cash: "1000.00", upi: "200.00", bank: "0.00", total: "1200.00" },
  cash_out: "300.00",
  purchases_count: 0,
  top_items: [
    { description: "Cement PPC", base_unit: "bag", quantity: "8.000", taxable: "3000.00" },
  ],
};

const PREVIEW = {
  figures: FIGURES,
  opening_cash: "500.00",
  expected_cash: "1200.00",
  existing: null,
  locked: false,
  profit: null,
};

const CLOSED = {
  id: 4,
  location_id: 1,
  location_code: "S1",
  closing_date: "2026-10-09",
  status: "closed",
  invoices_count: 2,
  sales_total: "3540.00",
  returns_total: "0.00",
  opening_cash: "500.00",
  cash_in: "1000.00",
  cash_out: "300.00",
  expected_cash: "1200.00",
  counted_cash: "1150.00",
  difference: "-50.00",
  note: "change",
  closed_at: "2026-10-09T12:00:00Z",
  reopened_at: null,
  reopen_reason: null,
  times_closed: 1,
  has_pdf: true,
};

const base = {
  "GET /reports/today": () => ({
    body: {
      as_of: "2026-10-09",
      items_in_stock: 0,
      customers_owe: "0.00",
      we_owe: null,
      sales_today: "0.00",
      returns_today: "0.00",
      profit_today: null,
    },
  }),
  "GET /locations": () => ({ body: [S1] }),
  "GET /closings/preview": () => ({ body: PREVIEW }),
  "GET /closings": () => ({ body: { items: [], total: 0, limit: 30, offset: 0 } }),
};

describe("Daily closing", () => {
  it("shows the day's figures and what should be in the drawer, and closes the day", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(COUNTER),
      ...base,
      "POST /closings": () => ({ status: 201, body: CLOSED }),
    });
    renderAt("/reports");
    expect(
      await screen.findByText("S1/26-27/00001 to S1/26-27/00002", { exact: false }),
    ).toBeVisible();
    const drawer = screen.getByRole("complementary", { name: "Cash drawer" });
    expect(within(drawer).getByText("₹1,200.00")).toBeVisible();
    expect(screen.queryByText(/Profit/)).toBeNull();
    expect(screen.queryByRole("link", { name: "Profit" })).toBeNull();

    await user.click(within(drawer).getByRole("button", { name: "Close the day" }));
    expect(within(drawer).getByText("Enter the cash you counted.")).toBeVisible();
    await user.type(within(drawer).getByLabelText("Cash counted"), "1150");
    await user.type(within(drawer).getByLabelText(/Note/), "change");
    await user.click(within(drawer).getByRole("button", { name: "Close the day" }));

    expect(
      await within(drawer).findByText(/Day closed. The drawer is short by ₹50.00/),
    ).toBeVisible();
    expect(calls.find((c) => c.method === "POST" && c.path === "/closings")?.body).toEqual({
      location_id: 1,
      closing_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/) as string,
      counted_cash: "1150",
      opening_cash: null,
      note: "change",
    });
  });

  it("shows the server's rule when a note is missing", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(COUNTER),
      ...base,
      "POST /closings": () => ({
        status: 409,
        body: {
          code: "CASH_NOTE_REQUIRED",
          message: "The drawer is short by ₹50.00. Write a note before closing the day.",
          field: "note",
        },
      }),
    });
    renderAt("/reports");
    const drawer = await screen.findByRole("complementary", { name: "Cash drawer" });
    await user.type(within(drawer).getByLabelText("Cash counted"), "1150");
    await user.click(within(drawer).getByRole("button", { name: "Close the day" }));
    expect(await within(drawer).findByRole("alert")).toHaveTextContent(/Write a note/);
  });

  it("locks a closed day and lets only the owner reopen it", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      ...base,
      "GET /closings/preview": () => ({
        body: { ...PREVIEW, locked: true, existing: CLOSED, profit: "420.00" },
      }),
      "GET /closings": () => ({ body: { items: [CLOSED], total: 1, limit: 30, offset: 0 } }),
      "POST /closings/4/reopen": () => ({ body: { ...CLOSED, status: "reopened" } }),
    });
    vi.stubGlobal("prompt", () => "forgot a bill");
    renderAt("/reports");
    expect(await screen.findByText(/This day is closed. Counted ₹1,150.00/)).toBeVisible();
    expect(screen.getByText("Profit (not on the PDF)")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Close the day" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Reopen 2026-10-09" }));
    await vi.waitFor(() =>
      expect(calls.find((c) => c.path === "/closings/4/reopen")?.body).toEqual({
        reason: "forgot a bill",
      }),
    );
  });

  it("lets the accountant look but not close", async () => {
    mockApi({ ...session(ACCOUNTANT), ...base });
    renderAt("/reports");
    expect(await screen.findByText(/The accountant can look at a closing/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Dues" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Profit" })).toBeNull();
  });
});

describe("Profit, dues and segments", () => {
  it("shows profit by item to the owner", async () => {
    mockApi({
      ...session(OWNER),
      "GET /reports/profit": () => ({
        body: {
          group: "item",
          date_from: "2026-09-09",
          date_to: "2026-10-09",
          taxable: "33600.00",
          cost: "33000.00",
          freight: "300.00",
          profit: "300.00",
          rows: [
            {
              key: "TMT 12 mm",
              taxable: "33600.00",
              cost: "33000.00",
              freight: "300.00",
              profit: "300.00",
              margin_pct: "0.89",
            },
          ],
        },
      }),
    });
    renderAt("/reports/profit");
    expect(await screen.findByText("TMT 12 mm")).toBeVisible();
    expect(screen.getByText("0.89%")).toBeVisible();
  });

  it("keeps profit away from the accountant", async () => {
    mockApi({ ...session(ACCOUNTANT) });
    renderAt("/reports/profit");
    expect(await screen.findByText("Not available for your role")).toBeVisible();
  });

  it("draws the segment chart with a text table beside it, empty at first", async () => {
    mockApi({
      ...session(OWNER),
      "GET /reports/sales-by-segment": () => ({
        body: {
          financial_year: "26-27",
          start_year: 2026,
          total: "0.00",
          months: Array.from({ length: 12 }, (_, i) => ({
            month: `${i < 9 ? 2026 : 2027}-${String(((i + 3) % 12) + 1).padStart(2, "0")}`,
            retail: "0.00",
            contractor: "0.00",
            bulk: "0.00",
            unassigned: "0.00",
            total: "0.00",
          })),
        },
      }),
    });
    renderAt("/reports/segments");
    expect(await screen.findByText(/No sales in this year yet/)).toBeVisible();
    expect(
      screen.getByRole("img", { name: /Sales by customer segment, financial year 26-27/ }),
    ).toBeVisible();
    expect(screen.getByRole("table", { name: /Sales by segment/ })).toBeVisible();
  });

  it("lists dues with ageing", async () => {
    mockApi({
      ...session(OWNER),
      "GET /reports/dues": () => ({
        body: {
          account: "receivable",
          as_of: "2026-10-09",
          total: "5000.00",
          rows: [
            {
              party_id: 1,
              party_name: "Ravi Builders",
              balance: "5000.00",
              advance: "0.00",
              aging: { up_to_30: "3000.00", days_31_60: "2000.00", over_60: "0.00" },
              oldest_date: "2026-08-20",
            },
          ],
        },
      }),
    });
    renderAt("/reports/dues");
    expect(await screen.findByText("Ravi Builders")).toBeVisible();
    expect(screen.getByText("2026-08-20")).toBeVisible();
  });
});

describe("Today", () => {
  it("shows the figures by role", async () => {
    mockApi({
      ...session(COUNTER),
      "GET /reports/today": () => ({
        body: {
          as_of: "2026-10-09",
          items_in_stock: 4,
          customers_owe: "2409.00",
          we_owe: null,
          sales_today: "3409.00",
          returns_today: "0.00",
          profit_today: null,
        },
      }),
      "GET /stock": () => ({ body: [] }),
      "GET /locations": () => ({ body: [S1] }),
    });
    renderAt("/");
    expect(await screen.findByText("₹3,409.00".replace("₹", ""))).toBeVisible();
    expect(screen.getByText("Items in stock")).toBeVisible();
    expect(screen.queryByText("We owe suppliers")).toBeNull();
    expect(screen.queryByText("Profit today")).toBeNull();
  });
});
