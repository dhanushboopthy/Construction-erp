import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, G1, mockApi, OWNER, S1, session } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const BOOK = {
  location_id: 1,
  date_from: "2026-10-09",
  date_to: "2026-10-09",
  entries: [],
  drawer_in: "0.00",
  drawer_out: "0.00",
  expenses: "0.00",
  months: [],
};

function routes(user: typeof OWNER, post?: (body: unknown) => { status?: number; body?: unknown }) {
  return {
    ...session(user),
    "GET /locations": () => ({ body: [S1, G1] }),
    "GET /reports/today": () => ({ body: { as_of: "2026-10-09" } }),
    "GET /cash-book": () => ({ body: BOOK }),
    "GET /expense-categories": () => ({
      body: [{ id: 4, name: "Loading and unloading labour", nature: "variable", is_active: true }],
    }),
    ...(post ? { "POST /cash-book": post } : {}),
  };
}

describe("Cash book", () => {
  it("shows a month, a financial year, a range or everything, with month totals", async () => {
    const user = userEvent.setup();
    const asked: string[] = [];
    mockApi({
      ...routes(OWNER),
      "GET /cash-book": (_, url) => {
        asked.push(url.search);
        return {
          body: {
            ...BOOK,
            date_from: "2026-04-01",
            date_to: "2026-10-09",
            expenses: "1000.00",
            months: [
              { month: "2026-09", drawer_in: "0.00", drawer_out: "700.00", expenses: "700.00" },
              { month: "2026-10", drawer_in: "0.00", drawer_out: "300.00", expenses: "300.00" },
            ],
          },
        };
      },
    });
    renderAt("/cash");
    const period = await screen.findByLabelText("Period");

    await user.selectOptions(period, "month");
    await vi.waitFor(() =>
      expect(asked.at(-1)).toContain("date_from=2026-10-01&date_to=2026-10-31"),
    );
    await user.selectOptions(period, "year");
    expect(screen.getByLabelText("Financial year")).toHaveDisplayValue("2026-27");
    await vi.waitFor(() =>
      expect(asked.at(-1)).toContain("date_from=2026-04-01&date_to=2027-03-31"),
    );
    await user.selectOptions(period, "range");
    await user.type(screen.getByLabelText("From"), "2026-10-05");
    await user.type(screen.getByLabelText("To"), "2026-10-08");
    await vi.waitFor(() =>
      expect(asked.at(-1)).toContain("date_from=2026-10-05&date_to=2026-10-08"),
    );
    await user.selectOptions(period, "all");
    await vi.waitFor(() => expect(asked.at(-1)).toContain("all_time=true"));

    const months = await screen.findByRole("table", { name: "Month by month" });
    expect(within(months).getByText("2026-09")).toBeVisible();
    expect(within(months).getByText("₹700.00", { selector: "td:last-child" })).toBeVisible();
    expect(screen.getByText(/2026-04-01 to 2026-10-09/)).toBeVisible();
  });

  it("offers counter staff only expenses and bank deposits, with one shop and no shop picker", async () => {
    mockApi(routes(COUNTER));
    renderAt("/cash");
    const kind = await screen.findByLabelText("What happened");
    const options = within(kind)
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(options).toEqual(["Expense", "Cash taken to the bank"]);
    expect(screen.queryByLabelText("Shop")).toBeNull(); // one shop: nothing to pick
    expect(await screen.findByText(/No vouchers on this day/)).toBeVisible();
  });

  it("asks for the owner's PIN when an expense is above the limit", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi(
      routes(COUNTER, () => ({
        status: 409,
        body: {
          code: "EXPENSE_NEEDS_OWNER",
          message: "Vouchers above ₹5,000 need the owner's approval.",
          field: null,
          requires_owner_approval: true,
        },
      })),
    );
    renderAt("/cash");
    await screen.findByRole("option", { name: "Loading and unloading labour" });
    await user.selectOptions(screen.getByLabelText("Expense head"), "4");
    await user.type(screen.getByLabelText("Amount (₹)"), "6000");
    await user.click(screen.getByRole("button", { name: "Save voucher" }));
    expect(await screen.findByText(/Owner approval needed to pay this expense/)).toBeVisible();
    const sent = calls.find((c) => c.method === "POST" && c.path === "/cash-book");
    expect(sent?.body).toMatchObject({
      kind: "expense",
      amount: "6000",
      category_id: 4,
      mode: "cash",
    });
  });

  it("lets the owner record a bank withdrawal", async () => {
    mockApi(routes(OWNER));
    renderAt("/cash");
    const kind = await screen.findByLabelText("What happened");
    expect(within(kind).getByRole("option", { name: "Cash brought from the bank" })).toBeTruthy();
  });
});
