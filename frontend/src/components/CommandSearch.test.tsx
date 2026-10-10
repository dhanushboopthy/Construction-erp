import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";

import { actionsFor } from "@/actions";

import { CommandSearch } from "./CommandSearch";

function renderSearch(role: "owner" | "counter") {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <CommandSearch role={role} />
      <Routes>
        <Route path="/" element={<p>Home screen</p>} />
        <Route path="/purchases/new" element={<p>Purchase screen</p>} />
        <Route path="/stock" element={<p>Stock screen</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Command search", () => {
  it("opens with Ctrl+K, filters, and goes to the chosen action with Enter", async () => {
    const user = userEvent.setup();
    renderSearch("owner");

    await user.keyboard("{Control>}k{/Control}");
    const box = screen.getByRole("combobox", { name: "Search screens and actions" });
    expect(box).toHaveFocus();

    await user.type(box, "purchase");
    expect(screen.getByRole("option", { name: /New purchase/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await user.keyboard("{Enter}");
    expect(await screen.findByText("Purchase screen")).toBeVisible();
  });

  it("moves with the arrow keys and says when nothing matches", async () => {
    const user = userEvent.setup();
    renderSearch("owner");
    const box = screen.getByRole("combobox");

    await user.type(box, "stock");
    const options = screen.getAllByRole("option");
    expect(options.length).toBeGreaterThan(1);
    await user.keyboard("{ArrowDown}");
    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");

    await user.clear(box);
    await user.type(box, "zzzz");
    expect(screen.getByText(/Nothing matches/)).toBeVisible();
  });

  it("offers counter staff only what their role can open", () => {
    const ids = actionsFor("counter").map((a) => a.id);
    expect(ids).toContain("bill");
    expect(ids).not.toContain("rates");
    expect(ids).not.toContain("users");
  });
});
