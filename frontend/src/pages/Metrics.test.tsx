import { render, screen } from "@testing-library/react";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, S1, session } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const KPIS = [
  {
    code: "ccc_days",
    name: "Cash conversion cycle",
    formula: "DIO + DSO + advance days - DPO",
    meaning: "How many days your money is out of your hands.",
    example: "18.7 + 22.5 + 6.2 - 3.1 = 44.3 days",
    sources: "dio_days, dso_days",
    owner_only: true,
    refresh: "monthly",
    good: "down",
    unit: "days",
  },
  {
    code: "overdue_receivables",
    name: "Overdue receivables",
    formula: "Σ open bills past their due date",
    meaning: "Money customers should already have paid you.",
    example: "₹95,000 past due on 20 Oct",
    sources: "sales_invoice.due_date",
    owner_only: false,
    refresh: "live",
    good: "down",
    unit: "₹",
  },
];

describe("Metrics explained", () => {
  it("lists every metric from the catalogue with its formula, meaning and example", async () => {
    mockApi({
      ...session(OWNER),
      "GET /locations": () => ({ body: [S1] }),
      "GET /kpis/definitions": () => ({ body: KPIS }),
    });
    renderAt("/metrics");
    expect(await screen.findByRole("heading", { name: "Cash conversion cycle" })).toBeVisible();
    expect(screen.getByText("DIO + DSO + advance days - DPO")).toBeVisible();
    expect(screen.getByText("18.7 + 22.5 + 6.2 - 3.1 = 44.3 days")).toBeVisible();
    expect(screen.getByText("Money customers should already have paid you.")).toBeVisible();
    expect(screen.getAllByText("Lower is better")).toHaveLength(2);
    expect(screen.getByText(/monthly · owner only/)).toBeVisible();
    expect(screen.getByRole("link", { name: "docs/GLOSSARY.md" })).toHaveAttribute(
      "href",
      expect.stringContaining("GLOSSARY.md"),
    );
  });

  it("is not offered to counter staff", async () => {
    mockApi({ ...session(COUNTER), "GET /locations": () => ({ body: [S1] }) });
    renderAt("/metrics");
    expect(
      await screen.findByRole("heading", { name: "Not available for your role" }),
    ).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Metrics explained" })).toBeNull();
    expect(screen.queryByRole("link", { name: /Metrics explained/ })).toBeNull();
  });
});
