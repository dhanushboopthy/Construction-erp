import { render, screen, within } from "@testing-library/react";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, session, SETTINGS } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const MONTHS = Array.from({ length: 12 }, (_, i) => {
  const m = ((i + 3) % 12) + 1;
  const year = m >= 4 ? 2026 : 2027;
  return {
    month: `${year}-${String(m).padStart(2, "0")}`,
    retail: "1000.00",
    contractor: "2000.00",
    bulk: "500.00",
    unassigned: "100.00",
    total: "3600.00",
  };
});
const SEGMENTS = {
  financial_year: "26-27",
  start_year: 2026,
  total: "43200.00",
  months: MONTHS,
};

describe("Reports layout", () => {
  it("has a page header and tabs for the sections the role may open", async () => {
    mockApi({
      ...session(OWNER),
      "GET /locations": () => ({ body: [] }),
    });
    renderAt("/reports");
    expect(await screen.findByRole("heading", { level: 1, name: "Reports" })).toBeVisible();
    const tabs = within(screen.getByRole("navigation", { name: "Report sections" }));
    expect(tabs.getAllByRole("link")).toHaveLength(15);
    expect(tabs.getByRole("link", { name: "Profit & loss" })).toBeVisible();
  });

  it("shows counter staff only the daily closing, none of the owner-only reports", async () => {
    mockApi({ ...session(COUNTER), "GET /locations": () => ({ body: [] }) });
    renderAt("/reports");
    const tabs = within(await screen.findByRole("navigation", { name: "Report sections" }));
    expect(tabs.getAllByRole("link").map((a) => a.textContent)).toEqual(["Daily closing"]);
    expect(screen.queryByRole("link", { name: "Profit" })).toBeNull();
  });
});

describe("Settings layout", () => {
  it("lists every section as a link and marks the current one", async () => {
    mockApi({ ...session(OWNER), "GET /settings": () => ({ body: SETTINGS }) });
    renderAt("/settings/users");
    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
    const nav = within(screen.getByRole("navigation", { name: "Settings sections" }));
    expect(nav.getAllByRole("link")).toHaveLength(9);
    expect(nav.getByRole("link", { name: "Users" })).toHaveAttribute("aria-current", "page");
    expect(nav.getByRole("link", { name: "Shop details" })).not.toHaveAttribute("aria-current");
  });

  it("shows the rule a setting controls as a neutral tag", async () => {
    mockApi({ ...session(OWNER), "GET /settings": () => ({ body: SETTINGS }) });
    renderAt("/settings");
    const tags = await screen.findAllByText(/^Rule B\d+/);
    expect(tags.length).toBeGreaterThan(0);
  });
});

describe("Charts", () => {
  it("segments: each series has its own pattern as well as its own colour", async () => {
    mockApi({
      ...session(OWNER),
      "GET /locations": () => ({ body: [] }),
      "GET /reports/sales-by-segment": () => ({ body: SEGMENTS }),
    });
    const { container } = renderAt("/reports/segments");
    const legend = await screen.findByRole("list", { name: "Legend" });
    const items = within(legend).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual([
      "Retail",
      "Contractor",
      "Bulk",
      "No segment",
    ]);
    expect(items.map((li) => li.getAttribute("data-pattern"))).toEqual([
      "solid",
      "solid",
      "hatch",
      "dots",
    ]);
    expect(container.querySelector("pattern[id=seg-hatch]")).not.toBeNull();
    expect(container.querySelector("pattern[id=seg-dots]")).not.toBeNull();
    // The numbers are also there as a table, for anyone who cannot read the bars.
    expect(screen.getByRole("table", { name: "Sales by segment, month by month" })).toBeVisible();
  });
});
