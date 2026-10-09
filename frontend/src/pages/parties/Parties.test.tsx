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
