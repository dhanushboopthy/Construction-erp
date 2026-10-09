import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, page, session, TMT_ITEM } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

describe("Items for counter staff", () => {
  it("lists items read-only, with no margin and no way to add", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(COUNTER),
      "GET /items": () => ({ body: page([TMT_ITEM]) }),
      "GET /items/10/convert": () => ({
        body: { quantity: "2.5", from_unit: "ton", to_unit: "kg", result: "2500.000" },
      }),
    });
    renderAt("/items");

    await user.click(await screen.findByRole("button", { name: TMT_ITEM.name }));
    const detail = await screen.findByRole("complementary", { name: TMT_ITEM.name });
    expect(within(detail).getByText("72142090 at 18.00%")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Add item" })).toBeNull();
    expect(screen.queryByText(/margin/i)).toBeNull();

    await user.clear(within(detail).getByLabelText("Quantity"));
    await user.type(within(detail).getByLabelText("Quantity"), "2.5");
    await user.click(within(detail).getByRole("button", { name: "Convert" }));
    expect(await within(detail).findByText("2.5 ton = 2500.000 kg")).toBeVisible();
  });
});

describe("Items for the owner", () => {
  it("validates, then creates an item with decimal strings and listed units", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /items": () => ({ body: page([]) }),
      "POST /items": (body) => ({
        status: 201,
        body: { ...TMT_ITEM, ...(body as object), id: 11, min_margin: "1.2500" },
      }),
    });
    renderAt("/items");

    expect(await screen.findByText(/No items yet/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Add item" }));
    const panel = await screen.findByRole("complementary", { name: "New item" });
    await user.click(within(panel).getByRole("button", { name: "Create item" }));
    expect(within(panel).getByText(/Enter the item name/)).toBeVisible();
    expect(within(panel).getByText("HSN is 4 to 8 digits.")).toBeVisible();

    await user.type(within(panel).getByLabelText("Name"), "TMT bar 10 mm");
    await user.type(within(panel).getByLabelText("HSN"), "72142090");
    const margin = within(panel).getByLabelText(/Warn below margin/);
    await user.clear(margin);
    await user.type(margin, "1.25");
    await user.click(within(panel).getByRole("button", { name: "Add unit" }));
    await user.type(within(panel).getByLabelText("Unit 1"), "ton");
    await user.type(within(panel).getByLabelText(/kg per unit/), "1000");
    await user.click(within(panel).getByRole("button", { name: "Create item" }));

    expect(await screen.findByText("Item created.")).toBeVisible();
    const sent = calls.find((c) => c.method === "POST" && c.path === "/items")?.body as Record<
      string,
      unknown
    >;
    expect(sent).toMatchObject({
      name: "TMT bar 10 mm",
      hsn: "72142090",
      gst_rate: "18",
      base_unit: "kg",
      min_margin: "1.25",
      units: [{ unit: "ton", factor_to_base: "1000", whole_only: false }],
    });
  });

  it("checks an Excel file first and only saves after a clean check", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /items": () => ({ body: page([]) }),
      "POST /items/import": (_, url) => ({
        body:
          url.searchParams.get("dry_run") === "true"
            ? { dry_run: true, created: 2, updated: 1, errors: [] }
            : { dry_run: false, created: 2, updated: 1, errors: [] },
      }),
    });
    renderAt("/items");

    await user.click(await screen.findByRole("button", { name: "Import from Excel" }));
    const panel = await screen.findByRole("complementary", { name: "Import items from Excel" });
    expect(within(panel).getByRole("button", { name: "Check file" })).toBeDisabled();
    await user.upload(
      within(panel).getByLabelText("Excel file (.xlsx)"),
      new File(["x"], "items.xlsx"),
    );
    await user.click(within(panel).getByRole("button", { name: "Check file" }));
    expect(await within(panel).findByText(/File is fine: 2 new, 1 to update/)).toBeVisible();
    await user.click(within(panel).getByRole("button", { name: "Save 3 items" }));
    expect(await within(panel).findByText("Saved: 2 new, 1 updated.")).toBeVisible();
    expect(calls.filter((c) => c.path === "/items/import").map((c) => c.method)).toHaveLength(2);
  });

  it("lists the problems of a bad sheet and offers no save", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(OWNER),
      "GET /items": () => ({ body: page([]) }),
      "POST /items/import": () => ({
        body: {
          dry_run: true,
          created: 0,
          updated: 0,
          errors: [{ row: 3, field: "hsn", message: "String should match pattern" }],
        },
      }),
    });
    renderAt("/items");
    await user.click(await screen.findByRole("button", { name: "Import from Excel" }));
    const panel = await screen.findByRole("complementary", { name: "Import items from Excel" });
    await user.upload(
      within(panel).getByLabelText("Excel file (.xlsx)"),
      new File(["x"], "i.xlsx"),
    );
    await user.click(within(panel).getByRole("button", { name: "Check file" }));
    expect(await within(panel).findByText("Row 3, hsn: String should match pattern")).toBeVisible();
    expect(within(panel).queryByRole("button", { name: /^Save/ })).toBeNull();
  });
});
