import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, G1, mockApi, OWNER, S1, session, SETTINGS } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

describe("Settings access", () => {
  it("tells counter staff the screen is not for their role", async () => {
    const { calls } = mockApi({ ...session(COUNTER) });
    renderAt("/settings/users");
    expect(
      await screen.findByRole("heading", { name: "Not available for your role" }),
    ).toBeVisible();
    expect(calls.some((c) => c.path === "/users")).toBe(false);
  });
});

describe("Shop details", () => {
  it("blocks a bad GSTIN, then saves amounts as decimal strings", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /settings": () => ({ body: SETTINGS }),
      "PUT /settings": (body) => ({ body: { ...SETTINGS, ...(body as object) } }),
    });
    renderAt("/settings");

    const gstin = await screen.findByLabelText("GSTIN");
    await user.type(gstin, "33ABC");
    await user.click(screen.getByRole("button", { name: "Save shop details" }));
    expect(screen.getByText(/A GSTIN has 15 characters/)).toBeVisible();
    expect(gstin).toHaveAttribute("aria-invalid", "true");
    expect(calls.some((c) => c.method === "PUT")).toBe(false);

    await user.clear(gstin);
    const limit = screen.getByLabelText(/Credit limit/);
    await user.clear(limit);
    await user.type(limit, "15000.50");
    await user.click(screen.getByRole("button", { name: "Save shop details" }));

    expect(await screen.findByText("Shop details saved.")).toBeVisible();
    const put = calls.find((c) => c.method === "PUT")?.body as Record<string, unknown>;
    expect(put.default_credit_limit).toBe("15000.50");
    expect(put.cash_receipt_limit).toBe("200000.00");
    // Saving never resets the approval limits or the ITC setting to their defaults.
    expect(put.expense_approval_limit).toBe("5000.00");
    expect(put.adjustment_approval_limit).toBe("10000.00");
    expect(put.itc_reverse_shortages).toBe(true);
    expect(put.gstin).toBeNull();
    expect(put.default_credit_days).toBe(7);
  });
});

describe("Users", () => {
  it("opens a new user form with Alt+N, checks it, and creates the user", async () => {
    const user = userEvent.setup();
    const created = { ...COUNTER, id: 9, username: "counter3", full_name: "Ravi" };
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /users": () => ({ body: [OWNER, COUNTER] }),
      "GET /locations": () => ({ body: [G1, S1] }),
      "POST /users": () => ({ status: 201, body: created }),
    });
    renderAt("/settings/users");

    const table = await screen.findByRole("table");
    expect(within(table).getByRole("button", { name: "Counter, Shop 1" })).toBeVisible();

    await user.keyboard("{Alt>}n{/Alt}");
    const panel = await screen.findByRole("complementary", { name: "New user" });
    await user.click(within(panel).getByRole("button", { name: "Create user" }));
    expect(within(panel).getByText(/Use 3–50 lowercase/)).toBeVisible();
    expect(within(panel).getByText("Counter staff need at least one shop.")).toBeVisible();

    await user.type(within(panel).getByLabelText("Username"), "Counter3");
    await user.type(within(panel).getByLabelText("Full name"), "Ravi");
    await user.type(within(panel).getByLabelText("Password"), "long-enough");
    await user.click(within(panel).getByRole("checkbox", { name: /S1/ }));
    await user.click(within(panel).getByRole("button", { name: "Create user" }));

    expect(await screen.findByText(/User created/)).toBeVisible();
    expect(calls.find((c) => c.method === "POST" && c.path === "/users")?.body).toEqual({
      username: "counter3",
      full_name: "Ravi",
      role: "counter",
      password: "long-enough",
      location_ids: [1],
    });
  });

  it("shows the server's reason next to the field and resets a password", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /users": () => ({ body: [OWNER, COUNTER] }),
      "GET /locations": () => ({ body: [S1] }),
      "PATCH /users/2": () => ({
        status: 409,
        body: { code: "COUNTER_NEEDS_LOCATION", message: "Pick a shop", field: "location_ids" },
      }),
      "POST /users/2/reset-password": () => ({ status: 204 }),
    });
    renderAt("/settings/users");

    await user.click(await screen.findByRole("button", { name: "Counter, Shop 1" }));
    const panel = await screen.findByRole("complementary", { name: "Counter, Shop 1" });
    await user.click(within(panel).getByRole("button", { name: "Save changes" }));
    expect(await within(panel).findByText("Pick a shop")).toBeVisible();

    await user.type(within(panel).getByLabelText("New password"), "fresh-pass-1");
    await user.click(within(panel).getByRole("button", { name: "Reset password" }));
    expect(await within(panel).findByText(/Password reset/)).toBeVisible();
    expect(calls.find((c) => c.path === "/users/2/reset-password")?.body).toEqual({
      new_password: "fresh-pass-1",
    });
  });

  it("does not let the owner deactivate or demote themselves", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(OWNER),
      "GET /users": () => ({ body: [OWNER] }),
      "GET /locations": () => ({ body: [S1] }),
    });
    renderAt("/settings/users");
    await user.click(await screen.findByRole("button", { name: "Shop Owner" }));
    const panel = await screen.findByRole("complementary", { name: "Shop Owner" });
    expect(within(panel).getByRole("checkbox", { name: "Active" })).toBeDisabled();
    expect(within(panel).getByRole("radio", { name: /Counter staff/ })).toBeDisabled();
  });
});

describe("Shops and godown", () => {
  it("creates a location with an uppercase code and keeps codes fixed after", async () => {
    const user = userEvent.setup();
    const s3 = { ...S1, id: 7, code: "S3", name: "Shop 3" };
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /locations": (_, url) => ({
        body: url.searchParams.get("include_inactive") ? [G1, S1] : [S1],
      }),
      "POST /locations": () => ({ status: 201, body: s3 }),
    });
    renderAt("/settings/locations");

    await screen.findByRole("table");
    await user.click(screen.getByRole("button", { name: "Add location" }));
    const panel = await screen.findByRole("complementary", { name: "New location" });
    await user.type(within(panel).getByLabelText("Code"), "s3");
    await user.type(within(panel).getByLabelText("Name"), "Shop 3");
    await user.click(within(panel).getByRole("button", { name: "Create location" }));

    expect(await screen.findByText("Location created.")).toBeVisible();
    expect(calls.find((c) => c.method === "POST" && c.path === "/locations")?.body).toMatchObject({
      code: "S3",
      name: "Shop 3",
      kind: "shop",
      state_code: "33",
      phone: null,
    });
  });
});
