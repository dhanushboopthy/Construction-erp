import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, page, PARTY, session, TMT_ITEM } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const ROW = {
  item_id: 10,
  item_name: "TMT bar 12 mm Fe500D",
  base_unit: "kg",
  rate: "55.000000",
  effective_date: "2026-10-08",
  previous_rate: null,
  units: ["kg", "ton"],
  quote_unit: "ton",
  rate_quoted: "55000.0000",
  previous_quoted: null,
  avg_cost: "55.0000",
  margin_per_unit: "1.250000",
  suggested_rate: "56.25",
  margin_now: "0.0000",
  below_cost: false,
  below_min_margin: true,
  avg_cost_quoted: "55000.0000",
  margin_quoted: "1250.0000",
  suggested_quoted: "56250.0000",
  margin_now_quoted: "0.0000",
};

describe("Daily rates", () => {
  it("is for the owner only", async () => {
    mockApi({ ...session(COUNTER) });
    renderAt("/rates");
    expect(
      await screen.findByRole("heading", { name: "Not available for your role" }),
    ).toBeVisible();
  });

  it("fills the suggested rate, saves only what changed, and warns about thin margin", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /rates/market": () => ({ body: [ROW] }),
      "PUT /rates/market": () => ({
        body: {
          saved: 1,
          warnings: [
            { item_id: 10, item_name: ROW.item_name, below_cost: false, below_min_margin: true },
          ],
        },
      }),
    });
    renderAt("/rates");

    expect(await screen.findByText("Thin margin")).toBeVisible();
    expect(screen.getByLabelText("Margin for TMT bar 12 mm Fe500D")).toHaveValue("1250");
    await user.click(screen.getByRole("button", { name: "Save rates" }));
    expect(await screen.findByText("Nothing has changed yet.")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Fill in suggested rates" }));
    expect(screen.getByLabelText("Rate for TMT bar 12 mm Fe500D")).toHaveValue("56250");
    await user.click(screen.getByRole("button", { name: "Save rates" }));
    expect(await screen.findByText(/Saved 1 rate for/)).toBeVisible();
    expect(screen.getByText("TMT bar 12 mm Fe500D: margin is below your minimum")).toBeVisible();
    const sent = calls.find((c) => c.method === "PUT" && c.path === "/rates/market")?.body;
    expect(sent).toMatchObject({ rates: [{ item_id: 10, rate: "56250", unit: "ton" }] });
    // The margin was not touched, so it is not sent.
    expect(calls.some((c) => c.path === "/margins")).toBe(false);
  });

  it("creates a customer rate in the unit it was agreed in", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /customer-rates": () => ({ body: [] }),
      "GET /parties": () => ({ body: page([PARTY]) }),
      "GET /items": () => ({ body: page([TMT_ITEM]) }),
      "POST /customer-rates": () => ({ status: 201, body: {} }),
    });
    renderAt("/rates/customers");
    await screen.findByText(/Everyone pays the daily rate/);
    const form = screen.getByRole("form", { name: "New customer rate" });
    await user.click(within(form).getByRole("button", { name: "Add rate" }));
    expect(await screen.findByText("Pick the customer and the item.")).toBeVisible();
    await user.selectOptions(await within(form).findByLabelText("Customer"), "20");
    await user.selectOptions(await within(form).findByLabelText("Item"), "10");
    await user.type(within(form).getByLabelText("Agreed rate (₹)"), "54500");
    await user.click(within(form).getByRole("button", { name: "Add rate" }));
    await vi.waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.path === "/customer-rates")).toBe(true),
    );
    expect(
      calls.find((c) => c.method === "POST" && c.path === "/customer-rates")?.body,
    ).toMatchObject({
      party_id: 20,
      item_id: 10,
      rate: "54500",
      unit: "ton",
      valid_to: null,
    });
  });
});
