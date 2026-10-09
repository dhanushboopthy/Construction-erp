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

describe("Transfers", () => {
  it("refuses a move when the shop does not hold enough, in plain words", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(COUNTER),
      "GET /transfers": () => ({ body: [] }),
      "GET /items": () => ({ body: page([TMT_ITEM]) }),
      "GET /locations": () => ({ body: [S1, G1] }),
      "POST /transfers": () => ({
        status: 409,
        body: {
          code: "INSUFFICIENT_STOCK",
          message: "TMT: only 3000 here, cannot give out 3001 (rule B13)",
          field: "quantity",
        },
      }),
    });
    renderAt("/stock/transfers");
    await screen.findByRole("option", { name: "G1 Godown" });
    await user.selectOptions(screen.getByLabelText("To"), "3");
    await screen.findByRole("option", { name: "TMT bar 12 mm Fe500D" });
    await user.selectOptions(screen.getByLabelText("Item 1"), "10");
    await user.type(screen.getByLabelText("Quantity"), "3001");
    await user.click(screen.getByRole("button", { name: "Move stock" }));
    expect(await screen.findByText(/cannot give out 3001/)).toBeVisible();
  });
});

describe("Counts", () => {
  const draft = {
    id: 5,
    location_id: 1,
    location_code: "S1",
    count_date: "2026-10-09",
    status: "draft",
    note: null,
    total_variance_value: "0.00",
    lines: [
      {
        item_id: 10,
        item_name: "TMT bar 12 mm Fe500D",
        base_unit: "kg",
        system_qty: "10000.000",
        counted_qty: null,
        variance: null,
        variance_value: null,
      },
    ],
  };

  it("lets the owner post a count only after a second confirmation", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /locations": () => ({ body: [S1, G1] }),
      "GET /stock-counts": () => ({ body: [draft] }),
      "PUT /stock-counts/5/lines": () => ({ body: draft }),
      "POST /stock-counts/5/post": () => ({
        body: {
          ...draft,
          status: "posted",
          total_variance_value: "-1113.30",
          lines: [
            {
              ...draft.lines[0],
              counted_qty: "9980.000",
              variance: "-20.000",
              variance_value: "-1113.30",
            },
          ],
        },
      }),
    });
    renderAt("/stock/counts");
    await user.click(await screen.findByRole("button", { name: /S1 · 2026-10-09 · Draft/ }));
    await user.type(await screen.findByLabelText("Counted TMT bar 12 mm Fe500D"), "9980");
    await user.click(screen.getByRole("button", { name: "Post count" }));
    expect(calls.some((c) => c.path.endsWith("/post"))).toBe(false);
    await user.click(screen.getByRole("button", { name: "Yes, post the count" }));
    expect(await screen.findByText("Posted. Stock now matches the count.")).toBeVisible();
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
      lines: [{ item_id: 10, counted_qty: "9980" }],
    });
  });

  it("gives counter staff a save button but no post button", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(COUNTER),
      "GET /locations": () => ({ body: [S1] }),
      "GET /stock-counts": () => ({
        body: [
          {
            id: draft.id,
            location_id: draft.location_id,
            location_code: draft.location_code,
            count_date: draft.count_date,
            status: draft.status,
            note: draft.note,
            // The staff model has no worth column and no total (rule B4).
            lines: draft.lines.map((l) => ({
              item_id: l.item_id,
              item_name: l.item_name,
              base_unit: l.base_unit,
              system_qty: l.system_qty,
              counted_qty: l.counted_qty,
              variance: l.variance,
            })),
          },
        ],
      }),
    });
    renderAt("/stock/counts");
    await user.click(await screen.findByRole("button", { name: /S1 · 2026-10-09 · Draft/ }));
    const sheet = await screen.findByRole("table");
    expect(within(sheet).queryByText(/Worth/)).toBeNull();
    expect(screen.getByRole("button", { name: "Save counts" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Post count" })).toBeNull();
    expect(screen.getByText(/The owner posts the count/)).toBeVisible();
  });
});
