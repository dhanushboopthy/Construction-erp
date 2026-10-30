import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import type { Role } from "@/api/types";
import { App } from "@/App";
import { modulesFor } from "@/modules";
import { COUNTER, mockApi, OWNER, session } from "@/test/mockApi";

const ACCOUNTANT: typeof OWNER = {
  ...COUNTER,
  id: 3,
  username: "accounts",
  full_name: "Accounts",
  role: "accountant",
  locations: [],
};
const TENANT = { name: "Anand Steels", tagline: "Bill fast. Close on time." };
const OUT = (id: number, name: string) => ({ item_id: id, name, quantity: "0.000" });
const IN_STOCK = { item_id: 9, name: "Cement 50 kg", quantity: "120.000" };
const EWAY = {
  invoice_id: 5,
  number: "INV/26-27/0005",
  party_name: "Ravi Traders",
  grand_total: "125000.00",
};

function shell(
  user: typeof OWNER,
  extra: {
    stock?: unknown[];
    eway?: unknown[];
    tenant?: unknown;
  } = {},
) {
  return mockApi({
    ...session(user),
    "GET /tenant": () => ({ body: extra.tenant ?? TENANT }),
    "GET /stock": () => ({ body: extra.stock ?? [IN_STOCK] }),
    "GET /eway-bills/pending": () => ({ body: extra.eway ?? [] }),
    "POST /auth/logout": () => ({ status: 204 }),
  });
}

function renderAt(path = "/items") {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const USERS: [Role, typeof OWNER][] = [
  ["owner", OWNER],
  ["counter", COUNTER],
  ["accountant", ACCOUNTANT],
];

describe("Sidebar modules", () => {
  it.each(USERS)("lists every module for the %s, and no more", async (role, user) => {
    shell(user);
    renderAt();
    const nav = await screen.findByRole("navigation", { name: "Modules" });
    const hrefs = within(nav)
      .getAllByRole("link")
      .map((a) => a.getAttribute("href"));
    expect(hrefs.sort()).toEqual(
      modulesFor(role)
        .map((m) => m.path)
        .sort(),
    );
  });

  it("puts Settings below a divider for the owner only", async () => {
    shell(OWNER);
    const { unmount } = renderAt();
    const nav = await screen.findByRole("navigation", { name: "Modules" });
    const lists = within(nav).getAllByRole("list");
    expect(lists).toHaveLength(2);
    expect(within(lists[1] as HTMLElement).getByRole("link", { name: /Settings/ })).toBeVisible();
    unmount();

    shell(COUNTER);
    renderAt();
    await screen.findByRole("navigation", { name: "Modules" });
    expect(screen.queryByRole("link", { name: /Settings/ })).toBeNull();
  });

  it("marks the current screen and shows the shortcut as a hint", async () => {
    shell(OWNER);
    renderAt("/items");
    const link = await screen.findByRole("link", { name: /Items/ });
    expect(link).toHaveAttribute("aria-current", "page");
    expect(link).toHaveAttribute("title", "Items (Alt 0)");
  });

  it("keeps Alt+number shortcuts", async () => {
    const user = userEvent.setup();
    shell(OWNER);
    renderAt("/items");
    await screen.findByRole("navigation", { name: "Modules" });
    await user.keyboard("{Alt>}2{/Alt}");
    expect(window.location.pathname).toBe("/sales");
    await user.keyboard("{Alt>}0{/Alt}");
    expect(window.location.pathname).toBe("/items");
  });

  it("keeps Ctrl+K for the command search", async () => {
    const user = userEvent.setup();
    shell(OWNER);
    renderAt();
    await screen.findByRole("navigation", { name: "Modules" });
    await user.keyboard("{Control>}k{/Control}");
    expect(screen.getByRole("combobox", { name: "Search screens and actions" })).toHaveFocus();
  });
});

describe("Business name", () => {
  it("comes from the API, with its initials in the tile and the tagline at the foot", async () => {
    shell(OWNER);
    renderAt();
    expect(await screen.findByText("Anand Steels")).toBeVisible();
    expect(screen.getByText("AS")).toBeVisible();
    expect(screen.getByText("Bill fast. Close on time.")).toBeVisible();
  });

  it("follows the API: another business shows its own name and nothing fixed", async () => {
    shell(COUNTER, { tenant: { name: "Sri Lakshmi Hardware", tagline: "Steel for every site" } });
    renderAt();
    expect(await screen.findByText("Sri Lakshmi Hardware")).toBeVisible();
    expect(screen.getByText("Steel for every site")).toBeVisible();
    expect(screen.queryByText(/BuildTrack/)).toBeNull();
    expect(screen.queryByText("Anand Steels")).toBeNull();
  });

  it("falls back to the product name when the API cannot say", async () => {
    mockApi({ ...session(OWNER), "GET /stock": () => ({ body: [] }) });
    renderAt();
    const nav = await screen.findByRole("navigation", { name: "Modules" });
    expect(nav).toBeVisible();
    expect(screen.getAllByText("Construction ERP").length).toBeGreaterThan(0);
  });
});

describe("Alerts", () => {
  it("shows the count as a badge and says it in words", async () => {
    shell(OWNER, { stock: [OUT(1, "TMT 12 mm"), OUT(2, "Binding wire"), IN_STOCK], eway: [EWAY] });
    renderAt();
    const button = await screen.findByRole("button", { name: /3 alerts/ });
    expect(within(button).getByText("3")).toBeVisible();
  });

  it("says 1 alert for one", async () => {
    shell(OWNER, { stock: [OUT(1, "TMT 12 mm")] });
    renderAt();
    expect(await screen.findByRole("button", { name: /1 alert\b/ })).toBeVisible();
  });

  it("hides the badge at zero", async () => {
    shell(OWNER);
    renderAt();
    // Two buttons open the panel (sidebar and bell); neither shows a count.
    await screen.findAllByRole("button", { name: "Alerts" });
    for (const button of screen.getAllByRole("button", { name: /^Alerts/ })) {
      expect(button).toHaveAccessibleName("Alerts");
      expect(within(button).queryByText("0")).toBeNull();
    }
    expect(screen.queryByText(/\d alerts?/)).toBeNull();
  });

  it("lights the bell in the top bar when there are alerts", async () => {
    shell(OWNER, { stock: [OUT(1, "TMT 12 mm")] });
    renderAt();
    expect(await screen.findByRole("button", { name: "Alerts, 1 need attention" })).toBeVisible();
  });

  it("opens the panel from the sidebar, fetches again, and lists what needs attention", async () => {
    const user = userEvent.setup();
    const { calls } = shell(OWNER, { stock: [OUT(1, "TMT 12 mm")], eway: [EWAY] });
    renderAt();
    const button = await screen.findByRole("button", { name: /2 alerts/ });
    const before = calls.filter((c) => c.path === "/stock").length;

    await user.click(button);
    const panel = await screen.findByRole("dialog", { name: "Alerts" });
    expect(within(panel).getByText("TMT 12 mm")).toBeVisible();
    expect(within(panel).getByText("E-way bill for INV/26-27/0005")).toBeVisible();
    expect(calls.filter((c) => c.path === "/stock").length).toBeGreaterThan(before);

    // Clicking the sidebar button again closes it (it is not an outside click), and Esc too.
    await user.click(button);
    expect(screen.queryByRole("dialog", { name: "Alerts" })).toBeNull();
    await user.click(button);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Alerts" })).toBeNull();
  });
});

describe("Top bar user menu", () => {
  it("shows the name and role, and opens a menu with the theme and Sign out", async () => {
    const user = userEvent.setup();
    document.documentElement.dataset.theme = "light";
    const { calls } = shell(COUNTER);
    renderAt();
    const trigger = await screen.findByRole("button", { name: /Account menu, .*Counter/ });
    expect(within(trigger).getByText("Counter")).toBeVisible();

    await user.click(trigger);
    const menu = screen.getByRole("dialog", { name: "Account" });
    await user.click(within(menu).getByRole("button", { name: "Dark mode" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(within(menu).getByRole("button", { name: "Light mode" })).toBeVisible();

    await user.click(within(menu).getByRole("button", { name: "Sign out" }));
    expect(calls.some((c) => c.method === "POST" && c.path === "/auth/logout")).toBe(true);
    expect(await screen.findByRole("heading", { name: "Sign in to the shop" })).toBeVisible();
    delete document.documentElement.dataset.theme;
    localStorage.clear();
  });

  it("closes with Esc and gives focus back to the button", async () => {
    const user = userEvent.setup();
    shell(OWNER);
    renderAt();
    const trigger = await screen.findByRole("button", { name: /Account menu/ });
    await user.click(trigger);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Account" })).toBeNull();
    expect(trigger).toHaveFocus();
  });
});
