import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, S1, session } from "@/test/mockApi";
import type { User } from "@/api/types";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const ACCOUNTANT: User = { ...OWNER, id: 3, username: "accounts", role: "accountant" };

const PREVIEW = {
  date_from: "2026-10-01",
  date_to: "2026-10-31",
  company: "Demo Construction Materials",
  voucher_count: 13,
  kinds: [
    { kind: "Sales", count: 2, total: "70950.00" },
    { kind: "Receipt", count: 3, total: "34870.00" },
  ],
  checks: [
    {
      code: "receivable",
      label: "Customers owe (change in the dues report)",
      vouchers: "3040.00",
      report: "3040.00",
      ok: true,
    },
    {
      code: "gstr1_taxable",
      label: "Sales, taxable value (GSTR-1)",
      vouchers: "31804.50",
      report: "31804.50",
      ok: true,
    },
  ],
  gst_checked: true,
  note: null,
};

const LEDGERS = {
  company: "Demo Construction Materials",
  default_company: "Demo Construction Materials",
  ledgers: [
    {
      purpose: "sales",
      label: "Sales (taxable value of bills, less credit notes)",
      name: "Sales",
      default: "Sales",
      group: "Sales Accounts",
      is_custom: false,
    },
    {
      purpose: "cash",
      label: "Cash in the drawer",
      name: "Cash",
      default: "Cash",
      group: "Cash-in-Hand",
      is_custom: false,
    },
  ],
};

function routes(user: User, preview = PREVIEW) {
  return {
    ...session(user),
    "GET /locations": () => ({ body: [S1] }),
    "GET /reports/today": () => ({ body: { as_of: "2026-10-10" } }),
    "GET /tally/preview": () => ({ body: preview }),
    "GET /tally/ledgers": () => ({ body: LEDGERS }),
  };
}

describe("Tally export", () => {
  it("shows the accountant what the file holds and that it agrees with the books", async () => {
    const { calls } = mockApi(routes(ACCOUNTANT));
    renderAt("/reports/tally");
    const kinds = await screen.findByRole("table", { name: "Vouchers in the file" });
    expect(within(kinds).getByText("Sales")).toBeVisible();
    expect(within(kinds).getByText("₹70,950.00")).toBeVisible();
    const checks = screen.getByRole("table", { name: "Checks against the books" });
    expect(within(checks).getAllByText("Agrees")).toHaveLength(2);
    expect(screen.getByText(/13 vouchers for Demo Construction Materials/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Download Tally file" })).toBeEnabled();
    const asked = calls.find((c) => c.path === "/tally/preview");
    expect(asked).toBeDefined();
  });

  it("blocks the download while a check disagrees", async () => {
    mockApi(
      routes(OWNER, {
        ...PREVIEW,
        checks: PREVIEW.checks.map((c) => ({ ...c, report: "3041.00", ok: false })),
      }),
    );
    renderAt("/reports/tally");
    expect(await screen.findAllByText("Differs")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Download Tally file" })).toBeDisabled();
    expect(screen.getByText(/cannot be downloaded/)).toBeVisible();
  });

  it("saves the ledger names the accountant types", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...routes(OWNER),
      "PUT /tally/ledgers": () => ({ body: LEDGERS }),
    });
    renderAt("/reports/tally");
    const sales = await screen.findByLabelText("Sales (taxable value of bills, less credit notes)");
    await user.clear(sales);
    await user.type(sales, "Sales - Steel");
    await user.click(screen.getByRole("button", { name: "Save ledger names" }));
    expect(await screen.findByText("Saved.")).toBeVisible();
    const put = calls.find((c) => c.method === "PUT" && c.path === "/tally/ledgers");
    expect(put?.body).toEqual({
      company: null,
      names: { sales: "Sales - Steel", cash: "Cash" },
    });
  });

  it("is not offered to counter staff", async () => {
    mockApi({ ...session(COUNTER), "GET /locations": () => ({ body: [S1] }) });
    renderAt("/reports/tally");
    expect(await screen.findByRole("heading", { name: "Reports" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Tally export" })).toBeNull();
    expect(screen.queryByRole("table", { name: "Vouchers in the file" })).toBeNull();
  });
});
