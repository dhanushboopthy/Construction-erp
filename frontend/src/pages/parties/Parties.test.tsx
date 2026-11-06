import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, PARTY, page, session } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

describe("Parties", () => {
  it("shows counter staff the credit terms but no way to change them", async () => {
    const user = userEvent.setup();
    mockApi({ ...session(COUNTER), "GET /parties": () => ({ body: page([PARTY]) }) });
    renderAt("/parties");

    await user.click(await screen.findByRole("button", { name: "Ravi Builders" }));
    const panel = await screen.findByRole("complementary", { name: "Ravi Builders" });
    expect(within(panel).getByText(/Credit allowed up to ₹15,000.00/)).toBeVisible();
    expect(within(panel).queryByLabelText("Credit limit (₹)")).toBeNull();
    expect(within(panel).getAllByText("Anna Nagar villa").length).toBeGreaterThan(0);
  });

  it("lets the owner set credit terms", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /parties": () => ({ body: page([PARTY]) }),
      "PATCH /parties/20": (body) => ({ body: { ...PARTY, ...(body as object) } }),
    });
    renderAt("/parties");

    await user.click(await screen.findByRole("button", { name: "Ravi Builders" }));
    const panel = await screen.findByRole("complementary", { name: "Ravi Builders" });
    const limit = within(panel).getByLabelText("Credit limit (₹)");
    await user.clear(limit);
    await user.type(limit, "25000");
    await user.click(within(panel).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Changes saved.")).toBeVisible();
    expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({
      credit_allowed: true,
      credit_limit: "25000",
      credit_days: 10,
    });
  });

  it("fetches a party's details from the GST registry and keeps what was typed", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /parties": () => ({ body: page([PARTY]) }),
      "POST /parties/gstin-lookup": () => ({
        body: {
          gstin: "29AAPFU0939F1ZV",
          legal_name: "Kaveri Cement Agencies Private Limited",
          trade_name: "Kaveri Cement",
          address: "12 Main Road, Bengaluru",
          state_code: "29",
          status: "Active",
          fetched_at: "2026-11-03T10:00:00Z",
          cached: false,
          lookups_left_today: 49,
          near_limit: false,
        },
      }),
    });
    renderAt("/parties");
    await user.click(await screen.findByRole("button", { name: "Add party" }));
    const panel = await screen.findByRole("complementary", { name: "New party" });
    const fetch = within(panel).getByRole("button", { name: "Fetch details" });
    expect(fetch).toBeDisabled(); // nothing to look up yet
    await user.type(within(panel).getByLabelText("GSTIN"), "bad");
    await user.click(fetch);
    expect(await within(panel).findByRole("alert")).toHaveTextContent("15-character GSTIN");
    await user.clear(within(panel).getByLabelText("GSTIN"));
    await user.type(within(panel).getByLabelText("GSTIN"), "29aapfu0939f1zv");
    await user.type(within(panel).getByLabelText("Name"), "My own name");
    await user.click(fetch);
    expect(await within(panel).findByRole("status")).toHaveTextContent(
      "Kaveri Cement Agencies Private Limited · Active. 49 lookups left today.",
    );
    expect(within(panel).getByLabelText("Name")).toHaveValue("My own name");
    expect(within(panel).getByLabelText("Address")).toHaveValue("12 Main Road, Bengaluru");
    expect(within(panel).getByLabelText("State")).toHaveValue("29");
    expect(calls.find((c) => c.path === "/parties/gstin-lookup")?.body).toEqual({
      gstin: "29AAPFU0939F1ZV",
    });
  });

  it("tells the user in words when the company is over its lookup limit", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(OWNER),
      "GET /parties": () => ({ body: page([PARTY]) }),
      "POST /parties/gstin-lookup": () => ({
        status: 429,
        body: {
          code: "GSTIN_LOOKUP_LIMIT",
          message: "Your company has used its GSTIN lookups for now.",
          field: null,
        },
      }),
    });
    renderAt("/parties");
    await user.click(await screen.findByRole("button", { name: "Add party" }));
    const panel = await screen.findByRole("complementary", { name: "New party" });
    await user.type(within(panel).getByLabelText("GSTIN"), "29AAPFU0939F1ZV");
    await user.click(within(panel).getByRole("button", { name: "Fetch details" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent(
      "Your company has used its GSTIN lookups for now.",
    );
  });

  it("lets the owner set a supplier's delivery time for the reorder points", async () => {
    const user = userEvent.setup();
    const supplier = { ...PARTY, id: 21, name: "Mills", type: "supplier" as const };
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /parties": () => ({ body: page([supplier]) }),
      "PATCH /parties/21": (body) => ({ body: { ...supplier, ...(body as object) } }),
    });
    renderAt("/parties");
    await user.click(await screen.findByRole("button", { name: "Mills" }));
    const panel = await screen.findByRole("complementary", { name: "Mills" });
    await user.type(within(panel).getByLabelText(/Delivery lead time/), "10");
    await user.click(within(panel).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Changes saved.")).toBeVisible();
    expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ lead_time_days: 10 });
  });

  it("adds a site, and a new customer counter user cannot send credit fields", async () => {
    const user = userEvent.setup();
    let created: typeof PARTY | null = null;
    const { calls } = mockApi({
      ...session(COUNTER),
      "GET /parties": () => ({ body: page(created ? [created] : []) }),
      "POST /parties": (body) => {
        created = { ...PARTY, ...(body as object), sites: [] };
        return { status: 201, body: created };
      },
      "POST /parties/20/sites": () => ({ status: 201, body: PARTY.sites[0] }),
    });
    renderAt("/parties");

    await user.click(await screen.findByRole("button", { name: "Add party" }));
    const panel = await screen.findByRole("complementary", { name: "New party" });
    await user.click(within(panel).getByRole("button", { name: "Create party" }));
    expect(within(panel).getByText(/Enter the name/)).toBeVisible();
    await user.type(within(panel).getByLabelText("Name"), "Ravi Builders");
    await user.type(within(panel).getByLabelText("GSTIN"), "33ABC");
    await user.click(within(panel).getByRole("button", { name: "Create party" }));
    expect(within(panel).getByText(/A GSTIN has 15 characters/)).toBeVisible();
    await user.clear(within(panel).getByLabelText("GSTIN"));
    await user.click(within(panel).getByRole("button", { name: "Create party" }));

    expect(await screen.findByText(/Party created/)).toBeVisible();
    const sent = calls.find((c) => c.method === "POST" && c.path === "/parties")?.body;
    expect(sent).toMatchObject({ credit_allowed: false, credit_limit: null, credit_days: null });

    await user.click(await screen.findByRole("button", { name: "Add site" }));
    await user.type(screen.getByLabelText("Site name"), "Anna Nagar villa");
    await user.click(screen.getByRole("button", { name: "Add site", hidden: false }));
    expect(calls.some((c) => c.path === "/parties/20/sites")).toBe(true);
  });
});
