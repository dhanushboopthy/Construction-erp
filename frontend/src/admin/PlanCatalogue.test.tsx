import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "@/api/queryClient";

import { AdminApp } from "./AdminApp";
import { durationLabel, limitsNote, rupees } from "./labels";

const ADMIN = {
  id: 1,
  email: "ops@duolink.app",
  full_name: "Duolink Ops",
  mobile: null,
  role: "super_admin",
  must_change_password: false,
  last_login_at: null,
};
const SUPPORT = { ...ADMIN, id: 2, full_name: "Help Desk", role: "support" };

const plan = (id: number, code: string, name: string, extra: object = {}) => ({
  id,
  code,
  name,
  short_description: `${name} for a shop`,
  long_description: "",
  max_users: 10,
  max_locations: 3,
  features: ["EWAY_BILL"],
  is_active: true,
  is_popular: false,
  sort_order: id,
  prices: [
    {
      id: id * 10,
      duration_value: 1,
      duration_unit: "month",
      price: "999.90",
      currency: "INR",
      is_active: true,
    },
    {
      id: id * 10 + 1,
      duration_value: 1,
      duration_unit: "year",
      price: "123456.00",
      currency: "INR",
      is_active: true,
    },
  ],
  companies: 2,
  created_at: "2026-10-24T09:00:00Z",
  updated_at: "2026-10-24T09:00:00Z",
  ...extra,
});
const PLANS = [
  plan(1, "TRIAL", "Trial", { companies: 1 }),
  plan(2, "BASIC", "Basic", { companies: 4 }),
  plan(3, "PRO", "Pro", { is_popular: true, companies: 0 }),
  plan(4, "OLD", "Old", { is_active: false, companies: 0 }),
];
const FEATURES = [
  { code: "EWAY_BILL", name: "E-way bills", description: "Make e-way bills." },
  { code: "GST_EXPORTS", name: "GST exports", description: "GSTR-1 and 2B." },
];

type Route = (url: string, init?: RequestInit) => unknown;
type Call = { url: string; method: string; body?: string };

function stubApi(routes: [RegExp, Route][], admin: object = ADMIN) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      calls.push({ url, method: init?.method ?? "GET", body: init?.body as string | undefined });
      if (url.endsWith("/admin/auth/refresh")) {
        return new Response(
          JSON.stringify({ access_token: "t", token_type: "bearer", expires_in: 1800, admin }),
          { status: 200 },
        );
      }
      const match = routes.find(([pattern]) => pattern.test(url));
      if (!match) return new Response(JSON.stringify({ code: "NOT_FOUND" }), { status: 404 });
      const answer = match[1](url, init);
      if (answer instanceof Response) return answer;
      if (answer === undefined) return new Response(null, { status: 204 });
      return new Response(JSON.stringify(answer), { status: 200 });
    }),
  );
  return calls;
}

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<AdminApp client={createQueryClient()} />);
}

const catalogue: [RegExp, Route][] = [
  [/\/admin\/billing\/plans\/features$/, () => FEATURES],
  [/\/admin\/billing\/plans\/(\d+)$/, (url) => PLANS.find((p) => url.endsWith(`/${p.id}`))],
  [/\/admin\/billing\/plans/, () => PLANS],
];

const card = (name: string) => screen.findByRole("article", { name: `${name} plan` });

describe("plan labels", () => {
  it("writes prices from the server's text with Indian grouping and never rounds them", () => {
    expect(rupees("999.90")).toBe("₹999.90");
    expect(rupees("9999.00")).toBe("₹9,999.00");
    expect(rupees("123456.00")).toBe("₹1,23,456.00");
    expect(rupees("12345678.50")).toBe("₹1,23,45,678.50");
    expect(rupees("0.00")).toBe("₹0.00");
  });

  it("describes a duration and the limits", () => {
    expect(durationLabel(1, "month")).toBe("1 month");
    expect(durationLabel(14, "day")).toBe("14 days");
    expect(limitsNote({ max_users: 10, max_locations: 3 })).toBe("10 users, 3 shops and godowns");
    expect(limitsNote({ max_users: 1, max_locations: 1 })).toBe("1 user, 1 shop or godown");
  });
});

describe("AdminApp plans (M20)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows a card per active plan with its limits, prices and features", async () => {
    stubApi(catalogue);
    renderAt("/admin/plans");
    const pro = await card("Pro");
    expect(within(pro).getByText("Popular")).toBeInTheDocument();
    expect(within(pro).getByText("10 users, 3 shops and godowns")).toBeInTheDocument();
    expect(within(pro).getByText("₹999.90")).toBeInTheDocument();
    expect(within(pro).getByText("₹1,23,456.00")).toBeInTheDocument();
    expect(within(pro).getByText("E-way bills")).toBeInTheDocument();
    expect(
      within(await card("Basic")).getByText("4 companies are on this plan"),
    ).toBeInTheDocument();
    expect(within(await card("Trial")).getByText("1 company is on this plan")).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: "Old plan" })).not.toBeInTheDocument();
  });

  it("shows archived plans only when asked", async () => {
    stubApi(catalogue);
    const user = userEvent.setup();
    renderAt("/admin/plans");
    await card("Pro");
    await user.click(screen.getByLabelText("Show archived plans"));
    const old = await card("Old");
    expect(within(old).getByText("Archived")).toBeInTheDocument();
    expect(within(old).getByRole("button", { name: "Restore" })).toBeInTheDocument();
  });

  it("gives Support the catalogue to read and no way to change it", async () => {
    stubApi(catalogue, SUPPORT);
    renderAt("/admin/plans");
    await card("Pro");
    expect(screen.queryByRole("button", { name: "Add plan" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Archive|Delete|Copy/ })).not.toBeInTheDocument();
  });

  it("previews the card as the form is filled and sends the price as text", async () => {
    const calls = stubApi([
      [
        /\/admin\/billing\/plans$/,
        (_url, init) => (init?.method === "POST" ? plan(9, "GOLD", "Gold") : PLANS),
      ],
      ...catalogue,
    ]);
    const user = userEvent.setup();
    renderAt("/admin/plans");
    await user.click(await screen.findByRole("button", { name: "Add plan" }));
    await user.type(screen.getByLabelText("Code"), "gold");
    await user.type(screen.getByLabelText("Name"), "Gold");
    await user.type(screen.getByLabelText("Price 1 (rupees)"), "999.9");
    await user.click(await screen.findByLabelText("E-way bills"));
    await user.click(screen.getByLabelText("Popular"));

    const preview = screen.getByRole("article", { name: "Gold plan" });
    expect(within(preview).getByText("GOLD")).toBeInTheDocument();
    expect(within(preview).getByText("₹999.90")).toBeInTheDocument(); // padded to two decimals
    expect(within(preview).getByText("E-way bills")).toBeInTheDocument();
    expect(within(preview).getByText("Popular")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Add plan" }));
    const sent = JSON.parse(
      calls.find((c) => c.method === "POST" && c.url.endsWith("/billing/plans"))?.body ?? "{}",
    );
    expect(sent).toMatchObject({
      code: "GOLD",
      name: "Gold",
      features: ["EWAY_BILL"],
      is_popular: true,
      prices: [{ duration_value: 1, duration_unit: "month", price: "999.9" }],
    });
    expect(typeof sent.prices[0].price).toBe("string"); // a price is text, never a float
  });

  it("refuses a price that is not an amount, and keeps one to six price rows", async () => {
    const calls = stubApi(catalogue);
    const user = userEvent.setup();
    renderAt("/admin/plans");
    await user.click(await screen.findByRole("button", { name: "Add plan" }));
    await user.type(screen.getByLabelText("Code"), "gold");
    await user.type(screen.getByLabelText("Name"), "Gold");
    await user.click(screen.getByRole("button", { name: "Add plan" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Each price needs");
    expect(calls.some((c) => c.method === "POST" && c.url.includes("/billing/plans"))).toBe(false);

    expect(screen.getByRole("button", { name: "Remove price 1" })).toBeDisabled(); // at least one
    for (let i = 0; i < 5; i += 1) {
      await user.click(screen.getByRole("button", { name: "Add a price" }));
    }
    expect(screen.getByLabelText("Price 6 (rupees)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add a price" })).toBeDisabled(); // at most six
  });

  it("shows the server's reason when a plan is refused", async () => {
    stubApi([
      [
        /\/admin\/billing\/plans$/,
        (_url, init) =>
          init?.method === "POST"
            ? new Response(
                JSON.stringify({
                  code: "PLAN_CODE_TAKEN",
                  message: "A plan already has that code",
                }),
                { status: 409 },
              )
            : PLANS,
      ],
      ...catalogue,
    ]);
    const user = userEvent.setup();
    renderAt("/admin/plans");
    await user.click(await screen.findByRole("button", { name: "Add plan" }));
    await user.type(screen.getByLabelText("Code"), "PRO");
    await user.type(screen.getByLabelText("Name"), "Again");
    await user.type(screen.getByLabelText("Price 1 (rupees)"), "10");
    await user.click(screen.getByRole("button", { name: "Add plan" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A plan already has that code");
  });

  it("archives with a reason after fetching how many companies are on the plan", async () => {
    const calls = stubApi([
      [/\/admin\/billing\/plans\/2\/archive$/, () => ({ ...PLANS[1], is_active: false })],
      ...catalogue,
    ]);
    const user = userEvent.setup();
    renderAt("/admin/plans");
    const basic = await card("Basic");
    await user.click(within(basic).getByRole("button", { name: "Archive…" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(
      await within(dialog).findByText(/4 companies keep it and its limits/),
    ).toBeInTheDocument();
    expect(calls.filter((c) => c.url.endsWith("/billing/plans/2")).length).toBeGreaterThan(0); // fresh
    const archive = within(dialog).getByRole("button", { name: "Archive plan" });
    expect(archive).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Reason for archiving"), "Replaced by Pro");
    await user.click(archive);
    const sent = calls.find((c) => c.method === "POST" && c.url.endsWith("/2/archive"));
    expect(JSON.parse(sent?.body ?? "{}")).toEqual({ reason: "Replaced by Pro" });
  });

  it("offers Delete only for a plan nobody is on, and needs DELETE typed", async () => {
    const calls = stubApi([[/\/admin\/billing\/plans\/3\/delete$/, () => undefined], ...catalogue]);
    const user = userEvent.setup();
    renderAt("/admin/plans");
    expect(
      within(await card("Basic")).queryByRole("button", { name: "Delete…" }),
    ).not.toBeInTheDocument(); // companies are on it
    await user.click(within(await card("Pro")).getByRole("button", { name: "Delete…" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(await within(dialog).findByText(/No company is on it/)).toBeInTheDocument();
    const remove = within(dialog).getByRole("button", { name: "Delete plan" });
    await user.type(within(dialog).getByLabelText("Reason for deleting"), "Never sold");
    await user.type(within(dialog).getByLabelText("Type DELETE to confirm"), "delete");
    expect(remove).toBeDisabled(); // case matters
    await user.clear(within(dialog).getByLabelText("Type DELETE to confirm"));
    await user.type(within(dialog).getByLabelText("Type DELETE to confirm"), "DELETE");
    await user.click(remove);
    const sent = calls.find((c) => c.method === "POST" && c.url.endsWith("/3/delete"));
    expect(JSON.parse(sent?.body ?? "{}")).toEqual({
      confirmation: "DELETE",
      reason: "Never sold",
    });
  });

  it("restores an archived plan and copies a plan", async () => {
    const calls = stubApi([
      [/\/admin\/billing\/plans\/4$/, () => PLANS[3]],
      [/\/admin\/billing\/plans\/4$/, () => ({ ...PLANS[3], is_active: true })],
      [/\/admin\/billing\/plans\/2\/duplicate$/, () => plan(5, "BASIC_COPY", "Basic (copy)")],
      ...catalogue,
    ]);
    const user = userEvent.setup();
    renderAt("/admin/plans");
    await user.click(await screen.findByLabelText("Show archived plans"));
    await user.click(within(await card("Old")).getByRole("button", { name: "Restore" }));
    await user.click(within(await card("Basic")).getByRole("button", { name: "Copy" }));
    const restore = calls.find((c) => c.method === "PATCH" && c.url.endsWith("/plans/4"));
    expect(JSON.parse(restore?.body ?? "{}")).toEqual({ is_active: true });
    expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/plans/2/duplicate"))).toBe(
      true,
    );
  });

  it("is in the navigation for every role", async () => {
    stubApi(catalogue, SUPPORT);
    renderAt("/admin/plans");
    expect(await screen.findByRole("link", { name: /Plans/ })).toHaveAttribute(
      "href",
      "/admin/plans",
    );
  });
});
