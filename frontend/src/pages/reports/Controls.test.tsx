import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import type { User } from "@/api/types";
import { COUNTER, mockApi, OWNER, S1, SETTINGS, session } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const ACCOUNTANT: User = { ...OWNER, id: 3, username: "accounts", role: "accountant" };

const KPIS = [
  {
    code: "bank_unmatched_lines",
    name: "Bank lines with no entry",
    formula: "Count of statement lines with no entry",
    meaning: "Money the bank shows that your books do not.",
    example: "10 lines, 8 match: 2 left",
    sources: "bank_statement_line",
    owner_only: false,
    refresh: "live",
    good: "down",
    unit: "count",
  },
];

const RECONCILIATION = {
  date_from: "2026-09-10",
  date_to: "2026-10-10",
  window_days: 3,
  line_count: 2,
  matched_count: 1,
  unmatched_count: 1,
  unmatched_in: "18750.00",
  unmatched_out: "0.00",
  not_in_bank_total: "8000.00",
  last_balance: "497960.00",
  last_balance_date: "2026-10-10",
  lines: [
    {
      id: 1,
      line_date: "2026-10-09",
      narration: "UPI/RAVI/412345678901",
      reference: "412345678901",
      debit: "0.00",
      credit: "25000.00",
      matched: true,
      matched_key: "payment:1",
      matched_label: "Receipt S1R/26-27/00001, Ravi Builders",
      matched_how: "reference",
    },
    {
      id: 2,
      line_date: "2026-10-09",
      narration: "CHQ DEP UNKNOWN",
      reference: "",
      debit: "0.00",
      credit: "18750.00",
      matched: false,
      matched_key: null,
      matched_label: null,
      matched_how: null,
    },
  ],
  not_in_bank: [
    {
      key: "payment:8",
      entry_date: "2026-10-10",
      label: "Receipt S1R/26-27/00008, Ravi Builders",
      mode: "UPI",
      reference: "999999999999",
      amount: "8000.00",
      money_in: true,
    },
  ],
};

function bankRoutes(
  user: User,
  extra: Record<string, () => { status?: number; body?: unknown }> = {},
) {
  return {
    ...session(user),
    "GET /locations": () => ({ body: [S1] }),
    "GET /reports/today": () => ({ body: { as_of: "2026-10-10" } }),
    "GET /kpis/definitions": () => ({ body: KPIS }),
    "GET /bank/accounts": () => ({
      body: [{ id: 5, name: "SBI current", account_no_last4: null, is_active: true }],
    }),
    "GET /bank/statements": () => ({ body: [] }),
    "GET /bank/reconciliation": () => ({ body: RECONCILIATION }),
    ...extra,
  };
}

describe("Bank", () => {
  it("shows what matched and what did not, on both sides", async () => {
    mockApi(bankRoutes(ACCOUNTANT));
    renderAt("/reports/bank");
    const lines = await screen.findByRole("table", { name: "Bank lines" });
    expect(within(lines).getByText(/Receipt S1R\/26-27\/00001/)).toBeVisible();
    expect(within(lines).getByText("by reference")).toBeVisible();
    expect(within(lines).getByText("No entry in our books")).toBeVisible();
    const missing = screen.getByRole("table", { name: "Recorded but not in the bank" });
    expect(within(missing).getByText("999999999999")).toBeVisible();
    expect(screen.getAllByText("₹8,000.00").length).toBeGreaterThan(0);
    expect(screen.getByText("₹4,97,960.00")).toBeVisible();
    // The accountant uploads statements but does not add accounts.
    expect(screen.queryByLabelText("New bank account")).toBeNull();
  });

  it("uploads a statement for the chosen account", async () => {
    const user = userEvent.setup();
    const { fetchMock } = mockApi(
      bankRoutes(OWNER, {
        "POST /bank/statements": () => ({
          status: 201,
          body: { id: 1, row_count: 10, skipped_count: 2 },
        }),
      }),
    );
    renderAt("/reports/bank");
    await screen.findByRole("table", { name: "Bank lines" });
    await user.upload(
      screen.getByLabelText("Bank statement (CSV)"),
      new File(["Date,Debit,Credit"], "oct.csv", { type: "text/csv" }),
    );
    expect(await screen.findByText("oct.csv: 8 lines added, 2 already held.")).toBeVisible();
    const post = fetchMock.mock.calls.find(
      ([url, init]) => String(url).endsWith("/bank/statements") && init?.method === "POST",
    );
    const form = post?.[1]?.body as FormData;
    expect(form.get("bank_account_id")).toBe("5");
    expect(form.get("file")).toBeInstanceOf(File);
  });

  it("says why a file was refused", async () => {
    const user = userEvent.setup();
    mockApi(
      bankRoutes(OWNER, {
        "POST /bank/statements": () => ({
          status: 409,
          body: {
            code: "STATEMENT_UNREADABLE",
            message: "The file could not be read, so nothing was imported. Line 2: not a date.",
          },
        }),
      }),
    );
    renderAt("/reports/bank");
    await screen.findByRole("table", { name: "Bank lines" });
    await user.upload(
      screen.getByLabelText("Bank statement (CSV)"),
      new File(["x"], "bad.csv", { type: "text/csv" }),
    );
    expect(await screen.findByText(/nothing was imported\. Line 2/)).toBeVisible();
  });

  it("is not offered to counter staff", async () => {
    mockApi({ ...session(COUNTER), "GET /locations": () => ({ body: [S1] }) });
    renderAt("/reports/bank");
    expect(await screen.findByRole("heading", { name: "Reports" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Bank" })).toBeNull();
    expect(screen.queryByRole("table", { name: "Bank lines" })).toBeNull();
  });
});

describe("Exceptions", () => {
  const REPORT = {
    date_from: "2026-09-11",
    date_to: "2026-10-10",
    counts: [
      { code: "round_adjustment", title: "Round-number stock adjustment", count: 1 },
      { code: "repeat_returns", title: "Many returns from one customer", count: 0 },
    ],
    rows: [
      {
        code: "round_adjustment",
        title: "Round-number stock adjustment",
        on: "2026-10-09",
        location_code: "S1",
        user_name: "Counter, Shop 1",
        document: "S1A/26-27/00004",
        detail: "Worth exactly ₹1,000 (breakage).",
        value: "1000.00",
        link: "/stock/adjustments",
      },
    ],
  };

  it("lists flagged entries for the owner and links to the document", async () => {
    mockApi({
      ...session(OWNER),
      "GET /locations": () => ({ body: [S1] }),
      "GET /reports/today": () => ({ body: { as_of: "2026-10-10" } }),
      "GET /kpis/definitions": () => ({ body: [] }),
      "GET /reports/exceptions": () => ({ body: REPORT }),
    });
    renderAt("/reports/exceptions");
    const table = await screen.findByRole("table", { name: "Flagged entries" });
    expect(within(table).getByText("Worth exactly ₹1,000 (breakage).")).toBeVisible();
    expect(within(table).getByRole("link", { name: "S1A/26-27/00004" })).toHaveAttribute(
      "href",
      "/stock/adjustments",
    );
    const pills = screen.getByRole("list", { name: "Flags by kind" });
    expect(within(pills).getByText("Round-number stock adjustment: 1")).toBeVisible();
    expect(within(pills).queryByText(/Many returns/)).toBeNull(); // zero counts are hidden
  });

  it("is for the owner only", async () => {
    mockApi({ ...session(ACCOUNTANT), "GET /locations": () => ({ body: [S1] }) });
    renderAt("/reports/exceptions");
    expect(await screen.findByRole("heading", { name: "Reports" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Exceptions" })).toBeNull();
    expect(screen.queryByRole("table", { name: "Flagged entries" })).toBeNull();
  });
});

describe("Books lock", () => {
  function lockRoutes(
    locked: string | null,
    extra: Record<string, () => { status?: number; body?: unknown }> = {},
  ) {
    return {
      ...session(OWNER),
      "GET /locations": () => ({ body: [S1] }),
      "GET /settings": () => ({ body: SETTINGS }),
      "GET /reports/today": () => ({ body: { as_of: "2026-10-10" } }),
      "GET /period-lock": () => ({
        body: { locked_through: locked, changed_at: null, changed_by_name: null, reason: null },
      }),
      "GET /period-lock/checklist": () => ({
        body: {
          period: "2026-10",
          ready: false,
          items: [
            {
              code: "gstr2b",
              label: "GSTR-2B imported and matched",
              state: "warn",
              detail: "No GSTR-2B has been imported for this month.",
            },
          ],
        },
      }),
      ...extra,
    };
  }

  it("locks the books through a date with a reason", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi(
      lockRoutes(null, {
        "PUT /period-lock": () => ({
          body: {
            locked_through: "2026-09-30",
            changed_at: null,
            changed_by_name: null,
            reason: null,
          },
        }),
      }),
    );
    renderAt("/settings/lock");
    expect(await screen.findByText(/The books are not locked/)).toBeVisible();
    expect(await screen.findByText(/No GSTR-2B has been imported/)).toBeVisible();
    const lock = screen.getByRole("button", { name: "Lock books" });
    expect(lock).toBeDisabled();
    await user.type(screen.getByLabelText("Lock through"), "2026-09-30");
    await user.type(screen.getByLabelText("Reason"), "September GSTR-1 filed");
    await user.click(lock);
    const put = calls.find((c) => c.method === "PUT" && c.path === "/period-lock");
    expect(put?.body).toEqual({ locked_through: "2026-09-30", reason: "September GSTR-1 filed" });
  });

  it("reopens the books only with a reason", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi(
      lockRoutes("2026-09-30", {
        "PUT /period-lock": () => ({
          body: { locked_through: null, changed_at: null, changed_by_name: null, reason: null },
        }),
      }),
    );
    renderAt("/settings/lock");
    expect(await screen.findByText(/on or before 2026-09-30/)).toBeVisible();
    const reopen = screen.getByRole("button", { name: "Reopen all" });
    expect(reopen).toBeDisabled();
    await user.type(screen.getByLabelText("Reason"), "Late credit note");
    await user.click(reopen);
    const put = calls.find((c) => c.method === "PUT" && c.path === "/period-lock");
    expect(put?.body).toEqual({ locked_through: null, reason: "Late credit note" });
  });

  it("shows the refusal when the lock is later than today", async () => {
    const user = userEvent.setup();
    mockApi(
      lockRoutes(null, {
        "PUT /period-lock": () => ({
          status: 409,
          body: { code: "LOCK_IN_FUTURE", message: "The lock cannot be later than today" },
        }),
      }),
    );
    renderAt("/settings/lock");
    await screen.findByText(/The books are not locked/);
    await user.type(screen.getByLabelText("Lock through"), "2026-10-10");
    await user.type(screen.getByLabelText("Reason"), "Early lock");
    await user.click(screen.getByRole("button", { name: "Lock books" }));
    expect(await screen.findByText("The lock cannot be later than today")).toBeVisible();
  });

  it("saves the new exception settings with the form", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...lockRoutes(null),
      "PUT /settings": () => ({ body: SETTINGS }),
    });
    renderAt("/settings");
    const field = await screen.findByLabelText(/Returns from one customer/);
    await user.clear(field);
    await user.type(field, "5");
    await user.click(screen.getByRole("button", { name: "Save shop details" }));
    const put = calls.find((c) => c.method === "PUT" && c.path === "/settings");
    expect(put?.body).toMatchObject({
      exception_returns_count: 5,
      exception_round_amount: "1000.00",
      bank_match_days: 3,
    });
    expect(put?.body).not.toHaveProperty("locked_through");
  });
});

describe("Audit log", () => {
  it("shows who changed what and expands the changes", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /locations": () => ({ body: [S1] }),
      "GET /users": () => ({ body: [OWNER] }),
      "GET /audit-log": () => ({
        body: {
          total: 1,
          limit: 50,
          offset: 0,
          items: [
            {
              id: 9,
              at: "2026-10-10T08:30:00Z",
              user_id: 1,
              action: "override",
              entity: "period_lock",
              entity_id: "1",
              changes: { reason: "September GSTR-1 filed", from: null, to: "2026-09-30" },
              request_id: null,
              ip: null,
            },
          ],
        },
      }),
    });
    renderAt("/settings/audit");
    const table = await screen.findByRole("table", { name: "Audit log" });
    expect(within(table).getByText("Shop Owner")).toBeVisible();
    expect(within(table).getByText("period_lock #1")).toBeVisible();
    await user.click(within(table).getByRole("button", { name: "Show" }));
    expect(await screen.findByText(/September GSTR-1 filed/)).toBeVisible();
    await user.type(screen.getByLabelText("Record kind"), "payment");
    await vi.waitFor(() =>
      expect(calls.some((c) => c.path === "/audit-log" && c.method === "GET")).toBe(true),
    );
  });
});
