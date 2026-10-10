import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, G1, mockApi, OWNER, page, S1, session, TMT_ITEM } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const ENTRY = {
  id: 1,
  number: "S1A/26-27/00001",
  location_id: 1,
  location_code: "S1",
  adjustment_date: "2026-10-09",
  reason: "breakage",
  reason_label: "Breakage",
  note: null,
  approved: false,
  created_by_name: "Counter, Shop 1",
  lines: [{ item_id: 10, item_name: "TMT bar", base_unit: "kg", direction: "out", quantity: "2" }],
};
const BOOK = {
  date_from: "2026-10-01",
  date_to: "2026-10-09",
  location_id: null,
  entries: [ENTRY],
};
const OWNER_BOOK = {
  ...BOOK,
  entries: [
    {
      ...ENTRY,
      value: "760.00",
      itc_to_reverse: "136.80",
      lines: [{ ...ENTRY.lines[0], unit_cost: "380", value: "760.00" }],
    },
  ],
  by_reason: [{ reason: "breakage", reason_label: "Breakage", value: "760.00" }],
  net_loss: "760.00",
  itc_to_reverse: "136.80",
};

function routes(
  user: typeof OWNER,
  book: unknown,
  post?: () => { status?: number; body?: unknown },
) {
  return {
    ...session(user),
    "GET /locations": () => ({ body: [S1, G1] }),
    "GET /items": () => ({ body: page([TMT_ITEM]) }),
    "GET /stock-adjustments": () => ({ body: book }),
    ...(post ? { "POST /stock-adjustments": post } : {}),
  };
}

describe("Stock adjustments", () => {
  it("shows counter staff their adjustments without any value", async () => {
    mockApi(routes(COUNTER, BOOK));
    renderAt("/stock/adjustments");
    const table = await screen.findByRole("table", { name: "Adjustments this month" });
    expect(await within(table).findByText("S1A/26-27/00001")).toBeVisible();
    expect(within(table).queryByText(/₹/)).toBeNull();
    expect(screen.queryByText(/Stock lost this month/)).toBeNull();
    expect(screen.queryByLabelText("Where")).toBeNull(); // one shop: nothing to pick
  });

  it("asks for the owner's PIN when an adjustment is above the limit", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi(
      routes(COUNTER, BOOK, () => ({
        status: 409,
        body: {
          code: "ADJUSTMENT_NEEDS_OWNER",
          message: "Adjustments worth more than ₹10,000 need the owner's approval.",
          field: null,
          requires_owner_approval: true,
        },
      })),
    );
    renderAt("/stock/adjustments");
    await screen.findByRole("option", { name: TMT_ITEM.name });
    await user.selectOptions(screen.getByLabelText("Reason"), "theft");
    await user.selectOptions(screen.getByLabelText("Item 1"), "10");
    await user.type(screen.getByLabelText("Quantity"), "250");
    await user.click(screen.getByRole("button", { name: "Post adjustment" }));
    expect(
      await screen.findByText(/Owner approval needed to post this stock adjustment/),
    ).toBeVisible();
    const sent = calls.find((c) => c.method === "POST" && c.path === "/stock-adjustments");
    expect(sent?.body).toMatchObject({
      reason: "theft",
      location_id: 1,
      lines: [{ item_id: 10, quantity: "250", direction: "out" }],
    });
  });

  it("asks which way a count correction went", async () => {
    const user = userEvent.setup();
    mockApi(routes(OWNER, OWNER_BOOK));
    renderAt("/stock/adjustments");
    await screen.findByRole("option", { name: TMT_ITEM.name });
    await user.selectOptions(screen.getByLabelText("Reason"), "count_correction");
    await user.selectOptions(screen.getByLabelText("Item 1"), "10");
    await user.type(screen.getByLabelText("Quantity"), "5");
    await user.click(screen.getByRole("button", { name: "Post adjustment" }));
    expect(await screen.findByText(/whether the count found more or less/)).toBeVisible();
  });

  it("shows the owner the value lost by reason and the ITC to reverse", async () => {
    mockApi(routes(OWNER, OWNER_BOOK));
    renderAt("/stock/adjustments");
    const band = await screen.findByLabelText("This month");
    expect(within(band).getByText(/Stock lost this month/)).toBeVisible();
    expect(within(band).getAllByText("₹760.00")).toHaveLength(2);
    expect(within(band).getByText("₹136.80")).toBeVisible();
    expect(screen.getByLabelText("Where")).toBeVisible(); // the owner can adjust the godown
  });
});
