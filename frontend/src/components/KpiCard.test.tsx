import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Wallet } from "lucide-react";
import { MemoryRouter, Route, Routes } from "react-router";

import { KpiCard } from "./KpiCard";

const inRouter = (ui: React.ReactNode) => (
  <MemoryRouter>
    <Routes>
      <Route path="/" element={ui} />
      <Route path="/reports/dues" element={<p>Dues screen</p>} />
    </Routes>
  </MemoryRouter>
);

describe("KpiCard", () => {
  it("shows the label, the value and a note", () => {
    render(
      inRouter(<KpiCard label="Net sales today" value="₹12,500.00" note="vs last week +8%" />),
    );
    expect(screen.getByText("Net sales today")).toBeVisible();
    expect(screen.getByText("₹12,500.00")).toBeVisible();
    expect(screen.getByText("vs last week +8%")).toBeVisible();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("draws a progress bar with its numbers and the percentage in words", () => {
    render(
      inRouter(
        <KpiCard
          label="Customers owe"
          value="₹4,00,000.00"
          icon={Wallet}
          tone="warn"
          progress={{ value: 30, max: 120, label: "Share of dues overdue" }}
        />,
      ),
    );
    const bar = screen.getByRole("progressbar", { name: "Share of dues overdue" });
    expect(bar).toHaveAttribute("aria-valuenow", "30");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "120");
    expect(bar).toHaveAttribute("aria-valuetext", "25%");
    expect(screen.getByText("25%")).toBeVisible();
  });

  it("keeps the bar inside 0 to max", () => {
    render(inRouter(<KpiCard label="Used" value="1" progress={{ value: 150, label: "Used" }} />));
    const bar = screen.getByRole("progressbar", { name: "Used" });
    expect(bar).toHaveAttribute("aria-valuenow", "100");
    expect(bar).toHaveAttribute("aria-valuetext", "100%");
  });

  it("is one link when it has an href, reachable and openable by keyboard", async () => {
    const user = userEvent.setup();
    render(inRouter(<KpiCard label="Customers owe" value="₹0.00" href="/reports/dues" />));
    const link = screen.getByRole("link", { name: /Customers owe/ });
    expect(link).toHaveAttribute("href", "/reports/dues");
    await user.tab();
    expect(link).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(screen.getByText("Dues screen")).toBeVisible();
  });
});
