import { render, screen, within } from "@testing-library/react";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, session } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const BASE = {
  as_of: "2026-10-28",
  items_in_stock: 2,
  out_of_stock: [{ item_id: 3, name: "Binding wire 18 g", base_unit: "kg" }],
  reorder: [
    {
      item_id: 2,
      name: "Cement PPC",
      base_unit: "bag",
      on_hand: "8.000",
      reorder_point: "9.000",
      short_by: "1.000",
    },
  ],
  enough_history: true,
};

describe("Stock dashboard", () => {
  it("shows the owner values by place and category, what ran out and what to order", async () => {
    mockApi({
      ...session(OWNER),
      "GET /stock/dashboard": () => ({
        body: {
          ...BASE,
          stock_value: "180150.00",
          dead_stock_value: "14000.00",
          places: [{ location_id: 1, code: "S1", name: "Shop 1", items: 2, value: "152400.00" }],
          categories: [{ category: "tmt", items: 1, value: "166500.00" }],
        },
      }),
    });
    renderAt("/stock/dashboard");
    expect(await screen.findByText("₹1,80,150.00")).toBeVisible();
    const places = screen.getByRole("table", { name: "By place" });
    expect(within(places).getByText("1,52,400.00")).toBeVisible();
    const out = screen.getByRole("table", { name: "Out of stock" });
    expect(within(out).getByText(/Binding wire/)).toBeVisible();
    const order = screen.getByRole("table", { name: "To order now" });
    expect(within(order).getByText("8 bag")).toBeVisible();
    expect(within(order).getByText("9 bag")).toBeVisible();
  });

  it("gives counter staff counts and quantities only", async () => {
    mockApi({
      ...session(COUNTER),
      "GET /stock/dashboard": () => ({
        body: {
          ...BASE,
          places: [{ location_id: 1, code: "S1", name: "Shop 1", items: 2 }],
          categories: [{ category: "tmt", items: 1 }],
        },
      }),
    });
    renderAt("/stock/dashboard");
    const places = await screen.findByRole("table", { name: "By place" });
    expect(within(places).queryByText(/Value/)).toBeNull();
    expect(screen.queryByText("Stock value")).toBeNull();
    expect(screen.queryByText(/Dead stock/)).toBeNull();
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeVisible();
  });
});
